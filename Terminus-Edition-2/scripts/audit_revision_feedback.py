#!/usr/bin/env python3
"""Fetch and audit portal feedback for all NEEDS_REVISION mapped tasks."""
from __future__ import annotations

import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STB = "/root/.local/bin/stb"
OUT = ROOT / "Revision-ChatGpt" / "revision_audit_report.md"
FB_DIR = ROOT / "Revision-ChatGpt" / "portal_feedback"

ALIASES = {
    "ruby-music-royalty-live-settlement-ledger": "ruby-music-royalty-live-settlement-router",
    "ruby-parking-garage-session-refund-matcher": "ruby-parking-garage-session-adjustment-clearing",
    "go-live-auction-bid-reversal-matcher": "go-live-auction-bid-reversal-ledger",
    "pl1-cobol-atm-risk-release-reconciler": "pl1-cobol-atm-risk-release-router",
    "ruby-cooking-class-voucher-refund-matcher": "ruby-cooking-class-voucher-matcher",
    "ruby-go-bash-vineyard-club-credit-ledger": "ruby-go-bash-vineyard-club-shipment-credit-router",
    "cobol-escrow-return-reconciler": "cobol-escrow-return-reconciliation",
}


def local_folder(platform: str) -> str:
    return ALIASES.get(platform, platform)


def load_tasks() -> list[tuple[str, str, str]]:
    rows = []
    for line in (ROOT / "needs_revision_mapped.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        sid, platform = line.split(None, 1)
        rows.append((sid, platform, local_folder(platform)))
    return rows


def fetch(sid: str) -> Path | None:
    try:
        subprocess.run([STB, "submissions", "feedback", sid], check=True, capture_output=True, text=True, timeout=180)
    except Exception as e:
        print(f"  fetch error: {e}", file=sys.stderr)
        return None
    candidates = sorted(Path("/tmp").glob(f"feedback_{sid}_*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        return None
    dest = FB_DIR / f"audit_{sid}"
    # stb writes to /tmp; copy notes+agent_review for offline parse
    notes_src = candidates[0] / "notes.txt"
    agent_src = candidates[0] / "agent_review.txt"
    if notes_src.is_file():
        dest.mkdir(parents=True, exist_ok=True)
        (dest / "notes.txt").write_text(notes_src.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        if agent_src.is_file():
            (dest / "agent_review.txt").write_text(agent_src.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
        return dest
    return None


def find_cached(sid: str, folder: str) -> Path | None:
    audit = FB_DIR / f"audit_{sid}"
    if (audit / "notes.txt").is_file():
        return audit
    for p in sorted(FB_DIR.glob(f"*{sid}*"), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.is_dir() and (p / "notes.txt").is_file():
            return p
        if p.is_file() and p.suffix == ".txt":
            return p
    for p in sorted(FB_DIR.glob(f"feedback_{folder}*"), key=lambda x: x.stat().st_mtime, reverse=True):
        if p.is_file():
            return p
    return None


def read_fb(path: Path) -> tuple[str, str]:
    if path.is_dir():
        notes = (path / "notes.txt").read_text(encoding="utf-8", errors="replace") if (path / "notes.txt").is_file() else ""
        agent = (path / "agent_review.txt").read_text(encoding="utf-8", errors="replace") if (path / "agent_review.txt").is_file() else ""
        return notes, agent
    text = path.read_text(encoding="utf-8", errors="replace")
    if "=== notes.txt ===" in text:
        parts = text.split("=== agent_review.txt ===")
        notes = parts[0].replace("=== notes.txt ===", "")
        agent = parts[1] if len(parts) > 1 else ""
        return notes, agent
    return text, ""


def parse(notes: str, agent: str) -> dict:
    t = notes + "\n" + agent

    llmaj_fails = re.findall(r"❌ fail - ([^\n]+)", notes)
    llmaj_pass = bool(re.search(r"Quality check summary", notes)) and not llmaj_fails

    # Revision notes often retain stale AutoEval fail from original NEEDS_REVISION flag.
    # Recent resubmit (2026-06-09) returned PASS for all 30 — treat stale infra fail separately.
    autoeval = "stale_fail_note"
    if re.search(r"Oracle solution failed|not tested with any agents as the Oracle", notes, re.I):
        autoeval = "oracle_fail"
    elif re.search(r"oracle: 100\.0%|Reference Agents:.*oracle: 100", notes, re.I):
        autoeval = "oracle_ok"
    if re.search(r"AutoEval execution failed|Build status: FAILED", notes, re.I):
        autoeval = "stale_fail_note" if autoeval == "oracle_ok" else autoeval

    diff = "unknown"
    dm = re.search(r"Difficulty:\s*([✅❌]?\s*(?:HARD|MEDIUM|TRIVIAL|EASY)\w*)", notes, re.I)
    if dm:
        diff = re.sub(r"^[✅❌]\s*", "", dm.group(1)).strip().upper()
    if re.search(r"Difficulty:\s*❌|TRIVIAL|too easy|pass rate too high", notes, re.I):
        diff = "ISSUE"

    instr = "unknown"
    if re.search(r"Instruction Sufficiency:\s*✅|Task Instruction Sufficiency: ✅", notes, re.I):
        instr = "pass"
    elif re.search(r"Instruction Sufficiency:\s*❌|Task Instruction Sufficiency: ❌", notes, re.I):
        instr = "fail"

    testq = "pass"
    if re.search(r"Test Quality.*❌|test quality.*fail", notes, re.I):
        testq = "fail"

    agent_status = "none"
    if re.search(r"Status:\s*❌", agent):
        agent_status = "critical"
    elif re.search(r"Status:\s*⚠️\s*WARNING", agent):
        agent_status = "warning"
    elif re.search(r"READY TO USE", agent):
        agent_status = "ready"

    human = "n/a"
    if re.search(r"Revision Notes", notes):
        rn = notes.split("Revision Notes", 1)[-1].split("Summary (difficulty check)", 1)[0].strip()
        if rn and len(rn) > 20 and "AutoEval" not in rn[:80]:
            human = rn[:120].replace("\n", " ")

    warnings = []
    for m in re.finditer(r"WARNINGS ⚠️[\s\S]*?(?=SUGGESTIONS|OVERALL ASSESSMENT|$)", agent):
        for line in m.group(0).splitlines():
            if re.match(r"^\d+\.", line.strip()):
                warnings.append(line.strip()[:80])

    return {
        "llmaj": "pass" if llmaj_pass else ("fail" if llmaj_fails else "unknown"),
        "llmaj_fails": llmaj_fails[:3],
        "autoeval": autoeval,
        "difficulty": diff,
        "instruction_sufficiency": instr,
        "test_quality": testq,
        "agent_status": agent_status,
        "agent_warnings": warnings[:2],
        "human_notes": human,
    }


def classify(p: dict) -> str:
    blockers = []
    if p["autoeval"] == "oracle_fail":
        blockers.append("oracle_fail")
    if p["llmaj"] == "fail":
        blockers.append("llmaj")
    if p["instruction_sufficiency"] == "fail":
        blockers.append("instruction_sufficiency")
    if p["test_quality"] == "fail":
        blockers.append("test_quality")
    if p.get("difficulty") == "ISSUE" or p.get("difficulty") == "TRIVIAL":
        blockers.append("difficulty")
    if p["agent_status"] == "critical":
        blockers.append("agent_critical")
    if blockers:
        return "NEEDS_FIX"
    if p["agent_status"] in ("warning", "ready") and p["llmaj"] == "pass":
        return "GOOD"
    if p["llmaj"] == "pass" and p["instruction_sufficiency"] in ("pass", "unknown"):
        return "GOOD"
    return "REVIEW"


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true", help="Fetch fresh feedback from stb")
    ap.add_argument("--no-fetch", action="store_true", help="Use cached feedback only")
    args = ap.parse_args()
    do_fetch = args.fetch or not args.no_fetch

    tasks = load_tasks()
    rows = []
    for sid, platform, folder in tasks:
        print(f"Audit {folder} ({sid[:8]}...)")
        fb_path = None
        if do_fetch:
            fb_path = fetch(sid)
            time.sleep(1.5)
        if not fb_path:
            fb_path = find_cached(sid, folder)
        if not fb_path:
            p = {k: "unknown" for k in ("llmaj", "autoeval", "difficulty", "instruction_sufficiency", "test_quality", "agent_status")}
            p["llmaj_fails"] = ["no_feedback"]
            p["agent_warnings"] = []
            p["human_notes"] = "n/a"
            status = "NO_FEEDBACK"
        else:
            notes, agent = read_fb(fb_path)
            p = parse(notes, agent)
            status = classify(p)
        rows.append((status, folder, sid, p))

    good = [r for r in rows if r[0] in ("GOOD", "GOOD_WARNINGS_ONLY")]
    fix = [r for r in rows if r[0] == "NEEDS_FIX"]
    other = [r for r in rows if r[0] not in ("GOOD", "GOOD_WARNINGS_ONLY", "NEEDS_FIX")]

    lines = [
        "# Revision audit report\n\n",
        f"Tasks: {len(rows)} | **Good (leave as-is):** {len(good)} | **Needs fix:** {len(fix)} | **Review/other:** {len(other)}\n\n",
        "## Leave as-is (good tasks)\n\n",
        "| Task | AutoEval | LLMaJ | Agent | Instr suff | Difficulty |\n",
        "|------|----------|-------|-------|------------|------------|\n",
    ]
    for status, folder, sid, p in sorted(good, key=lambda r: r[1]):
        lines.append(
            f"| {folder} | {p.get('autoeval','?')} | {p.get('llmaj','?')} | {p.get('agent_status','?')} | {p.get('instruction_sufficiency','?')} | {p.get('difficulty','?')} |\n"
        )

    lines.append("\n## Needs fix\n\n| Task | Issues |\n|------|--------|\n")
    for status, folder, sid, p in sorted(fix, key=lambda r: r[1]):
        issues = []
        if p.get("autoeval") in ("fail", "oracle_fail"):
            issues.append("autoeval")
        if p.get("llmaj") == "fail":
            issues.extend(p.get("llmaj_fails", []))
        if p.get("instruction_sufficiency") == "fail":
            issues.append("instruction_sufficiency")
        if p.get("test_quality") == "fail":
            issues.append("test_quality")
        if p.get("difficulty") == "issue":
            issues.append("difficulty")
        if p.get("agent_status") == "critical":
            issues.append("agent_critical")
        lines.append(f"| {folder} | {', '.join(issues) or 'see feedback'} |\n")

    if other:
        lines.append("\n## Review / no feedback\n\n| Task | Status | Notes |\n|------|--------|-------|\n")
        for status, folder, sid, p in sorted(other, key=lambda r: r[1]):
            lines.append(f"| {folder} | {status} | {p.get('llmaj_fails', [''])[0] if isinstance(p.get('llmaj_fails'), list) else ''} |\n")

    lines.append("\n## Agent warnings (cosmetic — safe to ignore if READY TO USE)\n\n")
    for status, folder, sid, p in rows:
        if p.get("agent_warnings"):
            lines.append(f"- **{folder}:** {'; '.join(p['agent_warnings'])}\n")

    OUT.write_text("".join(lines), encoding="utf-8")
    print(f"\nWrote {OUT}")
    print(f"GOOD={len(good)} NEEDS_FIX={len(fix)} OTHER={len(other)}")


if __name__ == "__main__":
    main()
