"""Verifier tests for realtime EV charging session release reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "charge_sessions.csv"
ACTION = APP / "data" / "session_releases.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "ev_release_report.csv"
SUMMARY = APP / "out" / "ev_release_summary.txt"


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
    write_csv(SOURCE, ["session_id", "vehicle_id", "station_id", "rate_plan", "amount", "plug_ts", "status", "port"], source)
    write_csv(ACTION, ["release_id", "session_id", "vehicle_id", "station_id", "rate_plan", "amount", "release_ts", "reason", "port"], action)
    write_csv(WINDOWS, ["station_id", "open_ts", "close_ts", "state"], windows)
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
            ["SRC-GATE-1", "PARTY-1", "S-G", "LEVEL2", "10", "20260528140000", "ACTIVE", "L1"],
            ["SRC-GATE-2", "PARTY-2", "S-G", "LEVEL2", "20", "20260528140100", "BAD", "L2"],
            ["SRC-GATE-3", "PARTY-3", "S-G", "DCFC", "30", "20260528140200", "ACTIVE", "L3"],
            ["SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140300", "ACTIVE", "L4"],
        ],
        [
            ["ACT-A", "SRC-GATE-1", "PARTY-1", "S-G", "LEVEL2", "10", "20260528140500", "STOP", "L1"],
            ["ACT-B", "SRC-GATE-1", "PARTY-1", "S-G", "LEVEL2", "10", "20260528140600", "STOP", "L1"],
            ["ACT-C", "SRC-GATE-2", "PARTY-2", "S-G", "LEVEL2", "20", "20260528140700", "STOP", "L2"],
            ["ACT-D", "SRC-GATE-3", "PARTY-X", "S-G", "DCFC", "30", "20260528140700", "FAULT", "L3"],
            ["ACT-E", "SRC-GATE-3", "PARTY-3", "S-G", "DCFC", "31", "20260528140700", "FAULT", "L3"],
            ["ACT-F", "SRC-GATE-3", "PARTY-3", "S-G", "DCFC", "30", "20260528135959", "FAULT", "L3"],
            ["ACT-G", "SRC-GATE-3", "PARTY-3", "S-G", "DCFC", "30", "20260528140700", "INFO", "L3"],
            ["ACT-H", "SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140700", "OVERRIDE", "L4"],
        ],
        [["S-G", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert rows[1]["rate_plan"] == ""
    assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 7, "unmatched_amount": 191}
def test_aliases_full_keys_and_canonical_output():
    """Aliases should match full source keys and emit canonical rate_plan values."""
    build_program()
    write_inputs(
        [
            ["SRC-100000001", "PARTY-1", "S-A", "LEVEL2", "12", "20260528120500", "ACTIVE", "LOC-1"],
            ["SRC-100000002", "PARTY-2", "S-A", "DCFC", "34", "20260528120600", "ACTIVE", "LOC-2"],
            ["SRC-100000003", "PARTY-3", "S-B", "FLEET", "56", "20260528130500", "ACTIVE", "LOC-3"],
        ],
        [
            ["ACT-1", "SRC-100000001", "PARTY-1", "S-A", "HR", "12", "20260528121000", "STOP", "LOC-1"],
            ["ACT-2", "SRC-100000002", "PARTY-2", "S-A", "QR", "34", "20260528121100", "FAULT", "LOC-2"],
            ["ACT-3", "SRC-100000003", "PARTY-3", "S-B", "CC", "56", "20260528131000", "OVERRIDE", "LOC-3"],
        ],
        [["S-A", "20260528120000", "20260528123000", "OPEN"], ["S-B", "20260528130000", "20260528133000", "OPEN"]],
    )
    rows, summary = run_program()
    assert REPORT.read_text().splitlines()[0] == "release_id,session_id,vehicle_id,station_id,rate_plan,amount,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["rate_plan"] for row in rows] == ["LEVEL2", "DCFC", "FLEET"]
    assert summary == {"matched_count": 3, "matched_amount": 102, "unmatched_count": 0, "unmatched_amount": 0}
def test_window_state_malformed_times_latest_candidate_and_order():
    """Closed windows, malformed timestamps, latest plug_ts selection among duplicate session_id rows, duplicate-row consumption, and blank unmatched rate_plan fields should hold."""
    build_program()
    write_inputs(
        [
            ["SRC-WIN-1", "PARTY-1", "S-O", "LEVEL2", "1", "20260528150000", "ACTIVE", "L1"],
            ["SRC-WIN-2", "PARTY-2", "S-C", "LEVEL2", "2", "20260528150000", "ACTIVE", "L2"],
            ["SRC-WIN-3", "PARTY-3", "S-M", "DCFC", "3", "bad-time", "ACTIVE", "L3"],
            ["SRC-DDYE", "PARTY-4", "S-O", "FLEET", "4", "20260528150100", "ACTIVE", "L4"],
            ["SRC-DDYE", "PARTY-4", "S-O", "FLEET", "4", "20260528150200", "ACTIVE", "L4"],
        ],
        [
            ["ACT-1", "SRC-WIN-1", "PARTY-1", "S-O", "LEVEL2", "1", "20260528150500", "STOP", "L1"],
            ["ACT-2", "SRC-WIN-2", "PARTY-2", "S-C", "LEVEL2", "2", "20260528150500", "STOP", "L2"],
            ["ACT-3", "SRC-WIN-3", "PARTY-3", "S-M", "DCFC", "3", "20260528150500", "FAULT", "L3"],
            ["ACT-4", "SRC-DDYE", "PARTY-4", "S-O", "FLEET", "4", "20260528150600", "OVERRIDE", "L4"],
        ],
        [["S-O", "20260528145900", "20260528153000", "OPEN"], ["S-C", "20260528145900", "20260528153000", "NOT_OPEN"], ["S-M", "bad-time", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["release_id"] for row in rows] == ["ACT-1", "ACT-2", "ACT-3", "ACT-4"]
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert [row["rate_plan"] for row in rows] == ["LEVEL2", "", "", "FLEET"]
    assert summary == {"matched_count": 2, "matched_amount": 5, "unmatched_count": 2, "unmatched_amount": 5}


def test_adjustment_after_window_close_is_rejected():
    """A correction whose release_ts is after the window close must not match."""
    build_program()
    write_inputs(
        [["SRC-AFTER_CLOSE-1", "PARTY-C", "S-AFTER_CLOSE", "LEVEL2", "11", "20260528180000", "ACTIVE", "L1"]],
        [["ACT-AFTER_CLOSE-1", "SRC-AFTER_CLOSE-1", "PARTY-C", "S-AFTER_CLOSE", "LEVEL2", "11", "20260528183001", "STOP", "L1"]],
        [["S-AFTER_CLOSE", "20260528175900", "20260528183000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["rate_plan"] == ""
    assert summary["matched_count"] == 0
    assert summary["unmatched_amount"] == 11


def test_adjustment_at_window_close_boundary_matches():
    """A correction whose release_ts equals the window close should still match."""
    build_program()
    write_inputs(
        [["SRC-BOUND-1", "PARTY-B", "S-BOUND", "DCFC", "22", "20260528190000", "ACTIVE", "L1"]],
        [["ACT-BOUND-1", "SRC-BOUND-1", "PARTY-B", "S-BOUND", "DCFC", "22", "20260528193000", "OVERRIDE", "L1"]],
        [["S-BOUND", "20260528185900", "20260528193000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["rate_plan"] == "DCFC"
    assert summary["matched_amount"] == 22


def test_duplicate_session_id_rows_are_consumed_by_position():
    """Duplicate source rows with the same session_id and plug_ts are independently consumable by row position."""
    build_program()
    write_inputs(
        [
            ["SRC-TIE-1", "PARTY-T", "S-TIE", "FLEET", "33", "20260528200000", "ACTIVE", "L1"],
            ["SRC-TIE-1", "PARTY-T", "S-TIE", "FLEET", "33", "20260528200000", "ACTIVE", "L1"],
        ],
        [
            ["ACT-TIE-1", "SRC-TIE-1", "PARTY-T", "S-TIE", "CC", "33", "20260528200100", "FAULT", "L1"],
            ["ACT-TIE-2", "SRC-TIE-1", "PARTY-T", "S-TIE", "CC", "33", "20260528200200", "FAULT", "L1"],
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
        [["SRC-REL-BAD", "PARTY-1", "S-1", "FLEET", "15", "20260528140000", "ACTIVE", "L1"]],
        [["ACT-REL-BAD", "SRC-REL-BAD", "PARTY-1", "S-1", "CC", "15", "bad-ts", "STOP", "L1"]],
        [["S-1", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["rate_plan"] == ""
    assert summary["matched_count"] == 0
