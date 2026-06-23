#!/usr/bin/env python3
"""Move pytest from Dockerfile to test.sh for LLMaJ test_deps_in_image compliance."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TEST_SH_TEMPLATE = """#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile."
    exit 1
fi

pip3 install --break-system-packages pytest==8.4.1 pytest-json-ctrf==0.3.5

python3 -m pytest --ctrf /logs/verifier/ctrf.json /tests/{test_file} -rA

if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
"""

PYTEST_LINE = re.compile(
    r"\s*&& pip3 install --break-system-packages pytest==8\.4\.1 pytest-json-ctrf==0\.3\.5 \\\n",
    re.MULTILINE,
)
PYTEST_LINE_ALT = re.compile(
    r"\s*&& pip3 install --break-system-packages pytest==8\.4\.1 pytest-json-ctrf==0\.3\.5\s*\n",
    re.MULTILINE,
)


def load_tasks(list_path: Path) -> list[str]:
    text = list_path.read_text(encoding="utf-8-sig")
    return [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]


def write_lf(path: Path, content: str) -> None:
    path.write_text(content.replace("\r\n", "\n"), encoding="utf-8", newline="\n")


def fix_dockerfile(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    new_text, n = PYTEST_LINE.subn("\n", text)
    if n == 0:
        new_text, n = PYTEST_LINE_ALT.subn("\n", new_text)
    if n == 0 and "pytest==8.4.1" not in text:
        return False
    if n == 0:
        # fallback: strip any pytest pip line
        lines = [ln for ln in text.splitlines() if "pytest==8.4.1" not in ln]
        new_text = "\n".join(lines) + ("\n" if text.endswith("\n") else "")
    if new_text != text:
        write_lf(path, new_text)
        return True
    return False


def fix_test_sh(path: Path, milestone: int) -> bool:
    test_file = f"test_m{milestone}.py"
    desired = TEST_SH_TEMPLATE.format(test_file=test_file)
    current = path.read_text(encoding="utf-8") if path.is_file() else ""
    if "pip3 install --break-system-packages pytest" in current and "PWD" in current:
        return False
    write_lf(path, desired)
    return True


def fix_task(task_dir: Path) -> tuple[bool, bool]:
    docker_changed = False
    test_changed = False
    docker = task_dir / "environment" / "Dockerfile"
    if docker.is_file():
        docker_changed = fix_dockerfile(docker)
    for m in range(1, 6):
        test_sh = task_dir / f"steps/milestone_{m}/tests/test.sh"
        if test_sh.is_file():
            if fix_test_sh(test_sh, m):
                test_changed = True
    return docker_changed, test_changed


def main() -> int:
    list_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "new_tasks.txt"
    tasks = load_tasks(list_path)
    for name in tasks:
        task_dir = ROOT / name
        if not task_dir.is_dir():
            print(f"skip missing {name}")
            continue
        d, t = fix_task(task_dir)
        if d or t:
            print(f"fixed {name}: dockerfile={d} test.sh={t}")
        else:
            print(f"ok {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
