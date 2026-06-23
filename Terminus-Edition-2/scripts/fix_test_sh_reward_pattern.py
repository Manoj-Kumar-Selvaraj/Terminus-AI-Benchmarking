#!/usr/bin/env python3
"""Fix test.sh to platform-compliant reward pattern (pytest + if [ $? -eq 0 ])."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TEMPLATE = """#!/bin/bash
# Omit -e so pytest failures reach the reward if/else block below.
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile."
    exit 1
fi

python3 -m pytest --ctrf /logs/verifier/ctrf.json /tests/test_m{M}.py -rA

if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
"""


def fix_task(task_dir: Path) -> int:
    n = 0
    for m in range(1, 20):
        p = task_dir / f"steps/milestone_{m}/tests/test.sh"
        if not p.is_file():
            break
        py = list((task_dir / f"steps/milestone_{m}/tests").glob("test_m*.py"))
        rb = list((task_dir / f"steps/milestone_{m}/tests").glob("test_m*.rb"))
        if py:
            test_file = py[0].name
        elif rb:
            # ruby tasks may use different runner; keep existing if rb-only
            continue
        else:
            continue
        mnum = re.search(r"test_m(\d+)", test_file)
        if not mnum:
            continue
        content = TEMPLATE.format(M=mnum.group(1))
        if p.read_text(encoding="utf-8") != content:
            p.write_bytes(content.encode("utf-8"))
            n += 1
    return n


def main() -> None:
    lists = [ROOT / "batch10_tasks.txt", ROOT / "batch11_tasks.txt"]
    tasks: list[str] = []
    for lst in lists:
        if lst.is_file():
            tasks.extend(
                line.strip()
                for line in lst.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")
            )
    if not tasks:
        tasks = [sys.argv[1]] if len(sys.argv) > 1 else []
    total = 0
    for task in tasks:
        td = ROOT / task
        if not td.is_dir():
            print(f"skip {task} (missing)")
            continue
        n = fix_task(td)
        if n:
            print(f"{task}: fixed {n} test.sh")
            total += n
    print(f"done, {total} files updated")


if __name__ == "__main__":
    main()
