#!/usr/bin/env python3
"""Strip CRLF from all .sh under batch11 task folders."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
tasks = [
    ln.strip()
    for ln in (ROOT / "batch11_tasks.txt").read_text(encoding="utf-8").splitlines()
    if ln.strip() and not ln.startswith("#")
]
n = 0
for task in tasks:
    td = ROOT / task
    if not td.is_dir():
        continue
    for sh in td.rglob("*.sh"):
        data = sh.read_bytes()
        if b"\r" in data:
            sh.write_bytes(data.replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
            n += 1
            print(f"fixed CRLF: {sh.relative_to(ROOT)}")
print(f"done, {n} files")
