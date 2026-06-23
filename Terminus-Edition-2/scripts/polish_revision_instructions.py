#!/usr/bin/env python3
"""Polish milestone instructions for revision-batch tasks."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from fix_custom_revisions_batch import all_tasks  # noqa: E402

VERIFIER_CLI = re.compile(
    r"\s*Keep the deliverable as a Go CLI: the verifier compiles[^.\n]*(?:\.[^\n]*)?\.\s*",
    re.IGNORECASE,
)
VERIFIER_MAY = re.compile(r"\b[Tt]he verifier may\b", re.IGNORECASE)
FOR_MILESTONE = re.compile(r"\bFor this milestone,\s*", re.IGNORECASE)


def polish_file(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    text = VERIFIER_CLI.sub(" ", text)
    text = VERIFIER_MAY.sub("The input files may", text)
    text = FOR_MILESTONE.sub("", text)
    text = re.sub(r"  +", " ", text)
    text = re.sub(r" \n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip() + "\n"
    if text != original:
        path.write_text(text, encoding="utf-8")
        return True
    return False


def main() -> int:
    changed = 0
    for folder in all_tasks():
        steps = ROOT / folder / "steps"
        if not steps.is_dir():
            continue
        for inst in steps.glob("milestone_*/instruction.md"):
            if polish_file(inst):
                changed += 1
                print(f"polished {inst.relative_to(ROOT)}")
    print(f"done: {changed} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
