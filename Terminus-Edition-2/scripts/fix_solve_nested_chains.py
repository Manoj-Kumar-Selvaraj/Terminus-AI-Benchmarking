#!/usr/bin/env python3
"""Remove redundant prior-milestone bash calls from solve{N}.sh when solve.sh chains them."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from fix_custom_revisions_batch import all_tasks  # noqa: E402

BASH_SOLVE = re.compile(r"^\s*bash\s+(.+solve(\d+)\.sh.*)$", re.MULTILINE)


def milestone_count(toml: Path) -> int:
    for line in toml.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("number_of_milestones"):
            return int(re.search(r"\d+", line).group())
    return 0


def strip_prior_calls(text: str, milestone: int) -> tuple[str, int]:
    removed = 0

    def drop(match: re.Match[str]) -> str:
        nonlocal removed
        prior = int(match.group(2))
        if prior < milestone:
            removed += 1
            return ""
        return match.group(0)

    text = BASH_SOLVE.sub(drop, text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text, removed


def fix_logistics_solve3(task_dir: Path) -> bool:
    solve3 = task_dir / "steps" / "milestone_3" / "solution" / "solve3.sh"
    if not solve3.is_file():
        return False
    body = solve3.read_text(encoding="utf-8")
    if "python3" in body or "cat >" in body or "main.go" in body:
        return False
    solve3.write_text(
        """#!/usr/bin/env bash
set -euo pipefail
# Milestone 3 date rules are implemented in milestone_2/solve2.sh; solve.sh chains prior milestones.
/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
""",
        encoding="utf-8",
    )
    return True


def main() -> int:
    changed: list[str] = []
    for folder in all_tasks():
        td = ROOT / folder
        toml = td / "task.toml"
        if not toml.is_file():
            continue
        n = milestone_count(toml)
        task_changes = 0
        for m in range(2, n + 1):
            solve_n = td / "steps" / f"milestone_{m}" / "solution" / f"solve{m}.sh"
            if not solve_n.is_file():
                continue
            text = solve_n.read_text(encoding="utf-8")
            new_text, removed = strip_prior_calls(text, m)
            if removed and new_text != text:
                solve_n.write_text(new_text, encoding="utf-8")
                task_changes += removed
        if folder == "go-logistics-accessorial-credit-matcher" and fix_logistics_solve3(td):
            task_changes += 1
        if task_changes:
            changed.append(f"{folder} ({task_changes})")
    for line in changed:
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
