#!/usr/bin/env python3
"""Check whether a revised task has the usual completion artifacts."""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path


def fail(messages: list[str], message: str) -> None:
    messages.append(f"FAIL: {message}")


def ok(messages: list[str], message: str) -> None:
    messages.append(f"OK: {message}")


def newest_oracle_log(log_dir: Path, task: str) -> Path | None:
    task_log_dir = log_dir / task
    if not task_log_dir.exists():
        return None
    logs = sorted(task_log_dir.glob("oracle_*.log"), key=lambda path: path.stat().st_mtime, reverse=True)
    return logs[0] if logs else None


def oracle_passed(log_path: Path) -> bool:
    text = log_path.read_text(encoding="utf-8", errors="replace")
    if "FAILED" in text or "Traceback" in text or "ERROR" in text:
        return False
    return bool(re.search(r"=+\s+\d+ passed", text) or "PASSED" in text)


def newest_zip(zip_dir: Path, task: str) -> Path | None:
    if not zip_dir.exists():
        return None
    zips = sorted(zip_dir.glob(f"{task}*.zip"), key=lambda path: path.stat().st_mtime, reverse=True)
    return zips[0] if zips else None


def zip_has_bad_artifacts(zip_path: Path) -> list[str]:
    bad = []
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            lowered = name.lower()
            if any(part in lowered for part in ("__pycache__", ".pytest_cache", ".ruff_cache", ".pyc", ".terminus_logs", "auto-eval-logs")):
                bad.append(name)
    return bad[:20]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task", required=True)
    parser.add_argument("--task-root", default=".")
    parser.add_argument("--feedback-root", default="All-New-Feedbacks")
    parser.add_argument("--zip-root", default="new-task-upload")
    parser.add_argument("--log-root", default=".terminus_logs")
    parser.add_argument("--allow-unchecked", action="store_true")
    args = parser.parse_args()

    root = Path(args.task_root)
    task_dir = root / args.task
    feedback_dir = root / args.feedback_root / args.task
    brief = feedback_dir / "REVISION_BRIEF.md"
    messages: list[str] = []

    if task_dir.exists():
        ok(messages, f"task folder exists: {task_dir}")
    else:
        fail(messages, f"task folder missing: {task_dir}")

    if feedback_dir.exists():
        ok(messages, f"fresh feedback exists: {feedback_dir}")
    else:
        fail(messages, f"fresh feedback missing: {feedback_dir}")

    if brief.exists():
        ok(messages, f"revision brief exists: {brief}")
        text = brief.read_text(encoding="utf-8", errors="replace")
        unchecked = [line for line in text.splitlines() if line.strip().startswith("- [ ]")]
        if unchecked and not args.allow_unchecked:
            fail(messages, f"revision brief has unchecked items ({len(unchecked)}). Use --allow-unchecked if intentionally using it as a working brief.")
        else:
            ok(messages, "revision brief checklist is complete or allowed")
    else:
        fail(messages, f"revision brief missing: {brief}")

    cache_dirs = []
    if task_dir.exists():
        for pattern in ("__pycache__", ".pytest_cache", ".ruff_cache"):
            cache_dirs.extend(path for path in task_dir.rglob(pattern) if path.is_dir())
    if cache_dirs:
        fail(messages, "cache directories present: " + ", ".join(str(path) for path in cache_dirs[:10]))
    else:
        ok(messages, "no cache directories found in task")

    oracle_log = newest_oracle_log(root / args.log_root, args.task)
    if oracle_log and oracle_passed(oracle_log):
        ok(messages, f"latest oracle log appears passed: {oracle_log}")
    elif oracle_log:
        fail(messages, f"latest oracle log does not appear clean: {oracle_log}")
    else:
        fail(messages, f"oracle log missing under {root / args.log_root / args.task}")

    zip_path = newest_zip(root / args.zip_root, args.task)
    if zip_path:
        bad = zip_has_bad_artifacts(zip_path)
        if bad:
            fail(messages, f"zip contains generated/cache artifacts: {bad}")
        else:
            ok(messages, f"newest upload zip exists and looks clean: {zip_path}")
            if oracle_log and zip_path.stat().st_mtime + 1 < oracle_log.stat().st_mtime:
                fail(messages, f"newest upload zip is older than latest oracle log; rebuild with scripts/zip.sh: zip={zip_path}, oracle={oracle_log}")
            elif oracle_log:
                ok(messages, "newest upload zip was created after the latest oracle log")
    else:
        fail(messages, f"upload zip missing under {root / args.zip_root}")

    for message in messages:
        print(message)
    return 1 if any(message.startswith("FAIL:") for message in messages) else 0


if __name__ == "__main__":
    raise SystemExit(main())
