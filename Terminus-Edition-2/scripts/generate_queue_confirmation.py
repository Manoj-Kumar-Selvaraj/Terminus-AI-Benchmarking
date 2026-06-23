#!/usr/bin/env python3
"""Generate queue_45_confirmation.md from manifest + audit folders."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FB = ROOT / "Revision-ChatGpt" / "portal_feedback"
MANIFEST = ROOT / "Revision-ChatGpt" / "queue_45_manifest.txt"
OUT = ROOT / "Revision-ChatGpt" / "queue_45_confirmation.md"

# Import audit helpers
import sys

sys.path.insert(0, str(ROOT / "scripts"))
from summarize_audit_notes import (  # noqa: E402
    count_agent_items,
    difficulty_valid,
    parse_agent_status,
)


def audit_row(sid: str, folder: str) -> tuple[str, list[str], dict]:
    if not folder or folder == "UNKNOWN" or folder == "ORPHAN":
        return "ORPHAN", ["no_local_folder"], {}
    if not (ROOT / folder).is_dir():
        return "ORPHAN", ["no_local_folder"], {}

    p = FB / f"audit_{sid}"
    notes = (p / "notes.txt").read_text(encoding="utf-8", errors="replace") if (p / "notes.txt").is_file() else ""
    agent = (p / "agent_review.txt").read_text(encoding="utf-8", errors="replace") if (p / "agent_review.txt").is_file() else ""

    if not notes:
        return "NO_FEEDBACK", ["fetch_feedback"], {}

    llmaj_fails = re.findall(r"❌ fail - ([^:\n]+)", notes)
    diff_m = re.search(r"Difficulty:\s*([^\n]+)", notes)
    diff_raw = diff_m.group(1) if diff_m else None
    diff = diff_raw.replace("✅", "").replace("❌", "").strip() if diff_raw else "not_run"

    instr = "not_run"
    if re.search(r"Instruction Sufficiency:\s*✅", notes):
        instr = "PASS"
    elif re.search(r"Instruction Sufficiency:\s*❌", notes):
        instr = "FAIL"

    oracle = "not_run"
    if re.search(r"oracle: 100\.0%", notes):
        oracle = "100%"
    elif re.search(r"not tested with any agents as the Oracle", notes):
        oracle = "stale_fail_msg"

    aw = count_agent_items(agent, "WARNINGS")
    asug = count_agent_items(agent, "SUGGESTIONS")
    agent_st = parse_agent_status(agent)

    issues = []
    if aw:
        issues.append(f"warnings({aw})")
    if asug:
        issues.append(f"suggestions({asug})")
    if instr == "FAIL":
        issues.append("instr_FAIL")
    elif instr == "not_run":
        issues.append("instr_not_run")
    if llmaj_fails:
        issues.extend(llmaj_fails[:2])
    if diff_raw and ("❌" in diff_raw or "EASY" in diff.upper() or "TRIVIAL" in diff.upper()):
        issues.append("difficulty")
    elif not difficulty_valid(diff, diff_raw):
        issues.append("diff_not_run")
    if oracle != "100%":
        issues.append("oracle_not_100")

    code_fix = any(
        x.startswith("warnings") or x.startswith("suggestions") or x == "instr_FAIL"
        or x.startswith("behavior") or x == "typos" or x == "difficulty"
        for x in issues
    )

    if not issues:
        status = "READY"
    elif code_fix:
        status = "FIX"
    else:
        status = "RESUBMIT"

    meta = {
        "diff": diff, "instr": instr, "oracle": oracle, "llmaj": "fail" if llmaj_fails else "pass",
        "agent": agent_st, "warnings": aw, "suggestions": asug,
    }
    return status, issues, meta


def main() -> None:
    rows = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split("\t")
        sid = parts[0].strip()
        folder = parts[1].strip()
        if folder == "UNKNOWN":
            folder = ""
        status, issues, meta = audit_row(sid, folder)
        rows.append((sid, folder or "ORPHAN", status, issues, meta))

    header = MANIFEST.read_text(encoding="utf-8").splitlines()
    stats_line = next((l for l in header if l.startswith("# Total")), "")

    buckets = {"READY": [], "FIX": [], "RESUBMIT": [], "ORPHAN": [], "NO_FEEDBACK": []}
    for r in rows:
        buckets[r[2]].append(r)

    lines = [
        "# Queue confirmation — non-fitness NEEDS_REVISION\n\n",
        stats_line.replace("# ", "") + "\n\n",
        f"Confirmed scope: **{len(rows)}** tasks (excludes 5 go-fitness duplicates).\n\n",
        "## Summary\n\n",
        f"| Verdict | Count |\n|--------|-------|\n",
    ]
    for k in ("READY", "FIX", "RESUBMIT", "NO_FEEDBACK", "ORPHAN"):
        lines.append(f"| {k} | {len(buckets[k])} |\n")

    lines.append("\n---\n\n## Ready for rubric + reviewer submit\n\n")
    if buckets["READY"]:
        lines.append("| Task | Submission ID | Difficulty | Instr | Oracle |\n")
        lines.append("|------|---------------|------------|-------|--------|\n")
        for sid, folder, _, _, m in sorted(buckets["READY"], key=lambda x: x[1]):
            lines.append(f"| {folder} | `{sid}` | {m['diff']} | {m['instr']} | {m['oracle']} |\n")
    else:
        lines.append("_None yet — fetch fresh feedback and close blockers per REVISION_POLICY._\n")

    lines.append("\n## Needs code fix\n\n")
    if buckets["FIX"]:
        lines.append("| Task | Submission ID | Blockers | Diff | Instr | Oracle |\n")
        lines.append("|------|---------------|----------|------|-------|--------|\n")
        for sid, folder, _, issues, m in sorted(buckets["FIX"], key=lambda x: x[1]):
            lines.append(
                f"| {folder} | `{sid}` | {', '.join(issues[:4])} | {m.get('diff','-')} | "
                f"{m.get('instr','-')} | {m.get('oracle','-')} |\n"
            )
    else:
        lines.append("_None classified as FIX (or feedback not fetched yet)._\n")

    lines.append("\n## Resubmit only (refresh difficulty/instr/oracle)\n\n")
    for sid, folder, _, issues, m in sorted(buckets["RESUBMIT"], key=lambda x: x[1]):
        lines.append(f"- **{folder}** (`{sid}`): {', '.join(issues)}\n")

    lines.append("\n## Orphans (no local repo folder)\n\n")
    lines.append("See [`queue_45_orphans.txt`](queue_45_orphans.txt). Resolve or ignore stale submissions.\n\n")
    for sid, folder, _, _, _ in sorted(buckets["ORPHAN"], key=lambda x: x[0]):
        lines.append(f"- `{sid}`\n")

    lines.append("\n## Next actions\n\n")
    lines.append("1. Close FIX items per [`REVISION_POLICY.md`](REVISION_POLICY.md)\n")
    lines.append("2. Re-run `bash scripts/fetch_queue_feedback.sh` after fixes\n")
    lines.append("3. Paste rubrics + `stb submissions update <folder> -s <id> --time 90` (no `--no-send-to-reviewer`) for READY tasks\n")

    OUT.write_text("".join(lines), encoding="utf-8")
    print(OUT)
    for k, v in buckets.items():
        print(f"  {k}: {len(v)}")


if __name__ == "__main__":
    main()
