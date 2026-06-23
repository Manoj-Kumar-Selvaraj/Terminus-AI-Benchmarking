#!/usr/bin/env python3
"""Audit batch tasks for common platform/oracle failure patterns."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REWARD_OK = """if [ $? -eq 0 ]; then
    echo 1 > /logs/verifier/reward.txt
else
    echo 0 > /logs/verifier/reward.txt
fi"""

TEST_SH_HEAD = "set -uo pipefail"


def load_tasks(path: Path) -> list[str]:
    return [
        ln.strip()
        for ln in path.read_text(encoding="utf-8-sig").splitlines()
        if ln.strip() and not ln.startswith("#")
    ]


def audit_task(name: str) -> dict:
    td = ROOT / name
    issues: list[str] = []
    if not td.is_dir():
        return {"task": name, "issues": ["missing folder"]}

    toml = (td / "task.toml").read_text(encoding="utf-8") if (td / "task.toml").is_file() else ""
    if not re.search(r"\[agent\]", toml):
        issues.append("missing root [agent]")
    if not re.search(r"\[verifier\]", toml):
        issues.append("missing root [verifier]")
    bt = re.search(r"build_timeout_sec\s*=\s*(\S+)", toml)
    if not bt:
        issues.append("missing build_timeout_sec")
    elif bt.group(1) not in ("1200", "1200.0"):
        issues.append(f"build_timeout_sec={bt.group(1)} (want 1200)")

    df = td / "environment/Dockerfile"
    if df.is_file():
        dft = df.read_text(encoding="utf-8")
        if "/opt/verifier" in dft and "pip3 install --break-system-packages" not in dft:
            issues.append("Dockerfile venv-only pytest (breaks python3 -m pytest)")
        if "pip3 install" not in dft and "pytest" not in dft:
            issues.append("Dockerfile may missing pytest")

    for py in td.glob("scripts/*.py"):
        issues.append(f"debug script in task root: {py.name}")

    for m in range(1, 20):
        ts = td / f"steps/milestone_{m}/tests/test.sh"
        if not ts.is_file():
            break
        t = ts.read_text(encoding="utf-8")
        if "if python3 -m pytest" in t and "then" in t.split("pytest")[1][:80]:
            issues.append(f"M{m} test.sh uses if pytest; then (platform reject)")
        if TEST_SH_HEAD not in t:
            issues.append(f"M{m} test.sh missing set -uo pipefail")
        if REWARD_OK not in t and "if [ $? -eq 0 ]" not in t:
            issues.append(f"M{m} test.sh bad reward block")

    return {"task": name, "issues": issues}


def main() -> None:
    tasks = load_tasks(ROOT / "batch10_tasks.txt") + load_tasks(ROOT / "batch11_tasks.txt")
    # dedupe
    seen: set[str] = set()
    unique = []
    for t in tasks:
        if t not in seen:
            seen.add(t)
            unique.append(t)

    clean, dirty = [], []
    for t in unique:
        r = audit_task(t)
        if r["issues"]:
            dirty.append(r)
        else:
            clean.append(t)

    print("=== CLEAN (local structural audit) ===")
    for t in clean:
        print(t)
    print(f"\nTotal clean: {len(clean)}")
    print("\n=== ISSUES ===")
    for r in dirty:
        print(f"{r['task']}: {', '.join(r['issues'])}")


if __name__ == "__main__":
    main()
