#!/usr/bin/env python3
"""Fix rubric.txt invalid scores (+4/+6 -> valid ±1,±2,±3,±5) and test/solution refs."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VALID = {1, 2, 3, 5}


def normalize_score(n: int) -> int:
    if n in VALID:
        return n
    if n == 4:
        return 3
    if n == 6:
        return 5
    if n == 0:
        return 1
    # clamp other invalid positives to nearest valid
    for v in (5, 3, 2, 1):
        if n >= v:
            return v
    return 1


def fix_line(line: str) -> str:
    m = re.match(r"^(.+),\s*([+-])(\d+)\s*$", line.rstrip())
    if not m:
        return line.rstrip()
    body, sign, num = m.group(1), m.group(2), int(m.group(3))
    new_num = normalize_score(num)
    # soften test/solution references
    body = re.sub(r"\btests?\b", "verifier behavior", body, flags=re.I)
    body = re.sub(r"\bsolution/[^\s,]+", "reference implementation paths", body, flags=re.I)
    body = re.sub(r"\btest_m\d+\.py\b", "verifier checks", body, flags=re.I)
    body = re.sub(r"\btest suite\b", "verifier coverage", body, flags=re.I)
    body = re.sub(r"\bmilestone \d+ tests\b", "milestone verifier checks", body, flags=re.I)
    return f"{body}, {sign}{new_num}"


def fix_rubric(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    new_lines = [fix_line(ln) if ln.strip() and not ln.startswith("#") else ln.rstrip() for ln in lines]
    new_text = "\n".join(new_lines).rstrip() + "\n"
    if new_text != text.replace("\r\n", "\n"):
        path.write_text(new_text, encoding="utf-8", newline="\n")
        return True
    return False


def main() -> int:
    folders = sys.argv[1:] if len(sys.argv) > 1 else [p.parent.name for p in ROOT.glob("*/rubric.txt")]
    n = 0
    for folder in folders:
        p = ROOT / folder / "rubric.txt"
        if p.is_file() and fix_rubric(p):
            print(f"fixed rubric: {folder}")
            n += 1
    print(f"updated {n} rubrics")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
