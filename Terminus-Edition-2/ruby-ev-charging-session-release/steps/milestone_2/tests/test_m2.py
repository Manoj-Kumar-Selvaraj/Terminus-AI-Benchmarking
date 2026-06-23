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


def test_unknown_rate_plan_stays_unmatched_even_when_both_sides_match():
    """Shared unknown rate_plan values must not match from milestone 2 onward."""
    build_program()
    write_inputs(
        [["SRC-UNK-1", "PARTY-U", "S-U", "BAD", "18", "20260528170000", "ACTIVE", "L1"]],
        [["ACT-UNK-1", "SRC-UNK-1", "PARTY-U", "S-U", "BAD", "18", "20260528170100", "STOP", "L1"]],
        [["S-U", "20260528165900", "20260528173000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert summary["matched_count"] == 0
