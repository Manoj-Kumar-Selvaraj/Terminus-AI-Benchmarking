#!/usr/bin/env python3
"""Chain milestone solve.sh scripts through prior milestones for revision-queue Go tasks."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from fix_custom_revisions_batch import all_tasks  # noqa: E402

CHAIN_HEADER = '''#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TASK_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
'''

SKIP_CROSS = {"solve1.sh"}  # only delete solve1 from M2+; keep solveN.sh in own milestone


def fix_milestone(task_dir: Path, m: int) -> list[str]:
    changes: list[str] = []
    if m < 2:
        return changes
    solve_sh = task_dir / "steps" / f"milestone_{m}" / "solution" / "solve.sh"
    solve_n = task_dir / "steps" / f"milestone_{m}" / "solution" / f"solve{m}.sh"
    if not solve_sh.is_file() or not solve_n.is_file():
        return changes

    # Remove duplicate prior-milestone solve copies from this milestone folder
    sol_dir = solve_sh.parent
    for prior in range(1, m):
        dup = sol_dir / f"solve{prior}.sh"
        if dup.is_file():
            dup.unlink()
            changes.append(f"deleted {dup.relative_to(task_dir)}")

    lines = [CHAIN_HEADER.rstrip()]
    for prior in range(1, m):
        lines.append(f'bash "$TASK_ROOT/milestone_{prior}/solution/solve{prior}.sh"')
    lines.append(f'bash "$SCRIPT_DIR/solve{m}.sh"')
    lines.append("")
    new_text = "\n".join(lines)
    old = solve_sh.read_text(encoding="utf-8")
    if old != new_text:
        solve_sh.write_text(new_text, encoding="utf-8")
        changes.append(f"chained milestone_{m}/solution/solve.sh")
    return changes


def main() -> int:
    for folder in all_tasks():
        if not folder.startswith("go-"):
            continue
        td = ROOT / folder
        if not td.is_dir():
            continue
        toml = td / "task.toml"
        if not toml.is_file():
            continue
        m = 0
        for line in toml.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("number_of_milestones"):
                m = int(re.search(r"\d+", line).group())
                break
        if m < 2:
            continue
        all_changes: list[str] = []
        for mi in range(2, m + 1):
            all_changes.extend(fix_milestone(td, mi))
        if all_changes:
            print(f"{folder}: {', '.join(all_changes)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
