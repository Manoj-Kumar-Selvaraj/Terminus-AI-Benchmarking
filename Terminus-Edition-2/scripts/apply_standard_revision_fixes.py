#!/usr/bin/env python3
"""Apply standard revision fixes: test.sh reward pattern, build_timeout 1200, Dockerfile merge pip."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TEST_SH = """#!/bin/bash
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


def fix_test_sh(task_dir: Path) -> int:
    n = 0
    for m in range(1, 20):
        p = task_dir / f"steps/milestone_{m}/tests/test.sh"
        if not p.is_file():
            break
        py = list((task_dir / f"steps/milestone_{m}/tests").glob("test_m*.py"))
        if not py:
            continue
        test_file = py[0].name
        mnum = re.search(r"test_m(\d+)", test_file)
        if not mnum:
            continue
        content = TEST_SH.format(M=mnum.group(1))
        if p.read_text(encoding="utf-8") != content:
            p.write_bytes(content.encode("utf-8"))
            n += 1
    return n


def fix_task_toml(task_dir: Path) -> bool:
    p = task_dir / "task.toml"
    if not p.is_file():
        return False
    text = p.read_text(encoding="utf-8")
    new = re.sub(
        r"build_timeout_sec\s*=\s*900\.0",
        "build_timeout_sec = 1200.0",
        text,
    )
    if new != text:
        p.write_text(new, encoding="utf-8")
        return True
    return False


def fix_dockerfile(task_dir: Path) -> bool:
    p = task_dir / "environment/Dockerfile"
    if not p.is_file():
        return False
    text = p.read_text(encoding="utf-8")
    if "pip3 install" in text and text.count("RUN ") >= 2:
        # merge separate pip RUN into prior apt RUN when possible
        lines = text.splitlines()
        out: list[str] = []
        i = 0
        changed = False
        while i < len(lines):
            line = lines[i]
            if (
                line.strip().startswith("RUN apt-get")
                and i + 2 < len(lines)
                and lines[i + 1].strip() == ""
                and "pip3 install" in lines[i + 2]
            ):
                apt_block = [line]
                j = i + 1
                while j < len(lines) and (lines[j].strip().startswith("&&") or lines[j].strip().endswith("\\")):
                    apt_block.append(lines[j])
                    j += 1
                pip_line = lines[j].strip()
                if pip_line.startswith("RUN pip3"):
                    pip_cmd = pip_line.replace("RUN ", "").strip()
                    # insert pip before rm -rf
                    merged = []
                    inserted = False
                    for ab in apt_block:
                        if "rm -rf /var/lib/apt/lists" in ab and not inserted:
                            merged.append(f"    && {pip_cmd} \\")
                            inserted = True
                        merged.append(ab)
                    if not inserted:
                        merged.append(f"    && {pip_cmd} \\")
                        merged.append("    && rm -rf /var/lib/apt/lists/*")
                    out.extend(merged)
                    i = j + 1
                    changed = True
                    continue
            out.append(line)
            i += 1
        if changed:
            p.write_text("\n".join(out) + "\n", encoding="utf-8")
            return True
    return False


def fix_task(name: str) -> dict:
    task_dir = ROOT / name
    if not task_dir.is_dir():
        return {"task": name, "error": "missing"}
    return {
        "task": name,
        "test_sh": fix_test_sh(task_dir),
        "toml": fix_task_toml(task_dir),
        "dockerfile": fix_dockerfile(task_dir),
    }


def main() -> int:
    tasks = [ln.strip() for ln in Path(sys.argv[1]).read_text(encoding="utf-8-sig").splitlines() if ln.strip() and not ln.startswith("#")]
    for r in fix_task(t) if False else [fix_task(t) for t in tasks]:
        print(r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
