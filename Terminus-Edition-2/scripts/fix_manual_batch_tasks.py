#!/usr/bin/env python3
"""Apply common hygiene fixes to manual_revision_batch_20260612 tasks only."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from audit_fix_task_toml_timeouts import fix_task_toml  # noqa: E402
from fix_custom_revisions_batch import (  # noqa: E402
    add_pwd_guard,
    bump_go_build_timeout,
    ensure_rubric_agent_prefix,
    fix_test_sh_exit_code,
    strip_tool_specific,
    trim_tags,
)
from fix_rubric_scores import fix_rubric  # noqa: E402

MAP = ROOT / "Revision-ChatGpt/manual_revision_batch_20260612/submission_mapping.tsv"


def load_tasks() -> list[str]:
    tasks: list[str] = []
    for line in MAP.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("submission_id"):
            continue
        parts = line.split("\t")
        if len(parts) >= 2:
            tasks.append(parts[1].strip())
    return tasks


def main() -> int:
    for folder in load_tasks():
        td = ROOT / folder
        if not td.is_dir():
            print(f"MISSING: {folder}")
            continue
        changes: list[str] = []
        toml = td / "task.toml"
        if toml.is_file():
            if strip_tool_specific(toml):
                changes.append("removed tool_specific")
            if bump_go_build_timeout(toml):
                changes.append("build_timeout 1200")
            if fix_task_toml(toml):
                changes.append("task.toml")
        n = fix_test_sh_exit_code(td)
        if n:
            changes.append(f"test.sh x{n}")
        pwd_n = sum(1 for ts in td.rglob("tests/test.sh") if add_pwd_guard(ts))
        if pwd_n:
            changes.append(f"pwd_guard x{pwd_n}")
        if trim_tags(td):
            changes.append("tags")
        rp = td / "rubric.txt"
        if rp.is_file():
            if fix_rubric(rp):
                changes.append("rubric scores")
            if ensure_rubric_agent_prefix(rp):
                changes.append("rubric Agent prefix")
            custom = ROOT / "revision-custom-rubrics" / f"{folder}.rubric.txt"
            custom.parent.mkdir(parents=True, exist_ok=True)
            custom.write_text(rp.read_text(encoding="utf-8"), encoding="utf-8")
            changes.append("sync rubric copy")
        if changes:
            print(f"{folder}: {', '.join(changes)}")
        else:
            print(f"{folder}: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
