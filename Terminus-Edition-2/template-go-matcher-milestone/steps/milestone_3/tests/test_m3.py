"""Template milestone 3 tests — extend when you add real M3 behavior."""

import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
GO = Path("/usr/local/go/bin/go")
BIN = APP / "build" / "template-reconcile"
RECORDS = APP / "data" / "records.csv"
ADJUSTMENTS = APP / "data" / "adjustments.csv"
REPORT = APP / "out" / "template_report.csv"
SUMMARY = APP / "out" / "template_summary.json"


def build_program():
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile/main.go"], check=True, cwd=APP, timeout=60)


def write_inputs(record_rows, adjustment_rows):
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    with RECORDS.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["record_id", "account_id", "amount_cents", "status", "tier"])
        writer.writerows(record_rows)
    with ADJUSTMENTS.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["record_id", "account_id", "amount_cents", "tier"])
        writer.writerows(adjustment_rows)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


def test_milestone_two_alias_behavior_persists_in_milestone_three():
    """Placeholder M3 test: prior milestones must keep working until you add M3 rules."""
    build_program()
    write_inputs(
        [["REC-M3", "ACCT-1", "500", "ACTIVE", "TIER_B"]],
        [["REC-M3", "ACCT-1", "500", "TB"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["tier"] == "TIER_B"
    assert summary["matched_count"] == 1
