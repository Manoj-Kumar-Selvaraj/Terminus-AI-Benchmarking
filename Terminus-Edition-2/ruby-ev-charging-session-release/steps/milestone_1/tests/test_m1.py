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


def test_full_session_id_required():
    """A correction must not match when only the leading session_id prefix overlaps."""
    build_program()
    write_inputs(
        [
            ["SRC-PFX-001", "PARTY-1", "S-P", "LEVEL2", "15", "20260528150000", "ACTIVE", "L1"],
            ["SRC-PFX-002", "PARTY-1", "S-P", "LEVEL2", "15", "20260528150100", "ACTIVE", "L1"],
        ],
        [
            ["ACT-PFX-1", "SRC-PFX-999", "PARTY-1", "S-P", "LEVEL2", "15", "20260528150500", "STOP", "L1"],
            ["ACT-PFX-2", "SRC-PFX-002", "PARTY-1", "S-P", "LEVEL2", "15", "20260528150600", "STOP", "L1"],
        ],
        [["S-P", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert summary["matched_count"] == 1


def test_release_ts_before_plug_ts_is_rejected():
    """release_ts earlier than plug_ts must leave the correction unmatched."""
    build_program()
    write_inputs(
        [["SRC-EARLY-1", "PARTY-1", "S-E", "DCFC", "25", "20260528160000", "ACTIVE", "L1"]],
        [["ACT-EARLY-1", "SRC-EARLY-1", "PARTY-1", "S-E", "DCFC", "25", "20260528155959", "FAULT", "L1"]],
        [["S-E", "20260528155800", "20260528163000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["rate_plan"] == ""
    assert summary["matched_count"] == 0


def test_fleet_rate_plan_is_not_canonical_in_milestone_1():
    """FLEET is introduced by aliases later, so milestone 1 must reject it."""
    build_program()
    write_inputs(
        [["SRC-FLEET-M1", "PARTY-F", "S-F", "FLEET", "12", "20260528140000", "ACTIVE", "L1"]],
        [["ACT-FLEET-M1", "SRC-FLEET-M1", "PARTY-F", "S-F", "FLEET", "12", "20260528140500", "STOP", "L1"]],
        [["S-F", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["rate_plan"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 12}


def test_non_numeric_timestamps_stay_unmatched():
    """Non-numeric plug_ts or release_ts values must reject matching."""
    build_program()
    write_inputs(
        [["SRC-BAD-TS", "PARTY-1", "S-1", "LEVEL2", "10", "bad-ts", "ACTIVE", "L1"]],
        [["ACT-BAD-TS", "SRC-BAD-TS", "PARTY-1", "S-1", "LEVEL2", "10", "20260528140500", "STOP", "L1"]],
        [["S-1", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["rate_plan"] == ""
    assert summary["matched_count"] == 0
