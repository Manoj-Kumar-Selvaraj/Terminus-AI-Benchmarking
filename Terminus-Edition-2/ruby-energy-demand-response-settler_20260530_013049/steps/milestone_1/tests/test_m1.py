"""Verifier tests for realtime energy demand response settlement."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "events.csv"
ACTION = APP / "data" / "settlements.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "cod_demand_response_report.csv"
SUMMARY = APP / "out" / "cod_demand_response_summary.txt"


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
    write_csv(
        SOURCE,
        [
            "parcel_id",
            "meter_id",
            "station_id",
            "resource_type",
            "amount",
            "event_ts",
            "status",
            "feeder",
        ],
        source,
    )
    write_csv(
        ACTION,
        [
            "settlement_id",
            "parcel_id",
            "meter_id",
            "station_id",
            "resource_type",
            "amount",
            "settle_ts",
            "reason",
            "feeder",
        ],
        action,
    )
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
            [
                "SRC-GATE-1",
                "PARTY-1",
                "S-G",
                "LOAD",
                "10",
                "20260528140000",
                "CONFIRMED",
                "L1",
            ],
            [
                "SRC-GATE-2",
                "PARTY-2",
                "S-G",
                "LOAD",
                "20",
                "20260528140100",
                "BAD",
                "L2",
            ],
            [
                "SRC-GATE-3",
                "PARTY-3",
                "S-G",
                "SOLAR",
                "30",
                "20260528140200",
                "CONFIRMED",
                "L3",
            ],
            [
                "SRC-GATE-4",
                "PARTY-4",
                "S-G",
                "BAD",
                "40",
                "20260528140300",
                "CONFIRMED",
                "L4",
            ],
        ],
        [
            [
                "ACT-A",
                "SRC-GATE-1",
                "PARTY-1",
                "S-G",
                "LOAD",
                "10",
                "20260528140500",
                "CURTAIL",
                "L1",
            ],
            [
                "ACT-B",
                "SRC-GATE-1",
                "PARTY-1",
                "S-G",
                "LOAD",
                "10",
                "20260528140600",
                "CURTAIL",
                "L1",
            ],
            [
                "ACT-C",
                "SRC-GATE-2",
                "PARTY-2",
                "S-G",
                "LOAD",
                "20",
                "20260528140700",
                "CURTAIL",
                "L2",
            ],
            [
                "ACT-D",
                "SRC-GATE-3",
                "PARTY-X",
                "S-G",
                "SOLAR",
                "30",
                "20260528140700",
                "BONUS",
                "L3",
            ],
            [
                "ACT-E",
                "SRC-GATE-3",
                "PARTY-3",
                "S-G",
                "SOLAR",
                "31",
                "20260528140700",
                "BONUS",
                "L3",
            ],
            [
                "ACT-F",
                "SRC-GATE-3",
                "PARTY-3",
                "S-G",
                "SOLAR",
                "30",
                "20260528135959",
                "BONUS",
                "L3",
            ],
            [
                "ACT-G",
                "SRC-GATE-3",
                "PARTY-3",
                "S-G",
                "SOLAR",
                "30",
                "20260528140700",
                "INFO",
                "L3",
            ],
            [
                "ACT-H",
                "SRC-GATE-4",
                "PARTY-4",
                "S-G",
                "BAD",
                "40",
                "20260528140700",
                "CORRECT",
                "L4",
            ],
            [
                "ACT-I",
                "SRC-GATE-3",
                "PARTY-3",
                "S-G",
                "SOLAR",
                "30",
                "20260528140700",
                "BONUS",
                "WRONG-FEEDER",
            ],
        ],
        [["S-G", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == [
        "MATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
    ]
    assert rows[1]["resource_type"] == ""
    assert summary == {
        "matched_count": 1,
        "matched_amount": 10,
        "unmatched_count": 8,
        "unmatched_amount": 221,
    }
