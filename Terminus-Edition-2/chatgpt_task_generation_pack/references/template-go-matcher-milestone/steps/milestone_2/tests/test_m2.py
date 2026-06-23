"""Template milestone 2 tests — alias normalization."""

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


def test_aliases_match_and_emit_canonical_tiers():
    """TA and TB aliases should match and emit TIER_A and TIER_B on matched rows."""
    build_program()
    write_inputs(
        [["REC-A", "ACCT-1", "1200", "ACTIVE", "TIER_A"], ["REC-B", "ACCT-2", "3400", "ACTIVE", "TIER_B"]],
        [["REC-A", "ACCT-1", "1200", "TA"], ["REC-B", "ACCT-2", "3400", "tb"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["tier"] for row in rows] == ["TIER_A", "TIER_B"]
    assert summary["matched_count"] == 2


def test_milestone_one_rules_still_apply():
    """Milestone 2 must not regress full-id matching from milestone 1."""
    build_program()
    write_inputs(
        [["REC-X", "ACCT-1", "1000", "ACTIVE", "TIER_A"]],
        [["REC-WRONG", "ACCT-1", "1000", "TA"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["tier"] == ""
    assert summary["matched_count"] == 0
