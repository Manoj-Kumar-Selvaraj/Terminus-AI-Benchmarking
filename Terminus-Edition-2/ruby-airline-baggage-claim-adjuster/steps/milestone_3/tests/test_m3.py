"""Verifier tests for realtime airline baggage claim adjustment reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "appointments.csv"
ACTION = APP / "data" / "adjustments.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "claim_route_report.csv"
SUMMARY = APP / "out" / "claim_route_summary.txt"


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
    write_csv(SOURCE, ["bag_id", "member_id", "site_id", "bag_type", "amount", "scan_ts", "status", "station"], source)
    write_csv(ACTION, ["adjustment_id", "bag_id", "member_id", "site_id", "bag_type", "amount", "adjust_ts", "reason", "station"], action)
    write_csv(WINDOWS, ["site_id", "open_ts", "close_ts", "state"], windows)
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
            ["SRC-GATE-1", "PARTY-1", "S-G", "CHECKED", "10", "20260528140000", "TAGGED", "L1"],
            ["SRC-GATE-2", "PARTY-2", "S-G", "CHECKED", "20", "20260528140100", "BAD", "L2"],
            ["SRC-GATE-3", "PARTY-3", "S-G", "OVERSIZE", "30", "20260528140200", "TAGGED", "L3"],
            ["SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140300", "TAGGED", "L4"],
        ],
        [
            ["ACT-A", "SRC-GATE-1", "PARTY-1", "S-G", "CHECKED", "10", "20260528140500", "DAMAGED", "L1"],
            ["ACT-B", "SRC-GATE-1", "PARTY-1", "S-G", "CHECKED", "10", "20260528140600", "DAMAGED", "L1"],
            ["ACT-C", "SRC-GATE-2", "PARTY-2", "S-G", "CHECKED", "20", "20260528140700", "DAMAGED", "L2"],
            ["ACT-D", "SRC-GATE-3", "PARTY-X", "S-G", "OVERSIZE", "30", "20260528140700", "DELAYED", "L3"],
            ["ACT-E", "SRC-GATE-3", "PARTY-3", "S-G", "OVERSIZE", "31", "20260528140700", "DELAYED", "L3"],
            ["ACT-F", "SRC-GATE-3", "PARTY-3", "S-G", "OVERSIZE", "30", "20260528135959", "DELAYED", "L3"],
            ["ACT-G", "SRC-GATE-3", "PARTY-3", "S-G", "OVERSIZE", "30", "20260528140700", "INFO", "L3"],
            ["ACT-H", "SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140700", "REROUTE", "L4"],
        ],
        [["S-G", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert rows[1]["bag_type"] == ""
    assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 7, "unmatched_amount": 191}
def test_aliases_full_keys_and_canonical_output():
    """Aliases should match full source keys and emit canonical bag_type values."""
    build_program()
    write_inputs(
        [
            ["SRC-100000001", "PARTY-1", "S-A", "CHECKED", "12", "20260528120500", "TAGGED", "LOC-1"],
            ["SRC-100000002", "PARTY-2", "S-A", "OVERSIZE", "34", "20260528120600", "TAGGED", "LOC-2"],
            ["SRC-100000003", "PARTY-3", "S-B", "SPORT", "56", "20260528130500", "TAGGED", "LOC-3"],
        ],
        [
            ["ACT-1", "SRC-100000001", "PARTY-1", "S-A", "PRIMARY", "12", "20260528121000", "DAMAGED", "LOC-1"],
            ["ACT-2", "SRC-100000002", "PARTY-2", "S-A", "OVERSIZEIAL", "34", "20260528121100", "DELAYED", "LOC-2"],
            ["ACT-3", "SRC-100000003", "PARTY-3", "S-B", "SPORTORATORY", "56", "20260528131000", "REROUTE", "LOC-3"],
        ],
        [["S-A", "20260528120000", "20260528123000", "OPEN"], ["S-B", "20260528130000", "20260528133000", "OPEN"]],
    )
    rows, summary = run_program()
    assert REPORT.read_text().splitlines()[0] == "adjustment_id,bag_id,member_id,site_id,bag_type,amount,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["bag_type"] for row in rows] == ["CHECKED", "OVERSIZE", "SPORT"]
    assert summary == {"matched_count": 3, "matched_amount": 102, "unmatched_count": 0, "unmatched_amount": 0}
def test_window_state_malformed_times_latest_candidate_and_order():
    """Window eligibility, malformed times, latest candidate selection, order, and blank unmatched bag_type should hold."""
    build_program()
    write_inputs(
        [
            ["SRC-WIN-1", "PARTY-1", "S-O", "CHECKED", "1", "20260528150000", "TAGGED", "L1"],
            ["SRC-WIN-2", "PARTY-2", "S-C", "CHECKED", "2", "20260528150000", "TAGGED", "L2"],
            ["SRC-WIN-3", "PARTY-3", "S-M", "OVERSIZE", "3", "bad-time", "TAGGED", "L3"],
            ["SRC-DUPE", "PARTY-4", "S-O", "SPORT", "4", "20260528150100", "TAGGED", "L4"],
            ["SRC-DUPE", "PARTY-4", "S-O", "SPORT", "4", "20260528150200", "TAGGED", "L4"],
        ],
        [
            ["ACT-1", "SRC-WIN-1", "PARTY-1", "S-O", "CHECKED", "1", "20260528150500", "DAMAGED", "L1"],
            ["ACT-2", "SRC-WIN-2", "PARTY-2", "S-C", "CHECKED", "2", "20260528150500", "DAMAGED", "L2"],
            ["ACT-3", "SRC-WIN-3", "PARTY-3", "S-M", "OVERSIZE", "3", "20260528150500", "DELAYED", "L3"],
            ["ACT-4", "SRC-DUPE", "PARTY-4", "S-O", "SPORT", "4", "20260528150600", "REROUTE", "L4"],
        ],
        [["S-O", "20260528145900", "20260528153000", "OPEN"], ["S-C", "20260528145900", "20260528153000", "CLOS"], ["S-M", "bad-time", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["adjustment_id"] for row in rows] == ["ACT-1", "ACT-2", "ACT-3", "ACT-4"]
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert [row["bag_type"] for row in rows] == ["CHECKED", "", "", "SPORT"]
    assert summary == {"matched_count": 2, "matched_amount": 5, "unmatched_count": 2, "unmatched_amount": 5}
