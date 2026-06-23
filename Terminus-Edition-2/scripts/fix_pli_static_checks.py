#!/usr/bin/env python3
"""Apply Edition 2 static-check fixes to all pli-* Harbor tasks."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

DOCKERIGNORE = """out/
build/
.git
.gitignore
**/__pycache__/
**/*.pyc
**/.pytest_cache/
**/.mypy_cache/
**/.ruff_cache/
**/node_modules/
"""

TEST_SH_TEMPLATE = """#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile."
    exit 1
fi

python3 -m pytest --ctrf /logs/verifier/ctrf.json /tests/{test_file} -rA

if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
"""


def pli_tasks() -> list[Path]:
    return sorted(p for p in ROOT.glob("pli-*") if p.is_dir() and (p / "task.toml").is_file())


def fix_test_sh(task: Path) -> int:
    changed = 0
    for milestone in sorted((task / "steps").glob("milestone_*")):
        test_sh = milestone / "tests" / "test.sh"
        if not test_sh.is_file():
            continue
        text = test_sh.read_text(encoding="utf-8")
        match = re.search(r"/tests/(test_m\d+\.py)", text)
        if not match:
            print(f"  skip {test_sh.relative_to(ROOT)} (no test file in pytest line)")
            continue
        new_text = TEST_SH_TEMPLATE.format(test_file=match.group(1))
        if text != new_text:
            test_sh.write_text(new_text, encoding="utf-8", newline="\n")
            changed += 1
    return changed


def fix_python(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    text = text.replace("import csv, subprocess", "import csv\nimport subprocess")
    text = re.sub(
        r"\(l\.split\(\"=\",1\) for l in",
        "(line.split(\"=\", 1) for line in",
        text,
    )
    if text != original:
        path.write_text(text, encoding="utf-8", newline="\n")
        return True
    return False


def ruff_fix(paths: list[Path]) -> None:
    if not paths:
        return
    subprocess.run(
        [sys.executable, "-m", "ruff", "check", "--fix", *[str(p) for p in paths]],
        cwd=ROOT,
        check=False,
    )


def ruff_check(paths: list[Path]) -> list[str]:
    if not paths:
        return []
    proc = subprocess.run(
        [sys.executable, "-m", "ruff", "check", *[str(p) for p in paths]],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    if proc.returncode == 0:
        return []
    return [line for line in proc.stdout.splitlines() if line.strip()]


def fix_dockerignore(task: Path) -> bool:
    path = task / "environment" / ".dockerignore"
    if not path.parent.is_dir():
        return False
    if path.read_text(encoding="utf-8") == DOCKERIGNORE:
        return False
    path.write_text(DOCKERIGNORE, encoding="utf-8", newline="\n")
    return True


def main() -> int:
    tasks = pli_tasks()
    print(f"Found {len(tasks)} pli-* tasks")
    py_paths: list[Path] = []
    failures: dict[str, list[str]] = {}

    for task in tasks:
        name = task.name
        print(f"\n=== {name} ===")
        sh_changed = fix_test_sh(task)
        print(f"  test.sh updated: {sh_changed}")
        if fix_dockerignore(task):
            print("  .dockerignore updated")

        task_py = sorted(task.glob("steps/milestone_*/tests/test_m*.py"))
        for py in task_py:
            if fix_python(py):
                print(f"  pre-ruff fix: {py.relative_to(ROOT)}")
        py_paths.extend(task_py)

    print("\n=== ruff --fix (all pli test files) ===")
    ruff_fix(py_paths)

    print("\n=== ruff verify ===")
    for task in tasks:
        task_py = sorted(task.glob("steps/milestone_*/tests/test_m*.py"))
        errors = ruff_check(task_py)
        if errors:
            failures[task.name] = errors
            print(f"FAIL {task.name}: {len(errors)} ruff issue(s)")
            for err in errors[:5]:
                print(f"  {err}")
        else:
            print(f"OK   {task.name}")

    if failures:
        print(f"\n{len(failures)} task(s) still have ruff errors", file=sys.stderr)
        return 1
    print("\nAll pli-* tasks pass ruff on verifier tests.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
