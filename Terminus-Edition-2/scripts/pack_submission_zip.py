#!/usr/bin/env python3
"""Create a Harbor-compatible submission zip (task files at archive root, with dir entries)."""
from __future__ import annotations

import argparse
import sys
import zipfile
from datetime import datetime
from pathlib import Path

SKIP_PARTS = {
    "terminus_logs",
    "harbor_logs",
    "submission_zips",
    "revision_logs",
    "__pycache__",
    ".git",
    ".terminus_logs",
}

SKIP_FILES = {"rubric.txt"}


def should_skip(rel: Path) -> bool:
    return any(part in SKIP_PARTS or part.startswith("jobs") for part in rel.parts)


def milestone_test_file(task_dir: Path, milestone: int) -> str:
    tests_dir = task_dir / f"steps/milestone_{milestone}/tests"
    py_path = tests_dir / f"test_m{milestone}.py"
    rb_path = tests_dir / f"test_m{milestone}.rb"
    if py_path.is_file():
        return py_path.name
    if rb_path.is_file():
        return rb_path.name
    return f"test_m{milestone}.py"


def validate_zip(zip_path: Path, milestones: int, task_dir: Path) -> list[str]:
    errors: list[str] = []
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        if "task.toml" not in names:
            errors.append("zip missing task.toml at archive root")
        env_files = [n for n in names if n.startswith("environment/") and not n.endswith("/")]
        if not env_files:
            errors.append("zip missing environment/ files")
        if not any(n == "environment/" or n.startswith("environment/") for n in names):
            errors.append("zip missing environment/ directory entry (use this script, not Compress-Archive)")
        if milestones > 0:
            for i in range(1, milestones + 1):
                base = f"steps/milestone_{i}"
                test_file = milestone_test_file(task_dir, i)
                for rel in (
                    f"{base}/instruction.md",
                    f"{base}/tests/test.sh",
                    f"{base}/tests/{test_file}",
                    f"{base}/solution/solve.sh",
                    f"{base}/solution/solve{i}.sh",
                ):
                    if rel not in names:
                        errors.append(f"zip missing {rel}")
            for forbidden in ("instruction.md", "tests/test.sh", "solution/solve.sh"):
                if forbidden in names:
                    errors.append(f"zip must not include root-level {forbidden}")
        else:
            for rel in ("instruction.md", "tests/test.sh", "solution/solve.sh"):
                if rel not in names:
                    errors.append(f"zip missing {rel}")
        nested = {n.split("/")[0] for n in names if "/" in n}
        if len(nested) == 1 and list(nested)[0] not in {
            "environment",
            "steps",
            "solution",
            "tests",
        }:
            errors.append(
                f"zip appears nested inside an extra folder ({list(nested)[0]}/); "
                "zip task contents, not the parent folder name"
            )
        if any(n == "rubric.txt" or n.endswith("/rubric.txt") for n in names):
            errors.append(
                "zip must not include rubric.txt; maintain rubrics in the Snorkel platform UI only"
            )
    return errors


def read_milestones(task_dir: Path) -> int:
    text = (task_dir / "task.toml").read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if line.startswith("number_of_milestones"):
            return int(line.split("=", 1)[1].strip())
    return 0


def pack_task(task_dir: Path, out_dir: Path) -> Path:
    task_dir = task_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = out_dir / f"{task_dir.name}_{stamp}.zip"
    if zip_path.exists():
        zip_path.unlink()

    dirs_written: set[str] = set()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(task_dir.rglob("*")):
            rel = path.relative_to(task_dir)
            if should_skip(rel):
                continue
            if path.is_dir():
                name = rel.as_posix().rstrip("/") + "/"
                if name not in dirs_written:
                    zf.writestr(name, "")
                    dirs_written.add(name)
                continue
            if path.suffix == ".pyc":
                continue
            if path.name in SKIP_FILES:
                continue
            parent = rel.parent
            if parent != Path("."):
                parent_name = parent.as_posix().rstrip("/") + "/"
                if parent_name not in dirs_written:
                    zf.writestr(parent_name, "")
                    dirs_written.add(parent_name)
            zf.write(path, rel.as_posix())

    milestones = read_milestones(task_dir)
    errors = validate_zip(zip_path, milestones, task_dir)
    if errors:
        zip_path.unlink(missing_ok=True)
        raise SystemExit("\n".join(errors))
    return zip_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_dir", type=Path, help="Path to task directory")
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "submission_zips",
        help="Output directory for zip files",
    )
    args = parser.parse_args()
    if not args.task_dir.is_dir():
        print(f"ERROR: not a directory: {args.task_dir}", file=sys.stderr)
        raise SystemExit(2)
    zip_path = pack_task(args.task_dir, args.out_dir)
    print(f"Created: {zip_path}")
    with zipfile.ZipFile(zip_path) as zf:
        print(f"Entries: {len(zf.namelist())} (dirs: {sum(1 for n in zf.namelist() if n.endswith('/'))})")


if __name__ == "__main__":
    main()
