"""Verifier tests for realtime marina berth hold release reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "berth_holds.csv"
ACTION = APP / "data" / "berth_releases.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "berth_release_report.csv"
SUMMARY = APP / "out" / "berth_release_summary.txt"


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
    write_csv(SOURCE, ["hold_id", "vessel_id", "dock_id", "berth_type", "amount", "hold_ts", "status", "slip"], source)
    write_csv(ACTION, ["release_id", "hold_id", "vessel_id", "dock_id", "berth_type", "amount", "release_ts", "reason", "slip"], action)
    write_csv(WINDOWS, ["dock_id", "open_ts", "close_ts", "state"], windows)
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
            ["SRC-GATE-1", "PARTY-1", "S-G", "SLIP", "10", "20260528140000", "MOORED", "L1"],
            ["SRC-GATE-2", "PARTY-2", "S-G", "SLIP", "20", "20260528140100", "BAD", "L2"],
            ["SRC-GATE-3", "PARTY-3", "S-G", "DRY", "30", "20260528140200", "MOORED", "L3"],
            ["SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140300", "MOORED", "L4"],
        ],
        [
            ["ACT-A", "SRC-GATE-1", "PARTY-1", "S-G", "SLIP", "10", "20260528140500", "DEPART", "L1"],
            ["ACT-B", "SRC-GATE-1", "PARTY-1", "S-G", "SLIP", "10", "20260528140600", "DEPART", "L1"],
            ["ACT-C", "SRC-GATE-2", "PARTY-2", "S-G", "SLIP", "20", "20260528140700", "DEPART", "L2"],
            ["ACT-D", "SRC-GATE-3", "PARTY-X", "S-G", "DRY", "30", "20260528140700", "TRANSFER", "L3"],
            ["ACT-E", "SRC-GATE-3", "PARTY-3", "S-G", "DRY", "31", "20260528140700", "TRANSFER", "L3"],
            ["ACT-F", "SRC-GATE-3", "PARTY-3", "S-G", "DRY", "30", "20260528135959", "TRANSFER", "L3"],
            ["ACT-G", "SRC-GATE-3", "PARTY-3", "S-G", "DRY", "30", "20260528140700", "INFO", "L3"],
            ["ACT-H", "SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140700", "OVERRIDE", "L4"],
        ],
        [["S-G", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert rows[1]["berth_type"] == ""
    assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 7, "unmatched_amount": 191}


def test_full_hold_id_required():
    """A correction must not match when only the leading hold_id prefix overlaps."""
    build_program()
    write_inputs(
        [
            ["SRC-PFX-001", "PARTY-1", "S-P", "SLIP", "15", "20260528150000", "MOORED", "L1"],
            ["SRC-PFX-002", "PARTY-1", "S-P", "SLIP", "15", "20260528150100", "MOORED", "L1"],
        ],
        [
            ["ACT-PFX-1", "SRC-PFX-999", "PARTY-1", "S-P", "SLIP", "15", "20260528150500", "DEPART", "L1"],
            ["ACT-PFX-2", "SRC-PFX-002", "PARTY-1", "S-P", "SLIP", "15", "20260528150600", "DEPART", "L1"],
        ],
        [["S-P", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert summary["matched_count"] == 1


def test_release_ts_before_hold_ts_is_rejected():
    """release_ts earlier than hold_ts must leave the correction unmatched."""
    build_program()
    write_inputs(
        [["SRC-EARLY-1", "PARTY-1", "S-E", "DRY", "25", "20260528160000", "MOORED", "L1"]],
        [["ACT-EARLY-1", "SRC-EARLY-1", "PARTY-1", "S-E", "DRY", "25", "20260528155959", "TRANSFER", "L1"]],
        [["S-E", "20260528155800", "20260528163000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["berth_type"] == ""
    assert summary["matched_count"] == 0

def test_non_numeric_timestamps_stay_unmatched():
    """Non-numeric hold_ts or release_ts values must reject matching."""
    build_program()
    write_inputs(
        [["SRC-BAD-TS", "PARTY-1", "S-1", "SLIP", "10", "bad-ts", "MOORED", "L1"]],
        [["ACT-BAD-TS", "SRC-BAD-TS", "PARTY-1", "S-1", "SLIP", "10", "20260528140500", "DEPART", "L1"]],
        [["S-1", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["berth_type"] == ""
    assert summary["matched_count"] == 0
