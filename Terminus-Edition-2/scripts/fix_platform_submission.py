#!/usr/bin/env python3
"""Platform submission fixes: offline deps in Dockerfile, not test.sh."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from audit_fix_task_toml_timeouts import fix_task_toml  # noqa: E402

PYTEST_INSTALL = (
    " && pip3 install --no-cache-dir --break-system-packages "
    "pytest==8.4.1 pytest-json-ctrf==0.3.5"
)
PIP_LINE = re.compile(
    r"\n\s*pip3 install --break-system-packages pytest==8\.4\.1 pytest-json-ctrf==0\.3\.5\s*\n"
)


def load_tasks(list_path: Path) -> list[str]:
    text = list_path.read_text(encoding="utf-8-sig")
    return [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]


def write_lf(path: Path, content: str) -> None:
    path.write_text(content.replace("\r\n", "\n"), encoding="utf-8", newline="\n")


def fix_dockerfile(path: Path) -> bool:
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    if "pytest==8.4.1" in text:
        return False
    if "python -m pip install" in text and "pytest==8.4.1" not in text:
        new = text.replace(
            "RUN python -m pip install --no-cache-dir pytest==8.4.1 pytest-json-ctrf==0.3.5",
            "RUN python -m pip install --no-cache-dir pytest==8.4.1 pytest-json-ctrf==0.3.5",
        )
        return False
    if "rm -rf /var/lib/apt/lists/*" in text and ("python3-pip" in text or "python3" in text):
        new = text.replace(
            "&& rm -rf /var/lib/apt/lists/*",
            PYTEST_INSTALL + " && rm -rf /var/lib/apt/lists/*",
            1,
        )
    elif "FROM python:" in text:
        insert = (
            "\nRUN python -m pip install --no-cache-dir "
            "pytest==8.4.1 pytest-json-ctrf==0.3.5\n"
        )
        if insert.strip() in text:
            return False
        m = re.search(r"(WORKDIR /app\n)", text)
        new = text[: m.end()] + insert + text[m.end() :] if m else text + insert
    else:
        return False
    if new != text:
        write_lf(path, new)
        return True
    return False


def fix_test_sh(path: Path, milestone: int) -> bool:
    if not path.is_file():
        return False
    test_file = f"test_m{milestone}.py"
    desired = f"""#!/bin/bash
set -uo pipefail
mkdir -p /logs/verifier
echo 0 > /logs/verifier/reward.txt

if [ "$PWD" = "/" ]; then
    echo "Error: No working directory set. Please set a WORKDIR in your Dockerfile."
    exit 1
fi

# Requires pytest-json-ctrf (installed in environment/Dockerfile)
python3 -m pytest --ctrf /logs/verifier/ctrf.json /tests/{test_file} -rA

if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi
"""
    current = path.read_text(encoding="utf-8")
    if PIP_LINE.search(current) or "pip3 install --break-system-packages pytest" in current:
        write_lf(path, desired)
        return True
    if "# Requires pytest-json-ctrf" not in current:
        new = current.replace(
            "python3 -m pytest",
            "# Requires pytest-json-ctrf (installed in environment/Dockerfile)\npython3 -m pytest",
            1,
        )
        if new != current:
            write_lf(path, new)
            return True
    return False


def fix_task(task_dir: Path) -> None:
    changes: list[str] = []
    docker = task_dir / "environment" / "Dockerfile"
    if fix_dockerfile(docker):
        changes.append("dockerfile")
    toml = task_dir / "task.toml"
    if toml.is_file():
        fixed, notes = fix_task_toml(toml)
        if fixed or notes:
            changes.append("task.toml")
    for m in range(1, 6):
        test_sh = task_dir / f"steps/milestone_{m}/tests/test.sh"
        if fix_test_sh(test_sh, m):
            changes.append(f"m{m} test.sh")
    print(f"{task_dir.name}: {', '.join(changes) if changes else 'ok'}")


def main() -> int:
    list_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "new_tasks.txt"
    for name in load_tasks(list_path):
        task_dir = ROOT / name
        if not task_dir.is_dir():
            print(f"skip missing {name}")
            continue
        fix_task(task_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
