#!/usr/bin/env python3
"""Add test_mN.py wrappers for ruby-go-bash-vineyard milestone Ruby tests."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASK = ROOT / "ruby-go-bash-vineyard-club-shipment-credit-router"

WRAPPER = '''"""Preflight/oracle wrapper — runs the Ruby milestone verifier."""
import subprocess
import sys
from pathlib import Path

rb = Path(__file__).with_suffix(".rb")
sys.exit(subprocess.run(["ruby", str(rb)], check=False).returncode)
'''

for m in range(1, 8):
    tests_dir = TASK / "steps" / f"milestone_{m}" / "tests"
    rb = tests_dir / f"test_m{m}.rb"
    py = tests_dir / f"test_m{m}.py"
    if rb.is_file() and not py.is_file():
        py.write_text(WRAPPER, encoding="utf-8")
        print(f"created {py.relative_to(ROOT)}")
