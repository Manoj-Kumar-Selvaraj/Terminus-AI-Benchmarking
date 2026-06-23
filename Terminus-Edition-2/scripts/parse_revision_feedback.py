#!/usr/bin/env python3
"""Parse portal feedback for all LOCAL_OK manifest tasks -> TSV report."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "Revision-ChatGpt" / "needs_revision_pulls" / "portal_ids_manifest.tsv"
FB = ROOT / "Revision-ChatGpt" / "portal_feedback"
OUT = ROOT / "Revision-ChatGpt" / "revision_feedback_parsed.tsv"


def load_rows() -> list[tuple[str, str]]:
    seen: set[str] = set()
    rows: list[tuple[str, str]] = []
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        sid, folder, status = line.split("\t")
        if status != "LOCAL_OK" or folder in seen:
            continue
        seen.add(folder)
        rows.append((sid, folder))
    return sorted(rows, key=lambda x: x[1])


def find_notes(sid: str) -> tuple[str, Path | None]:
    for p in sorted(FB.glob(f"audit_{sid}*")) + sorted(FB.glob(f"full_feedback_{sid}*")):
        n = p / "notes.txt"
        if n.is_file():
            return n.read_text(encoding="utf-8", errors="replace"), p
    return "", None


def count_agent(path: Path | None, kind: str) -> int:
    if not path:
        return 0
    ar = path / "agent_review.txt"
    if not ar.is_file():
        return 0
    text = ar.read_text(encoding="utf-8", errors="replace").upper()
    if kind == "warning":
        return text.count("WARNING") + text.count("⚠")
    if kind == "critical":
        return text.count("CRITICAL") + text.count("🔴")
    if kind == "suggestion":
        return text.count("SUGGESTION") + text.count("💡")
    return 0


def main() -> None:
    lines = [
        "folder\tsubmission_id\tfeedback\tautoeval_fail\tdifficulty\tquality_fails\tinstr\tagent_w\tagent_c\tagent_s\trevision_notes_snip"
    ]
    for sid, folder in load_rows():
        notes, fbdir = find_notes(sid)
        if not notes:
            lines.append(f"{folder}\t{sid}\tMISSING\t\t\t\t\t\t\t\t")
            continue
        diff = ""
        m = re.search(r"Difficulty:\s*(.+)", notes)
        if m:
            diff = m.group(1).strip()
        ae = "yes" if "Build status: FAILED" in notes else "no"
        qf = sum(1 for ln in notes.splitlines() if ln.strip().startswith("❌"))
        instr = ""
        m = re.search(r"Task Instruction Sufficiency:\s*(.+)", notes)
        if m:
            instr = m.group(1).strip()[:80]
        rn = ""
        m = re.search(r"Revision Notes\s*-+\s*(.*?)(?=\n(?:Rebuttal|Summary|Quality|Agent|\Z))", notes, re.S)
        if m:
            rn = re.sub(r"\s+", " ", m.group(1).strip())[:120]
        lines.append(
            f"{folder}\t{sid}\tOK\t{ae}\t{diff}\t{qf}\t{instr}\t"
            f"{count_agent(fbdir,'warning')}\t{count_agent(fbdir,'critical')}\t{count_agent(fbdir,'suggestion')}\t{rn}"
        )
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {OUT} ({len(lines)-1} rows)")


if __name__ == "__main__":
    main()
