#!/usr/bin/env python3
import subprocess
from pathlib import Path

APP = Path("/app")
subprocess.run(["/app/scripts/compile.sh"], check=True, cwd=APP)
subprocess.run(["/app/scripts/clean_outputs.sh"], check=True, cwd=APP)
(APP / "config/usage_manifest.txt").write_text("01 /app/data/run01.usg\n")
rows = []
for i, amt in enumerate((100000, 450000), start=1):
    rows.append(f"U{'ACCT2001':8}{'BATCH2':6}{i:04d}{amt:010d}{'SVC1':4}".ljust(52))
(APP / "data/run01.usg").write_text("\n".join(rows) + "\n")
proc = subprocess.run(["/app/build/batch"], cwd=APP, capture_output=True, text=True)
print("rc", proc.returncode)
print("stdout", proc.stdout)
print("stderr", proc.stderr)
print("INV", repr((APP / "out/invoice_register.dat").read_text()))
print("SUM", (APP / "out/billing_summary.txt").read_text())
print("TRACE", repr((APP / "out/approval_trace.dat").read_text()))
