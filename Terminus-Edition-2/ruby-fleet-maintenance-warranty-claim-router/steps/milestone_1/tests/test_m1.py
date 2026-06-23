"""Verifier tests for realtime fleet maintenance warranty claim reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "appointments.csv"
ACTION = APP / "data" / "warranty_claims.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "claim_route_report.csv"
SUMMARY = APP / "out" / "claim_route_summary.txt"


def build_program():
    """Prepare the reconciler for one verifier scenario."""
    pass


def write_csv(path, header, rows):
    """Write one CSV fixture."""
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(source, action, windows):
    """Overwrite all input files at runtime."""
    write_csv(SOURCE, ["repair_id", "member_id", "site_id", "repair_type", "amount", "repair_ts", "status", "bay"], source)
    write_csv(ACTION, ["claim_id", "repair_id", "member_id", "site_id", "repair_type", "amount", "claim_ts", "reason", "bay"], action)
    write_csv(WINDOWS, ["site_id", "open_ts", "close_ts", "state"], windows)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the reconciler and parse outputs."""
    subprocess.run(["ruby", "/app/app/reconcile.rb"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        summary[key] = int(value)
    return rows, summary


def test_all_gates_consumption_and_positive_unmatched_totals():
    """Every identity, status, timestamp, reason, and consumption gate should reject bad candidates."""
    build_program()
    write_inputs(
        [
            ["SRC-GATE-1", "PARTY-1", "S-G", "ENGINE", "10", "20260528140000", "CLOSED", "L1"],
            ["SRC-GATE-2", "PARTY-2", "S-G", "ENGINE", "20", "20260528140100", "BAD", "L2"],
            ["SRC-GATE-3", "PARTY-3", "S-G", "BRAKE", "30", "20260528140200", "CLOSED", "L3"],
            ["SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140300", "CLOSED", "L4"],
        ],
        [
            ["ACT-A", "SRC-GATE-1", "PARTY-1", "S-G", "ENGINE", "10", "20260528140500", "PARTS", "L1"],
            ["ACT-B", "SRC-GATE-1", "PARTY-1", "S-G", "ENGINE", "10", "20260528140600", "PARTS", "L1"],
            ["ACT-C", "SRC-GATE-2", "PARTY-2", "S-G", "ENGINE", "20", "20260528140700", "PARTS", "L2"],
            ["ACT-D", "SRC-GATE-3", "PARTY-X", "S-G", "BRAKE", "30", "20260528140700", "TIREOR", "L3"],
            ["ACT-E", "SRC-GATE-3", "PARTY-3", "S-G", "BRAKE", "31", "20260528140700", "TIREOR", "L3"],
            ["ACT-F", "SRC-GATE-3", "PARTY-3", "S-G", "BRAKE", "30", "20260528135959", "TIREOR", "L3"],
            ["ACT-G", "SRC-GATE-3", "PARTY-3", "S-G", "BRAKE", "30", "20260528140700", "INFO", "L3"],
            ["ACT-H", "SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140700", "TOW", "L4"],
        ],
        [["S-G", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert rows[1]["repair_type"] == ""
    assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 7, "unmatched_amount": 191}
