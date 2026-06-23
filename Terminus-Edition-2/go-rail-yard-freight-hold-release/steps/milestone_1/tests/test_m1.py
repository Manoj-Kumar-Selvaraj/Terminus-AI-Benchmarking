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


def test_active_status_is_required():
    """A source hold with any status other than HELD must not match."""
    build_program()
    write_inputs(
        [["SRC-STATUS", "BOX-1", "G-1", "HAZ", "25", "20260528100000", "NOT_OPENED", "LANE-1"]],
        [["REL-STATUS", "SRC-STATUS", "BOX-1", "G-1", "HAZ", "25", "20260528100100", "RELEASE", "LANE-1"]],
        [["G-1", "20260528090000", "20260528110000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["cargo_class"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 25}


def test_reason_must_be_allowed():
    """A release reason outside the allowed milestone 1 set must not match."""
    build_program()
    write_inputs(
        [["SRC-REASON", "BOX-2", "G-1", "DRY", "35", "20260528100000", "HELD", "LANE-2"]],
        [["REL-REASON", "SRC-REASON", "BOX-2", "G-1", "DRY", "35", "20260528100100", "INFO", "LANE-2"]],
        [["G-1", "20260528090000", "20260528110000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["cargo_class"] == ""
    assert summary["unmatched_amount"] == 35


def test_consumption_prevents_second_release_match():
    """A matched hold row must be consumed so a later duplicate release stays unmatched."""
    build_program()
    write_inputs(
        [["SRC-CONSUME", "BOX-3", "G-1", "HAZ", "45", "20260528100000", "HELD", "LANE-3"]],
        [
            ["REL-CONSUME-1", "SRC-CONSUME", "BOX-3", "G-1", "HAZ", "45", "20260528100100", "RELEASE", "LANE-3"],
            ["REL-CONSUME-2", "SRC-CONSUME", "BOX-3", "G-1", "HAZ", "45", "20260528100200", "RELEASE", "LANE-3"],
        ],
        [["G-1", "20260528090000", "20260528110000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert [row["cargo_class"] for row in rows] == ["HAZ", ""]
    assert summary == {"matched_count": 1, "matched_amount": 45, "unmatched_count": 1, "unmatched_amount": 45}

def test_non_numeric_timestamps_stay_unmatched():
    """Non-numeric hold_ts or release_ts values must reject matching."""
    build_program()
    write_inputs(
        [["SRC-BAD-TS", "PARTY-1", "S-1", "HAZ", "10", "bad-ts", "HELD", "L1"]],
        [["ACT-BAD-TS", "SRC-BAD-TS", "PARTY-1", "S-1", "HAZ", "10", "20260528140500", "RELEASE", "L1"]],
        [["S-1", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["cargo_class"] == ""
    assert summary["matched_count"] == 0
