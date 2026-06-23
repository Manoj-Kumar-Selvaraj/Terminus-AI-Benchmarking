"""Verifier tests for realtime warehouse dock hold release reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "dock_holds.csv"
ACTION = APP / "data" / "dock_releases.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "dock_release_report.csv"
SUMMARY = APP / "out" / "dock_release_summary.txt"


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
    write_csv(SOURCE, ["hold_id", "shipment_id", "dock_id", "load_type", "amount", "hold_ts", "status", "door"], source)
    write_csv(ACTION, ["release_id", "hold_id", "shipment_id", "dock_id", "load_type", "amount", "release_ts", "reason", "door"], action)
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
            ["SRC-GATE-1", "PARTY-1", "S-G", "LTL", "10", "20260528140000", "STAGED", "L1"],
            ["SRC-GATE-2", "PARTY-2", "S-G", "LTL", "20", "20260528140100", "BAD", "L2"],
            ["SRC-GATE-3", "PARTY-3", "S-G", "FTL", "30", "20260528140200", "STAGED", "L3"],
            ["SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140300", "STAGED", "L4"],
        ],
        [
            ["ACT-A", "SRC-GATE-1", "PARTY-1", "S-G", "LTL", "10", "20260528140500", "SHIP", "L1"],
            ["ACT-B", "SRC-GATE-1", "PARTY-1", "S-G", "LTL", "10", "20260528140600", "SHIP", "L1"],
            ["ACT-C", "SRC-GATE-2", "PARTY-2", "S-G", "LTL", "20", "20260528140700", "SHIP", "L2"],
            ["ACT-D", "SRC-GATE-3", "PARTY-X", "S-G", "FTL", "30", "20260528140700", "SHORT", "L3"],
            ["ACT-E", "SRC-GATE-3", "PARTY-3", "S-G", "FTL", "31", "20260528140700", "SHORT", "L3"],
            ["ACT-F", "SRC-GATE-3", "PARTY-3", "S-G", "FTL", "30", "20260528135959", "SHORT", "L3"],
            ["ACT-G", "SRC-GATE-3", "PARTY-3", "S-G", "FTL", "30", "20260528140700", "INFO", "L3"],
            ["ACT-H", "SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140700", "OVERRIDE", "L4"],
        ],
        [["S-G", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert rows[1]["load_type"] == ""
    assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 7, "unmatched_amount": 191}
def test_aliases_full_keys_and_canonical_output():
    """Aliases should match full source keys and emit canonical load_type values."""
    build_program()
    write_inputs(
        [
            ["SRC-100000001", "PARTY-1", "S-A", "LTL", "12", "20260528120500", "STAGED", "LOC-1"],
            ["SRC-100000002", "PARTY-2", "S-A", "FTL", "34", "20260528120600", "STAGED", "LOC-2"],
            ["SRC-100000003", "PARTY-3", "S-B", "PARCEL", "56", "20260528130500", "STAGED", "LOC-3"],
        ],
        [
            ["ACT-1", "SRC-100000001", "PARTY-1", "S-A", "HR", "12", "20260528121000", "SHIP", "LOC-1"],
            ["ACT-2", "SRC-100000002", "PARTY-2", "S-A", "QR", "34", "20260528121100", "SHORT", "LOC-2"],
            ["ACT-3", "SRC-100000003", "PARTY-3", "S-B", "CC", "56", "20260528131000", "OVERRIDE", "LOC-3"],
        ],
        [["S-A", "20260528120000", "20260528123000", "OPEN"], ["S-B", "20260528130000", "20260528133000", "OPEN"]],
    )
    rows, summary = run_program()
    assert REPORT.read_text().splitlines()[0] == "release_id,hold_id,shipment_id,dock_id,load_type,amount,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["load_type"] for row in rows] == ["LTL", "FTL", "PARCEL"]
    assert summary == {"matched_count": 3, "matched_amount": 102, "unmatched_count": 0, "unmatched_amount": 0}


def test_unknown_load_type_stays_unmatched_even_when_both_sides_match():
    """Shared unknown load_type values must not match from milestone 2 onward."""
    build_program()
    write_inputs(
        [["SRC-UNK-1", "PARTY-U", "S-U", "BAD", "18", "20260528170000", "STAGED", "L1"]],
        [["ACT-UNK-1", "SRC-UNK-1", "PARTY-U", "S-U", "BAD", "18", "20260528170100", "SHIP", "L1"]],
        [["S-U", "20260528165900", "20260528173000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert summary["matched_count"] == 0
