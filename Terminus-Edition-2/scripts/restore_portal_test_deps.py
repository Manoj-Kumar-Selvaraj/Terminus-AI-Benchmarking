#!/usr/bin/env python3
"""Restore verifier dependencies to Dockerfiles for portal-standard task images."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTEST_INSTALL = "RUN pip3 install --break-system-packages pytest==8.4.1 pytest-json-ctrf==0.3.5"


def load_tasks(list_path: Path) -> list[str]:
    text = list_path.read_text(encoding="utf-8-sig")
    return [line.strip() for line in text.splitlines() if line.strip() and not line.strip().startswith("#")]


def write_lf(path: Path, content: str) -> None:
    path.write_text(content.replace("\r\n", "\n"), encoding="utf-8", newline="\n")


def restore_dockerfile(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text

    if "apt-get install" in text and "rm -rf /var/lib/apt/lists/*" not in text:
        text = re.sub(
            r"(\s*&& apt-get install -y --no-install-recommends [^\n]+)\\\n\s*\n",
            r"\1\\\n    && rm -rf /var/lib/apt/lists/*\n\n",
            text,
            count=1,
        )

    if "pytest==8.4.1" not in text:
        text = text.replace("\nCOPY ", f"\n{PYTEST_INSTALL}\n\nCOPY ", 1)

    if text != original:
        write_lf(path, text)
        return True
    return False


def restore_test_sh(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    original = text
    lines = [line for line in text.splitlines() if "pip3 install --break-system-packages pytest" not in line]
    text = "\n".join(lines) + "\n"
    text = re.sub(r"\n{3,}", "\n\n", text)
    if text != original:
        write_lf(path, text)
        return True
    return False


def restore_task(task_dir: Path) -> tuple[bool, bool]:
    docker_changed = False
    test_changed = False
    dockerfile = task_dir / "environment" / "Dockerfile"
    if dockerfile.is_file():
        docker_changed = restore_dockerfile(dockerfile)
    for test_sh in task_dir.glob("steps/milestone_*/tests/test.sh"):
        if restore_test_sh(test_sh):
            test_changed = True
    return docker_changed, test_changed


def main() -> int:
    list_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "new_tasks.txt"
    for task_name in load_tasks(list_path):
        task_dir = ROOT / task_name
        if not task_dir.is_dir():
            print(f"skip missing {task_name}")
            continue
        docker_changed, test_changed = restore_task(task_dir)
        print(f"{task_name}: dockerfile={docker_changed} test.sh={test_changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
