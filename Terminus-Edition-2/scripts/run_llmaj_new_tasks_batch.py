#!/usr/bin/env python3
"""Run strict LLMaJ on every task listed in new_tasks.txt."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIST = ROOT / "new_tasks.txt"
LOG = ROOT / ".terminus_logs" / "llmaj_new_tasks_batch.log"


def main() -> int:
    tasks = [
        line.strip()
        for line in LIST.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    LOG.parent.mkdir(parents=True, exist_ok=True)
    failed: list[str] = []
    with LOG.open("w", encoding="utf-8") as log:
        for task in tasks:
            log.write(f"========== {task} ==========\n")
            log.flush()
            proc = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "run_llmaj_litellm.py"), task, "--strict"],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            log.write(proc.stdout)
            log.write(proc.stderr)
            log.write(f"\nexit={proc.returncode}\n\n")
            log.flush()
            if proc.returncode != 0:
                failed.append(task)
            print(f"{task}: {'FAIL' if proc.returncode else 'PASS'}", flush=True)
    summary = LOG.with_name("llmaj_new_tasks_batch_summary.txt")
    summary.write_text(
        f"Total: {len(tasks)}\nPassed: {len(tasks) - len(failed)}\nFailed: {len(failed)}\n"
        + ("Failed tasks:\n" + "\n".join(failed) + "\n" if failed else ""),
        encoding="utf-8",
    )
    print(f"Summary: {summary}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
