"""Template milestone 1 tests — replace domain names when forking."""

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
    """Compile the Go reconciler for one scenario."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile/main.go"], check=True, cwd=APP, timeout=60)


def write_inputs(record_rows, adjustment_rows):
    """Overwrite inputs and clear outputs for one scenario."""
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
    """Run the CLI and return parsed report rows and summary."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


def test_full_id_match_and_positive_summary():
    """Full record_id match with ACTIVE status and allowed tiers should match."""
    build_program()
    write_inputs(
        [["REC-001", "ACCT-1", "1000", "ACTIVE", "TIER_A"], ["REC-002", "ACCT-2", "2000", "ACTIVE", "TIER_B"]],
        [["REC-001", "ACCT-1", "1000", "TIER_A"], ["REC-002", "ACCT-2", "2000", "TIER_B"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert summary == {"matched_count": 2, "matched_amount_cents": 3000, "unmatched_count": 0, "unmatched_amount_cents": 0}


def test_prefix_only_record_id_stays_unmatched():
    """Partial record_id prefix matching must not match unrelated records."""
    build_program()
    write_inputs(
        [["REC-PREFIX-001", "ACCT-1", "1000", "ACTIVE", "TIER_A"], ["REC-PREFIX-002", "ACCT-1", "1000", "ACTIVE", "TIER_A"]],
        [["REC-PREFIX-999", "ACCT-1", "1000", "TIER_A"], ["REC-PREFIX-002", "ACCT-1", "1000", "TIER_A"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert summary["matched_count"] == 1
    assert summary["unmatched_amount_cents"] == 1000
