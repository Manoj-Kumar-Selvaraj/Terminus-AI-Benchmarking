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
def test_aliases_full_keys_and_canonical_output():
    """Aliases should match full source keys and emit canonical berth_type values."""
    build_program()
    write_inputs(
        [
            ["SRC-100000001", "PARTY-1", "S-A", "SLIP", "12", "20260528120500", "MOORED", "LOC-1"],
            ["SRC-100000002", "PARTY-2", "S-A", "DRY", "34", "20260528120600", "MOORED", "LOC-2"],
            ["SRC-100000003", "PARTY-3", "S-B", "TRANSIT", "56", "20260528130500", "MOORED", "LOC-3"],
        ],
        [
            ["ACT-1", "SRC-100000001", "PARTY-1", "S-A", "HR", "12", "20260528121000", "DEPART", "LOC-1"],
            ["ACT-2", "SRC-100000002", "PARTY-2", "S-A", "QR", "34", "20260528121100", "TRANSFER", "LOC-2"],
            ["ACT-3", "SRC-100000003", "PARTY-3", "S-B", "CC", "56", "20260528131000", "OVERRIDE", "LOC-3"],
        ],
        [["S-A", "20260528120000", "20260528123000", "OPEN"], ["S-B", "20260528130000", "20260528133000", "OPEN"]],
    )
    rows, summary = run_program()
    assert REPORT.read_text().splitlines()[0] == "release_id,hold_id,vessel_id,dock_id,berth_type,amount,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["berth_type"] for row in rows] == ["SLIP", "DRY", "TRANSIT"]
    assert summary == {"matched_count": 3, "matched_amount": 102, "unmatched_count": 0, "unmatched_amount": 0}
def test_window_state_malformed_times_latest_candidate_and_order():
    """Closed windows, malformed timestamps, latest hold_ts selection among duplicate hold_id rows, earliest-input tie-break on equal hold_ts, and blank unmatched category fields should hold."""
    build_program()
    write_inputs(
        [
            ["SRC-WIN-1", "PARTY-1", "S-O", "SLIP", "1", "20260528150000", "MOORED", "L1"],
            ["SRC-WIN-2", "PARTY-2", "S-C", "SLIP", "2", "20260528150000", "MOORED", "L2"],
            ["SRC-WIN-3", "PARTY-3", "S-M", "DRY", "3", "bad-time", "MOORED", "L3"],
            ["SRC-DDYE", "PARTY-4", "S-O", "TRANSIT", "4", "20260528150100", "MOORED", "L4"],
            ["SRC-DDYE", "PARTY-4", "S-O", "TRANSIT", "4", "20260528150200", "MOORED", "L4"],
        ],
        [
            ["ACT-1", "SRC-WIN-1", "PARTY-1", "S-O", "SLIP", "1", "20260528150500", "DEPART", "L1"],
            ["ACT-2", "SRC-WIN-2", "PARTY-2", "S-C", "SLIP", "2", "20260528150500", "DEPART", "L2"],
            ["ACT-3", "SRC-WIN-3", "PARTY-3", "S-M", "DRY", "3", "20260528150500", "TRANSFER", "L3"],
            ["ACT-4", "SRC-DDYE", "PARTY-4", "S-O", "TRANSIT", "4", "20260528150600", "OVERRIDE", "L4"],
        ],
        [["S-O", "20260528145900", "20260528153000", "OPEN"], ["S-C", "20260528145900", "20260528153000", "CLOS"], ["S-M", "bad-time", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["release_id"] for row in rows] == ["ACT-1", "ACT-2", "ACT-3", "ACT-4"]
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert [row["berth_type"] for row in rows] == ["SLIP", "", "", "TRANSIT"]
    assert summary == {"matched_count": 2, "matched_amount": 5, "unmatched_count": 2, "unmatched_amount": 5}


def test_adjustment_after_window_close_is_rejected():
    """A correction whose release_ts is after the window close must not match."""
    build_program()
    write_inputs(
        [["SRC-CLOSE-1", "PARTY-C", "S-CLOSE", "SLIP", "11", "20260528180000", "MOORED", "L1"]],
        [["ACT-CLOSE-1", "SRC-CLOSE-1", "PARTY-C", "S-CLOSE", "SLIP", "11", "20260528183001", "DEPART", "L1"]],
        [["S-CLOSE", "20260528175900", "20260528183000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["berth_type"] == ""
    assert summary["matched_count"] == 0
    assert summary["unmatched_amount"] == 11


def test_adjustment_at_window_close_boundary_matches():
    """A correction whose release_ts equals the window close should still match."""
    build_program()
    write_inputs(
        [["SRC-BOUND-1", "PARTY-B", "S-BOUND", "DRY", "22", "20260528190000", "MOORED", "L1"]],
        [["ACT-BOUND-1", "SRC-BOUND-1", "PARTY-B", "S-BOUND", "DRY", "22", "20260528193000", "OVERRIDE", "L1"]],
        [["S-BOUND", "20260528185900", "20260528193000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["berth_type"] == "DRY"
    assert summary["matched_amount"] == 22


def test_equal_hold_ts_tie_uses_earliest_source_row():
    """When hold_ts ties, the earliest source input row must win."""
    build_program()
    write_inputs(
        [
            ["SRC-TIE-1", "PARTY-T", "S-TIE", "TRANSIT", "33", "20260528200000", "MOORED", "L1"],
            ["SRC-TIE-1", "PARTY-T", "S-TIE", "TRANSIT", "33", "20260528200000", "MOORED", "L1"],
        ],
        [
            ["ACT-TIE-1", "SRC-TIE-1", "PARTY-T", "S-TIE", "CC", "33", "20260528200100", "TRANSFER", "L1"],
            ["ACT-TIE-2", "SRC-TIE-1", "PARTY-T", "S-TIE", "CC", "33", "20260528200200", "TRANSFER", "L1"],
        ],
        [["S-TIE", "20260528195900", "20260528203000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount"] == 66

def test_non_numeric_release_timestamp_stays_unmatched():
    """A correction with non-numeric release_ts must stay unmatched even inside an OPEN window."""
    build_program()
    write_inputs(
        [["SRC-REL-BAD", "PARTY-1", "S-1", "TRANSIT", "15", "20260528140000", "MOORED", "L1"]],
        [["ACT-REL-BAD", "SRC-REL-BAD", "PARTY-1", "S-1", "CC", "15", "bad-ts", "DEPART", "L1"]],
        [["S-1", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["berth_type"] == ""
    assert summary["matched_count"] == 0
