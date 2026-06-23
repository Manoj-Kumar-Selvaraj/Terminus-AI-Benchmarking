#!/usr/bin/env python3
"""Audit NEEDS_REVISION tasks from stb feedback; classify clean vs needs-fix."""
from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STB = "/root/.local/bin/stb"
OUT = ROOT / "Revision-ChatGpt" / "revision_audit"
OUT.mkdir(parents=True, exist_ok=True)

# id -> local folder
MAPPING: dict[str, str] = {}
for line in (ROOT / "needs_revision_mapped.txt").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    parts = line.split()
    if len(parts) >= 2:
        MAPPING[parts[0]] = parts[1]

for line in (ROOT / "batch11_submission_map.txt").read_text(encoding="utf-8").splitlines():
    line = line.strip()
    if not line or line.startswith("#"):
        continue
    parts = line.split()
    if len(parts) >= 2:
        MAPPING[parts[0]] = parts[1]

# extra IDs from platform list not in mapping
EXTRA = {
    "d0295913-57b4-4d22-ae74-449c845df95e": None,
    "3a6b0228-726b-4d9a-a39a-c31830e2744d": None,
    "5f8ce7c6-9981-4d2a-9194-540fcdfa9e6b": None,
    "a870f40f-b704-4edd-98fe-77fb6d05f3bf": None,
    "4375ed22-f2cf-457a-8e84-223859fcb2d2": None,
    "0377ba70-c90c-4d91-8083-e835bdcffeac": None,
    "0122149a-0a15-44c5-8703-ac5cfe6d6b59": None,
    "1e20b807-48d1-4496-aeb9-8b92f62cead9": None,
    "d99e0689-a056-4793-87ff-0f85431d97e1": None,
}
for k, v in EXTRA.items():
    MAPPING.setdefault(k, v)

PLATFORM_ALIASES = {
    "ruby-music-royalty-live-settlement-ledger": "ruby-music-royalty-live-settlement-router",
    "ruby-parking-garage-session-refund-matcher": "ruby-parking-garage-session-adjustment-clearing",
    "go-live-auction-bid-reversal-matcher": "go-live-auction-bid-reversal-ledger",
    "pl1-cobol-atm-risk-release-reconciler": "pl1-cobol-atm-risk-release-router",
    "ruby-cooking-class-voucher-refund-matcher": "ruby-cooking-class-voucher-matcher",
    "ruby-go-bash-vineyard-club-credit-ledger": "ruby-go-bash-vineyard-club-shipment-credit-router",
    "cobol-escrow-return-reconciler": "cobol-escrow-return-reconciliation",
}


def local_folder(platform_name: str | None, sid: str) -> str | None:
    if sid in MAPPING and MAPPING[sid]:
        return MAPPING[sid]
    if platform_name:
        if (ROOT / platform_name).is_dir():
            return platform_name
        if platform_name in PLATFORM_ALIASES:
            return PLATFORM_ALIASES[platform_name]
    return None


def fetch_feedback(sid: str) -> Path | None:
    try:
        subprocess.run([STB, "submissions", "feedback", sid], check=True, capture_output=True, text=True, timeout=120)
    except subprocess.CalledProcessError as e:
        print(f"fetch fail {sid}: {e.stderr[:200]}", file=sys.stderr)
        return None
    except subprocess.TimeoutExpired:
        print(f"fetch timeout {sid}", file=sys.stderr)
        return None
    tmp = sorted(Path("/tmp").glob(f"feedback_{sid}_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    return tmp[0] if tmp else None


def parse_feedback(fb_dir: Path) -> dict:
    notes = (fb_dir / "notes.txt").read_text(encoding="utf-8", errors="replace") if (fb_dir / "notes.txt").is_file() else ""
    agent = (fb_dir / "agent_review.txt").read_text(encoding="utf-8", errors="replace") if (fb_dir / "agent_review.txt").is_file() else ""
    text = notes + "\n" + agent

    def has_fail(pattern: str) -> bool:
        return bool(re.search(pattern, text, re.I))

    llmaj_fails = re.findall(r"❌ fail - ([^\n]+)", notes)
    llmaj_pass = "Quality check summary" in notes and not llmaj_fails

    return {
        "autoeval_fail": has_fail(r"AutoEval execution failed|Build status: FAILED"),
        "oracle_fail_msg": has_fail(r"Oracle solution failed|not tested with any agents as the Oracle"),
        "agent_warning": has_fail(r"Status:\s*⚠️\s*WARNING"),
        "agent_critical": has_fail(r"CRITICAL|Status:\s*❌"),
        "agent_suggestion": bool(re.search(r"SUGGESTIONS 💡", agent)),
        "agent_warnings_section": bool(re.search(r"WARNINGS ⚠️", agent)),
        "ready_to_use": has_fail(r"RECOMMENDATION: ✅ READY TO USE"),
        "instruction_sufficiency_fail": has_fail(r"Instruction Sufficiency.*❌|instruction_sufficiency.*fail|Task Instruction Sufficiency: ❌"),
        "test_quality_fail": has_fail(r"Test Quality.*❌|test quality.*fail"),
        "difficulty_issue": has_fail(r"TRIVIAL|pass rate too high|too easy|Difficulty.*❌"),
        "llmaj_fails": llmaj_fails,
        "llmaj_clean": llmaj_pass,
    }


def check_local_task(folder: str) -> list[str]:
    issues: list[str] = []
    td = ROOT / folder
    if not td.is_dir():
        issues.append("missing_local_folder")
        return issues
    toml = td / "task.toml"
    if not toml.is_file():
        issues.append("missing_task.toml")
        return issues
    text = toml.read_text(encoding="utf-8")
    if "[agent]" not in text or re.search(r"^\[agent\]", text, re.M) is None:
        if "[steps.agent]" in text and not re.search(r"^\[agent\]", text, re.M):
            issues.append("missing_root_[agent]")
    if "[verifier]" not in text or re.search(r"^\[verifier\]", text, re.M) is None:
        if "[steps.verifier]" in text and not re.search(r"^\[verifier\]", text, re.M):
            issues.append("missing_root_[verifier]")
    # test.sh reward pattern
    for sh in td.glob("steps/milestone_*/tests/test.sh"):
        c = sh.read_text(encoding="utf-8")
        if "if python3 -m pytest" in c and "; then" in c:
            issues.append(f"bad_test_sh_reward:{sh.relative_to(td)}")
        if "set -euo pipefail" in c:
            issues.append(f"test_sh_has_set_e:{sh.relative_to(td)}")
    if list(td.glob("scripts/debug*.py")) or list(td.glob("scripts/*.py")):
        py_scripts = list(td.glob("scripts/*.py"))
        if py_scripts:
            issues.append(f"task_root_py_scripts:{len(py_scripts)}")
    return issues


def classify(parsed: dict, local_issues: list[str]) -> str:
    blockers = []
    if parsed["autoeval_fail"] or parsed["oracle_fail_msg"]:
        blockers.append("autoeval_oracle")
    if parsed["llmaj_fails"]:
        blockers.extend(parsed["llmaj_fails"][:3])
    if parsed["instruction_sufficiency_fail"]:
        blockers.append("instruction_sufficiency")
    if parsed["test_quality_fail"]:
        blockers.append("test_quality")
    if parsed["difficulty_issue"]:
        blockers.append("difficulty")
    if parsed["agent_critical"]:
        blockers.append("agent_critical")
    if local_issues:
        blockers.extend(local_issues)
    if blockers:
        return "NEEDS_FIX"
    if parsed["agent_warning"] or parsed["agent_warnings_section"] or parsed["agent_suggestion"]:
        return "WARNINGS_ONLY"
    if parsed["llmaj_clean"] and parsed["ready_to_use"] and not parsed["autoeval_fail"]:
        return "CLEAN"
    return "REVIEW"


def main() -> None:
    ids_file = ROOT / "needs_revision_all_ids.txt"
    if not ids_file.is_file():
        print("Run stb list first to create needs_revision_all_ids.txt", file=sys.stderr)
        sys.exit(1)

    rows = []
    for line in ids_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        sid, _, folder = (line.split("\t") + ["", ""])[:3]
        folder = folder or MAPPING.get(sid) or ""
        if "fitness-class" in folder:
            continue
        if not folder and sid in MAPPING:
            folder = MAPPING[sid] or ""
        print(f"Fetching {sid} {folder}...")
        fb = fetch_feedback(sid)
        time.sleep(1)
        parsed = parse_feedback(fb) if fb else {"autoeval_fail": True, "oracle_fail_msg": True, "llmaj_fails": ["fetch_failed"], "llmaj_clean": False, "agent_warning": True, "agent_critical": False, "agent_suggestion": False, "agent_warnings_section": False, "ready_to_use": False, "instruction_sufficiency_fail": False, "test_quality_fail": False, "difficulty_issue": False}
        local = check_local_task(folder) if folder else ["unknown_folder"]
        status = classify(parsed, local)
        rows.append((status, sid, folder, parsed, local))
        print(f"  -> {status} local={local} llmaj={parsed.get('llmaj_fails')}")

    summary = OUT / "audit_summary.md"
    lines = ["# Revision audit\n", "| Status | Task | Submission ID | Issues |\n", "|--------|------|---------------|--------|\n"]
    for status, sid, folder, parsed, local in sorted(rows, key=lambda r: (r[0], r[2])):
        issues = local + parsed.get("llmaj_fails", [])
        if parsed.get("autoeval_fail"):
            issues.append("autoeval_fail")
        if parsed.get("agent_warning"):
            issues.append("agent_warning")
        if parsed.get("instruction_sufficiency_fail"):
            issues.append("instruction_sufficiency")
        lines.append(f"| {status} | {folder or '?'} | `{sid[:8]}…` | {', '.join(issues[:5]) or 'none'} |\n")
    summary.write_text("".join(lines), encoding="utf-8")
    print(f"Wrote {summary}")
    for label in ("CLEAN", "WARNINGS_ONLY", "NEEDS_FIX", "REVIEW"):
        n = sum(1 for r in rows if r[0] == label)
        print(f"{label}: {n}")


if __name__ == "__main__":
    main()
