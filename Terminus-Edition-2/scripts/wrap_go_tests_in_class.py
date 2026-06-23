#!/usr/bin/env python3
"""Wrap top-level test_* functions in a pytest class."""
from __future__ import annotations

import re
import sys
from pathlib import Path


def wrap_file(path: Path, class_name: str) -> bool:
    text = path.read_text(encoding="utf-8")
    if f"class {class_name}" in text:
        return False
    lines = text.splitlines()
    out: list[str] = []
    in_tests = False
    for line in lines:
        if re.match(r"^def test_", line):
            if not in_tests:
                out.append("")
                out.append(f"class {class_name}:")
                in_tests = True
            out.append("    " + line)
        elif in_tests and line and not line[0].isspace() and not line.startswith("#"):
            in_tests = False
            out.append(line)
        elif in_tests and line:
            out.append("    " + line if line.strip() else line)
        else:
            out.append(line)
    new = "\n".join(out).rstrip() + "\n"
    if new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: wrap_go_tests_in_class.py <class_name> <test.py> ...")
        return 1
    class_name = sys.argv[1]
    changed = 0
    for arg in sys.argv[2:]:
        if wrap_file(Path(arg), class_name):
            changed += 1
            print(f"wrapped {arg}")
    print(f"done: {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
