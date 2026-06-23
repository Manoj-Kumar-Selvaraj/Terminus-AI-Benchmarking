#!/usr/bin/env python3
"""Apply universal revision fixes to all LOCAL_OK manifest task folders."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_fix_task_toml_timeouts import fix_task_toml  # noqa: E402
from fix_rubric_scores import fix_rubric  # noqa: E402
from revision_manifest_tasks import load_manifest  # noqa: E402
from revision_batch_orchestrator import fix_test_sh_exit_code, trim_tags  # noqa: E402


def unique_folders() -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for _, folder in load_manifest():
        if folder not in seen:
            seen.add(folder)
            out.append(folder)
    return sorted(out)


def main() -> int:
    folders = unique_folders()
    print(f"Fixing {len(folders)} tasks...")
    for folder in folders:
        td = ROOT / folder
        if not td.is_dir():
            print(f"MISSING {folder}")
            continue
        changes = []
        if fix_task_toml(td / "task.toml"):
            changes.append("task.toml")
        n = fix_test_sh_exit_code(td)
        if n:
            changes.append(f"test.sh x{n}")
        if trim_tags(td):
            changes.append("tags")
        rp = td / "rubric.txt"
        if rp.is_file() and fix_rubric(rp):
            changes.append("rubric")
        if changes:
            print(f"{folder}: {', '.join(changes)}")
    # golang dockerfile batch
    subprocess.run([sys.executable, str(ROOT / "scripts" / "convert_go_dockerfile_golang_base.py")], check=False)
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
