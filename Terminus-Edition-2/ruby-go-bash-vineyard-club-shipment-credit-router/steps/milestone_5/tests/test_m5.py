"""Preflight/oracle wrapper — runs the Ruby milestone verifier."""
import subprocess
import sys
from pathlib import Path

rb = Path(__file__).with_suffix(".rb")
sys.exit(subprocess.run(["ruby", str(rb)], check=False).returncode)
