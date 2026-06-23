#!/usr/bin/env python3
"""Summarize audit_* feedback folders per REVISION_POLICY.md."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FB = ROOT / "Revision-ChatGpt" / "portal_feedback"

ALIASES = {
    "ruby-music-royalty-live-settlement-ledger": "ruby-music-royalty-live-settlement-router",
    "ruby-parking-garage-session-refund-matcher": "ruby-parking-garage-session-adjustment-clearing",
    "go-live-auction-bid-reversal-matcher": "go-live-auction-bid-reversal-ledger",
    "pl1-cobol-atm-risk-release-reconciler": "pl1-cobol-atm-risk-release-router",
    "ruby-cooking-class-voucher-refund-matcher": "ruby-cooking-class-voucher-matcher",
    "ruby-go-bash-vineyard-club-credit-ledger": "ruby-go-bash-vineyard-club-shipment-credit-router",
    "cobol-escrow-return-reconciler": "cobol-escrow-return-reconciliation",
}


def extract_section(agent: str, section: str) -> str:
    """Return body text between a section header and the next major section."""
    idx = agent.find(section)
    if idx < 0:
        return ""
    rest = agent[idx + len(section) :]
    # Skip decorative ==== line after header
    rest = re.sub(r"^[\s=⚠️💡✅❌\-]+\n", "", rest, count=1)
    stops = ("SUGGESTIONS", "OVERALL ASSESSMENT", "WARNINGS", "RECOMMENDATION:")
    end = len(rest)
    for stop in stops:
        if stop == section:
            continue
        pos = rest.find(stop)
        if 0 <= pos < end:
            end = pos
    return rest[:end]


def count_agent_items(agent: str, section: str) -> int:
    body = extract_section(agent, section)
    if not body:
        return 0
    return len(re.findall(r"^\d+\.\s", body, re.MULTILINE))


def parse_agent_status(agent: str) -> str:
    m = re.search(r"Status:\s*([^\n]+)", agent)
    if not m:
        return "none"
    line = m.group(1)
    if "CRITICAL" in line or "NEEDS REVISION" in line:
        return "CRITICAL"
    if "WARNING" in line:
        return "WARNING"
    if "PASS" in line:
        return "PASS"
    return "unknown"


def difficulty_valid(diff: str, diff_raw: str | None) -> bool:
    if not diff_raw or diff == "not_run":
        return False
    if "❌" in diff_raw:
        return False
    upper = diff.upper()
    if "EASY" in upper or "TRIVIAL" in upper:
        return False
    return "HARD" in upper or "MEDIUM" in upper


def load_tasks(manifest_path: Path) -> list[tuple[str, str, str]]:
    tasks = []
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        sid = parts[0].strip()
        folder = parts[1].strip() if len(parts) > 1 else ""
        if folder == "UNKNOWN":
            folder = ""
        tasks.append((sid, folder, folder or "ORPHAN"))
    return tasks


manifest = ROOT / "Revision-ChatGpt" / "queue_45_manifest.txt"
if not manifest.is_file():
    manifest = ROOT / "needs_revision_mapped.txt"
    tasks = []
    for line in manifest.read_text().splitlines():
        if line.strip() and not line.startswith("#"):
            sid, plat = line.split(None, 1)
            tasks.append((sid, ALIASES.get(plat, plat), ALIASES.get(plat, plat)))
else:
    tasks = load_tasks(manifest)

rows = []
for sid, folder, label in tasks:
    plat = label
    if not folder:
        folder = label
    p = FB / f"audit_{sid}"
    notes = (p / "notes.txt").read_text(encoding="utf-8", errors="replace") if (p / "notes.txt").is_file() else ""
    agent = (p / "agent_review.txt").read_text(encoding="utf-8", errors="replace") if (p / "agent_review.txt").is_file() else ""
    has_local = bool(folder and folder != "ORPHAN" and (ROOT / folder).is_dir())

    if not folder or folder == "ORPHAN" or not has_local:
        rows.append((sid, folder or "ORPHAN", "ORPHAN", ["no_local_folder"], {
            "sid": sid, "folder": folder or "ORPHAN", "has_local": False,
            "agent_warnings": 0, "agent_suggestions": 0, "diff": "-", "instr": "-", "oracle": "-", "llmaj": "-",
        }))
        continue

    if not notes:
        rows.append((sid, folder, "NO_FEEDBACK", [], {}))
        continue

    llmaj_fails = re.findall(r"❌ fail - ([^:\n]+)", notes)
    llmaj_ok = bool(re.search(r"✅ pass -", notes)) and not llmaj_fails

    diff_m = re.search(r"Difficulty:\s*([^\n]+)", notes)
    diff_raw = diff_m.group(1) if diff_m else None
    diff = diff_raw.replace("✅", "").replace("❌", "").strip() if diff_raw else "not_run"

    instr = "not_run"
    if re.search(r"Instruction Sufficiency:\s*✅", notes):
        instr = "PASS"
    elif re.search(r"Instruction Sufficiency:\s*❌", notes):
        instr = "FAIL"

    oracle = "not_run"
    stale_oracle = bool(re.search(r"not tested with any agents as the Oracle", notes))
    if re.search(r"oracle: 100\.0%", notes):
        oracle = "100%"
    elif stale_oracle:
        oracle = "stale_fail_msg"

    agent_status = parse_agent_status(agent)
    agent_warnings = count_agent_items(agent, "WARNINGS")
    agent_suggestions = count_agent_items(agent, "SUGGESTIONS")

    diff_ok = difficulty_valid(diff, diff_raw)
    instr_ok = instr == "PASS"
    oracle_ok = oracle == "100%"

    issues = []
    code_issues = []

    if agent_warnings > 0:
        issues.append(f"agent_warnings({agent_warnings})")
        code_issues.append(f"agent_warnings({agent_warnings})")
    if agent_suggestions > 0:
        issues.append(f"agent_suggestions({agent_suggestions})")
        code_issues.append(f"agent_suggestions({agent_suggestions})")
    if agent_status == "CRITICAL":
        issues.append("agent_critical")
        code_issues.append("agent_critical")

    if instr == "FAIL":
        issues.append("instruction_sufficiency")
        code_issues.append("instruction_sufficiency")
    elif not instr_ok:
        issues.append("instruction_sufficiency_not_run")
    if llmaj_fails:
        issues.extend(llmaj_fails[:3])
        code_issues.extend(llmaj_fails[:3])
    if diff_raw and ("❌" in diff_raw or diff.upper().startswith("EASY") or "TRIVIAL" in diff.upper()):
        issues.append("difficulty")
        code_issues.append("difficulty")
    elif not diff_ok:
        issues.append("difficulty_not_run")
    if not oracle_ok:
        issues.append("oracle_not_100")
    if stale_oracle and not diff_ok:
        issues.append("stale_oracle_msg")

    resubmit_only = (
        not code_issues
        and issues
        and all(
            i in ("difficulty_not_run", "instruction_sufficiency_not_run", "oracle_not_100", "stale_oracle_msg")
            for i in issues
        )
    )

    if not issues:
        status = "READY"
    elif resubmit_only:
        status = "RESUBMIT"
    else:
        status = "FIX"

    meta = {
        "sid": sid,
        "folder": folder,
        "has_local": has_local,
        "diff": diff,
        "instr": instr,
        "oracle": oracle,
        "llmaj": "pass" if llmaj_ok else ("fail" if llmaj_fails else "?"),
        "agent_status": agent_status,
        "agent_warnings": agent_warnings,
        "agent_suggestions": agent_suggestions,
        "diff_ok": diff_ok,
        "instr_ok": instr_ok,
        "oracle_ok": oracle_ok,
        "code_issues": code_issues,
    }
    rows.append((sid, folder, status, issues, meta))

ready = [r for r in rows if r[2] == "READY"]
resubmit = [r for r in rows if r[2] == "RESUBMIT"]
fix = [r for r in rows if r[2] == "FIX"]
orphan = [r for r in rows if r[2] == "ORPHAN"]
nofb = [r for r in rows if r[2] == "NO_FEEDBACK"]

out = ROOT / "Revision-ChatGpt" / "revision_audit_report.md"
lines = [
    "# Revision audit — REVISION_POLICY aligned\n\n",
    "Policy: fix any agent WARNING/SUGGESTION; require difficulty HARD/MEDIUM, ",
    "instruction sufficiency PASS, oracle 100%.\n\n",
    f"Audited: **{len(rows)}** | **Ready: {len(ready)}** | ",
    f"**Resubmit only: {len(resubmit)}** | **Needs code fix: {len(fix)}** | ",
    f"**Orphans (no local folder): {len(orphan)}** | No feedback: {len(nofb)}\n\n",
    "---\n\n",
]

if fix:
    lines.append("## Needs code fix before resubmit\n\n")
    lines.append(
        "| Task | Blockers | Warnings | Suggestions | Difficulty | Instr | Oracle | LLMaJ |\n"
    )
    lines.append("|------|----------|----------|-------------|------------|-------|--------|-------|\n")
    for sid, folder, status, issues, m in sorted(fix, key=lambda x: x[1]):
        lines.append(
            f"| {folder} | {', '.join(issues[:4])} | {m['agent_warnings']} | "
            f"{m['agent_suggestions']} | {m['diff']} | {m['instr']} | {m['oracle']} | {m['llmaj']} |\n"
        )
    lines.append("\n")

if resubmit:
    lines.append("## Resubmit only (no code changes — refresh difficulty/instr/oracle)\n\n")
    lines.append("| Task | Missing | Difficulty | Instr | Oracle |\n")
    lines.append("|------|---------|------------|-------|--------|\n")
    for sid, folder, status, issues, m in sorted(resubmit, key=lambda x: x[1]):
        lines.append(
            f"| {folder} | {', '.join(issues)} | {m['diff']} | {m['instr']} | {m['oracle']} |\n"
        )
    lines.append("\n")

if ready:
    lines.append("## Ready for reviewer resubmit\n\n")
    lines.append("| Task | Difficulty | Instr | Oracle | Agent |\n")
    lines.append("|------|------------|-------|--------|-------|\n")
    for sid, folder, status, issues, m in sorted(ready, key=lambda x: x[1]):
        lines.append(
            f"| {folder} | {m['diff']} | {m['instr']} | {m['oracle']} | {m['agent_status']} |\n"
        )
    lines.append("\n")

lines.append("---\n\n## Per-task detail (agent review open items)\n\n")
for sid, folder, status, issues, m in sorted(rows, key=lambda x: x[1]):
    if m.get("agent_warnings") or m.get("agent_suggestions"):
        lines.append(
            f"- **{folder}** (`{sid}`): {m['agent_warnings']} warning(s), "
            f"{m['agent_suggestions']} suggestion(s), status={m['agent_status']}\n"
        )

lines.append("\n## Do NOT fix (challenge reviewer if suggested)\n\n")
lines.append("- Remove root `[agent]` / `[verifier]` — static checks require them\n")
lines.append("- Rename `tbench-task` directory — platform unpack behavior\n")

out.write_text("".join(lines), encoding="utf-8")
print(out)
print(f"READY={len(ready)} RESUBMIT={len(resubmit)} FIX={len(fix)} NOFB={len(nofb)}")
for sid, folder, status, issues, m in fix:
    print(f"  FIX {folder}: {issues}")
