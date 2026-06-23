#!/usr/bin/env python3
"""Triage fresh STB feedback for manual revision batch."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAP = ROOT / "Revision-ChatGpt/manual_revision_batch_20260612/submission_mapping.tsv"
ARCHIVE = ROOT / "Revision-ChatGpt/portal_feedback"
OUT = ROOT / "revision-manual-batch-20260612/stb_triage.md"


def load_map() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for line in MAP.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("submission_id"):
            continue
        sid, folder = line.split("\t", 1)
        rows.append((sid.strip(), folder.strip()))
    return rows


def extract_section(text: str, label: str) -> str:
    pat = rf"{re.escape(label)}\s*\n-+\s*\n(.*?)(?:\n\n|\n[A-Z][a-z].*\n-+\s*\n|\Z)"
    m = re.search(pat, text, re.S)
    return m.group(1).strip() if m else ""


def count_warnings(agent_review: str) -> int:
    m = re.search(r"WARNINGS.*?(\d+)", agent_review, re.S | re.I)
    if m:
        return int(m.group(1))
    return agent_review.lower().count("warning")


def main() -> int:
    lines = ["# STB Fresh Feedback Triage\n"]
    for sid, folder in load_map():
        dest = ARCHIVE / f"audit_{sid}"
        notes = dest / "notes.txt"
        agent = dest / "agent_review.txt"
        lines.append(f"## {folder}\n")
        lines.append(f"- Submission: `{sid}`\n")
        if not notes.is_file():
            lines.append("- **MISSING fresh feedback**\n")
            continue
        nt = notes.read_text(encoding="utf-8", errors="replace")
        ar = agent.read_text(encoding="utf-8", errors="replace") if agent.is_file() else ""
        diff = re.search(r"Difficulty:\s*([^\n]+)", nt)
        instr = re.search(r"instruction sufficiency:\s*([^\n]+)", nt, re.I)
        solvable = re.search(r"Status:\s*([^\n]+)", nt)
        autobuild = re.search(r"Build status:\s*(\w+)", nt)
        fails = re.findall(r"❌\s*fail\s*-\s*([^:\n]+)", nt, re.I)
        warns = []
        for m in re.finditer(r"^##?\s*(\d+\.\s*.+)$", ar, re.M):
            warns.append(m.group(1).strip())
        if not warns:
            for m in re.finditer(r"^##\s+(.+)$", ar, re.M):
                if "WARNING" not in m.group(1).upper() and "SUGGESTION" not in m.group(1).upper():
                    warns.append(m.group(1).strip())
        lines.append(f"- Difficulty: {diff.group(1).strip() if diff else 'unknown'}\n")
        lines.append(f"- Solvable: {solvable.group(1).strip() if solvable else 'unknown'}\n")
        lines.append(f"- AutoEval build: {autobuild.group(1) if autobuild else 'unknown'}\n")
        if instr:
            lines.append(f"- Instruction sufficiency: {instr.group(1).strip()}\n")
        if fails:
            lines.append("- Quality fails:\n")
            for f in fails:
                lines.append(f"  - {f.strip()}\n")
        if warns:
            lines.append("- Agent review issues:\n")
            for w in warns[:8]:
                lines.append(f"  - {w}\n")
        lines.append("\n")
    OUT.write_text("".join(lines), encoding="utf-8")
    print(f"Wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
