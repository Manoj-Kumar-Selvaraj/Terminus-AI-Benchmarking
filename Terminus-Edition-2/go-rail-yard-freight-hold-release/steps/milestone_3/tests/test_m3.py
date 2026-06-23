"""Verifier tests for realtime rail yard freight hold release reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
GO = Path("/usr/local/go/bin/go")
BIN = APP / "build" / "reconcile"
SOURCE = APP / "data" / "holds.csv"
ACTION = APP / "data" / "releases.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "freight_release_report.csv"
SUMMARY = APP / "out" / "freight_release_summary.txt"


def build_program():
    """Prepare the reconciler for one verifier scenario."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile/main.go"], check=True, cwd=APP, timeout=60)


def write_csv(path, header, rows):
    """Write one CSV fixture."""
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(source, action, windows):
    """Overwrite all input files at runtime."""
    write_csv(SOURCE, ["hold_id", "car_id", "yard_id", "cargo_class", "amount", "hold_ts", "status", "track"], source)
    write_csv(ACTION, ["release_id", "hold_id", "car_id", "yard_id", "cargo_class", "amount", "release_ts", "reason", "track"], action)
    write_csv(WINDOWS, ["yard_id", "open_ts", "close_ts", "state"], windows)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the reconciler and parse outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
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
            ["SRC-GATE-1", "PARTY-1", "S-G", "HAZ", "10", "20260528140000", "HELD", "L1"],
            ["SRC-GATE-2", "PARTY-2", "S-G", "HAZ", "20", "20260528140100", "BAD", "L2"],
            ["SRC-GATE-3", "PARTY-3", "S-G", "DRY", "30", "20260528140200", "HELD", "L3"],
            ["SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140300", "HELD", "L4"],
        ],
        [
            ["ACT-A", "SRC-GATE-1", "PARTY-1", "S-G", "HAZ", "10", "20260528140500", "RELEASE", "L1"],
            ["ACT-B", "SRC-GATE-1", "PARTY-1", "S-G", "HAZ", "10", "20260528140600", "RELEASE", "L1"],
            ["ACT-C", "SRC-GATE-2", "PARTY-2", "S-G", "HAZ", "20", "20260528140700", "RELEASE", "L2"],
            ["ACT-D", "SRC-GATE-3", "PARTY-X", "S-G", "DRY", "30", "20260528140700", "RECALL", "L3"],
            ["ACT-E", "SRC-GATE-3", "PARTY-3", "S-G", "DRY", "31", "20260528140700", "RECALL", "L3"],
            ["ACT-F", "SRC-GATE-3", "PARTY-3", "S-G", "DRY", "30", "20260528135959", "RECALL", "L3"],
            ["ACT-G", "SRC-GATE-3", "PARTY-3", "S-G", "DRY", "30", "20260528140700", "INFO", "L3"],
            ["ACT-H", "SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140700", "OVERRIDE", "L4"],
        ],
        [["S-G", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert rows[1]["cargo_class"] == ""
    assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 7, "unmatched_amount": 191}
def test_aliases_full_keys_and_canonical_output():
    """Aliases should match full source keys and emit canonical cargo_class values."""
    build_program()
    write_inputs(
        [
            ["SRC-100000001", "PARTY-1", "S-A", "HAZ", "12", "20260528120500", "HELD", "LOC-1"],
            ["SRC-100000002", "PARTY-2", "S-A", "DRY", "34", "20260528120600", "HELD", "LOC-2"],
            ["SRC-100000003", "PARTY-3", "S-B", "REF", "56", "20260528130500", "HELD", "LOC-3"],
        ],
        [
            ["ACT-1", "SRC-100000001", "PARTY-1", "S-A", "IN", "12", "20260528121000", "RELEASE", "LOC-1"],
            ["ACT-2", "SRC-100000002", "PARTY-2", "S-A", "CU", "34", "20260528121100", "RECALL", "LOC-2"],
            ["ACT-3", "SRC-100000003", "PARTY-3", "S-B", "SE", "56", "20260528131000", "OVERRIDE", "LOC-3"],
        ],
        [["S-A", "20260528120000", "20260528123000", "OPEN"], ["S-B", "20260528130000", "20260528133000", "OPEN"]],
    )
    rows, summary = run_program()
    assert REPORT.read_text().splitlines()[0] == "release_id,hold_id,car_id,yard_id,cargo_class,amount,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["cargo_class"] for row in rows] == ["HAZ", "DRY", "REF"]
    assert summary == {"matched_count": 3, "matched_amount": 102, "unmatched_count": 0, "unmatched_amount": 0}


def test_unknown_cargo_class_stays_unmatched_inside_open_window():
    """The M3 window rules must not weaken the canonical cargo_class gate."""
    build_program()
    write_inputs(
        [["SRC-BAD-WINDOW", "BOX-BAD", "G-3", "BAD", "90", "20260528150000", "HELD", "LANE-B"]],
        [["REL-BAD-WINDOW", "SRC-BAD-WINDOW", "BOX-BAD", "G-3", "BAD", "90", "20260528150100", "OVERRIDE", "LANE-B"]],
        [["G-3", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["cargo_class"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 90}


def test_release_after_window_close_is_unmatched():
    """A release after the matching window close_ts must stay unmatched."""
    build_program()
    write_inputs(
        [["SRC-WINDOW-CLOSE", "BOX-WINDOW-CLOSE", "G-3", "REF", "95", "20260528150000", "HELD", "LANE-C"]],
        [["REL-WINDOW-CLOSE", "SRC-WINDOW-CLOSE", "BOX-WINDOW-CLOSE", "G-3", "SE", "95", "20260528153100", "OVERRIDE", "LANE-C"]],
        [["G-3", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["cargo_class"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 95}
def test_window_state_malformed_times_latest_candidate_and_order():
    """Closed windows, malformed timestamps, latest source timestamp selection among duplicate source-id rows, and blank unmatched type fields should hold."""
    build_program()
    write_inputs(
        [
            ["SRC-WIN-1", "PARTY-1", "S-O", "HAZ", "1", "20260528150000", "HELD", "L1"],
            ["SRC-WIN-2", "PARTY-2", "S-C", "HAZ", "2", "20260528150000", "HELD", "L2"],
            ["SRC-WIN-3", "PARTY-3", "S-M", "DRY", "3", "bad-time", "HELD", "L3"],
            ["SRC-DUPE", "PARTY-4", "S-O", "REF", "4", "20260528150100", "HELD", "L4"],
            ["SRC-DUPE", "PARTY-4", "S-O", "REF", "4", "20260528150200", "HELD", "L4"],
        ],
        [
            ["ACT-1", "SRC-WIN-1", "PARTY-1", "S-O", "HAZ", "1", "20260528150500", "RELEASE", "L1"],
            ["ACT-2", "SRC-WIN-2", "PARTY-2", "S-C", "HAZ", "2", "20260528150500", "RELEASE", "L2"],
            ["ACT-3", "SRC-WIN-3", "PARTY-3", "S-M", "DRY", "3", "20260528150500", "RECALL", "L3"],
            ["ACT-4", "SRC-DUPE", "PARTY-4", "S-O", "REF", "4", "20260528150600", "OVERRIDE", "L4"],
        ],
        [["S-O", "20260528145900", "20260528153000", "OPEN"], ["S-C", "20260528145900", "20260528153000", "CLOSED"], ["S-M", "bad-time", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["release_id"] for row in rows] == ["ACT-1", "ACT-2", "ACT-3", "ACT-4"]
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert [row["cargo_class"] for row in rows] == ["HAZ", "", "", "REF"]
    assert summary == {"matched_count": 2, "matched_amount": 5, "unmatched_count": 2, "unmatched_amount": 5}

def test_non_numeric_release_timestamp_stays_unmatched():
    """A correction with non-numeric release_ts must stay unmatched even inside an OPEN window."""
    build_program()
    write_inputs(
        [["SRC-REL-BAD", "PARTY-1", "S-1", "REF", "15", "20260528140000", "HELD", "L1"]],
        [["ACT-REL-BAD", "SRC-REL-BAD", "PARTY-1", "S-1", "SE", "15", "bad-ts", "RELEASE", "L1"]],
        [["S-1", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["cargo_class"] == ""
    assert summary["matched_count"] == 0
