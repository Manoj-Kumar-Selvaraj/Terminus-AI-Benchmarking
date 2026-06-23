#!/usr/bin/env python3
"""Strip CRLF from all .sh files under revision-queue task folders."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from fix_custom_revisions_batch import all_tasks  # noqa: E402


def strip_file(sh: Path) -> bool:
    data = sh.read_bytes()
    if b"\r" not in data:
        return False
    sh.write_bytes(data.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
    return True


def main() -> int:
    n = 0
    for folder in all_tasks():
        td = ROOT / folder
        if not td.is_dir():
            continue
        for sh in td.rglob("*.sh"):
            if strip_file(sh):
                n += 1
                print(f"fixed CRLF: {sh.relative_to(ROOT)}")
    # scripts used by zip/pack
    for sh in (ROOT / "scripts").glob("*.sh"):
        if strip_file(sh):
            n += 1
            print(f"fixed CRLF: {sh.relative_to(ROOT)}")
    print(f"done, {n} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
