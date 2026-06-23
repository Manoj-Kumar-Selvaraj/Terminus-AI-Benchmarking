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


def test_aliases_full_keys_and_canonical_output():
    """Aliases should match full source keys and emit canonical resource_type values."""
    build_program()
    write_inputs(
        [
            [
                "SRC-100000001",
                "PARTY-1",
                "S-A",
                "LOAD",
                "12",
                "20260528120500",
                "CONFIRMED",
                "LOC-1",
            ],
            [
                "SRC-100000002",
                "PARTY-2",
                "S-A",
                "SOLAR",
                "34",
                "20260528120600",
                "CONFIRMED",
                "LOC-2",
            ],
            [
                "SRC-100000003",
                "PARTY-3",
                "S-B",
                "BATTERY",
                "56",
                "20260528130500",
                "CONFIRMED",
                "LOC-3",
            ],
        ],
        [
            [
                "ACT-1",
                "SRC-100000001",
                "PARTY-1",
                "S-A",
                "LD",
                "12",
                "20260528121000",
                "CURTAIL",
                "LOC-1",
            ],
            [
                "ACT-2",
                "SRC-100000002",
                "PARTY-2",
                "S-A",
                "QR",
                "34",
                "20260528121100",
                "BONUS",
                "LOC-2",
            ],
            [
                "ACT-3",
                "SRC-100000003",
                "PARTY-3",
                "S-B",
                "CC",
                "56",
                "20260528131000",
                "CORRECT",
                "LOC-3",
            ],
        ],
        [
            ["S-A", "20260528120000", "20260528123000", "OPEN"],
            ["S-B", "20260528130000", "20260528133000", "OPEN"],
        ],
    )
    rows, summary = run_program()
    assert (
        REPORT.read_text().splitlines()[0]
        == "settlement_id,parcel_id,meter_id,station_id,resource_type,amount,reason,status"
    )
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["resource_type"] for row in rows] == ["LOAD", "SOLAR", "BATTERY"]
    assert summary == {
        "matched_count": 3,
        "matched_amount": 102,
        "unmatched_count": 0,
        "unmatched_amount": 0,
    }


def test_window_state_malformed_times_latest_candidate_and_order():
    """Window eligibility, malformed times, latest candidate selection, order, and blank unmatched resource_type should hold."""
    build_program()
    write_inputs(
        [
            [
                "SRC-WIN-1",
                "PARTY-1",
                "S-O",
                "LOAD",
                "1",
                "20260528150000",
                "CONFIRMED",
                "L1",
            ],
            [
                "SRC-WIN-2",
                "PARTY-2",
                "S-C",
                "LOAD",
                "2",
                "20260528150000",
                "CONFIRMED",
                "L2",
            ],
            [
                "SRC-WIN-3",
                "PARTY-3",
                "S-M",
                "SOLAR",
                "3",
                "bad-time",
                "CONFIRMED",
                "L3",
            ],
            [
                "SRC-DPVE",
                "PARTY-4",
                "S-O",
                "BATTERY",
                "4",
                "20260528150100",
                "CONFIRMED",
                "L4",
            ],
            [
                "SRC-DPVE",
                "PARTY-4",
                "S-O",
                "BATTERY",
                "4",
                "20260528150200",
                "CONFIRMED",
                "L4",
            ],
        ],
        [
            [
                "ACT-1",
                "SRC-WIN-1",
                "PARTY-1",
                "S-O",
                "LOAD",
                "1",
                "20260528150500",
                "CURTAIL",
                "L1",
            ],
            [
                "ACT-2",
                "SRC-WIN-2",
                "PARTY-2",
                "S-C",
                "LOAD",
                "2",
                "20260528150500",
                "CURTAIL",
                "L2",
            ],
            [
                "ACT-3",
                "SRC-WIN-3",
                "PARTY-3",
                "S-M",
                "SOLAR",
                "3",
                "20260528150500",
                "BONUS",
                "L3",
            ],
            [
                "ACT-4",
                "SRC-DPVE",
                "PARTY-4",
                "S-O",
                "BATTERY",
                "4",
                "20260528150600",
                "CORRECT",
                "L4",
            ],
        ],
        [
            ["S-O", "20260528145900", "20260528153000", "OPEN"],
            ["S-C", "20260528145900", "20260528153000", "CLOS"],
            ["S-M", "bad-time", "20260528153000", "OPEN"],
        ],
    )
    rows, summary = run_program()
    assert [row["settlement_id"] for row in rows] == [
        "ACT-1",
        "ACT-2",
        "ACT-3",
        "ACT-4",
    ]
    assert [row["status"] for row in rows] == [
        "MATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "MATCHED",
    ]
    assert [row["resource_type"] for row in rows] == ["LOAD", "", "", "BATTERY"]
    assert summary == {
        "matched_count": 2,
        "matched_amount": 5,
        "unmatched_count": 2,
        "unmatched_amount": 5,
    }
