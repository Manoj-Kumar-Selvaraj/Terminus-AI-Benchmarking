"""Verifier tests for realtime pharmacy coldchain exception routing reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
GO = Path("/usr/local/go/bin/go")
BIN = APP / "build" / "reconcile"
SOURCE = APP / "data" / "accessions.csv"
ACTION = APP / "data" / "exceptions.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "coldchain_exception_report.csv"
SUMMARY = APP / "out" / "coldchain_exception_summary.txt"


def build_program():
    """Compile the Go reconciler and run the batch script."""
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
    write_csv(SOURCE, ["shipment_id", "pharmacy_id", "chain_id", "package_type", "amount", "scan_ts", "status", "depot"], source)
    write_csv(ACTION, ["exception_id", "shipment_id", "pharmacy_id", "chain_id", "package_type", "amount", "exception_ts", "reason", "depot"], action)
    write_csv(WINDOWS, ["chain_id", "open_ts", "close_ts", "state"], windows)
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
            ["SRC-GATE-1", "PARTY-1", "S-G", "CHEM", "10", "20260528140000", "RECEIVED", "L1"],
            ["SRC-GATE-2", "PARTY-2", "S-G", "CHEM", "20", "20260528140100", "BAD", "L2"],
            ["SRC-GATE-3", "PARTY-3", "S-G", "HEME", "30", "20260528140200", "RECEIVED", "L3"],
            ["SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140300", "RECEIVED", "L4"],
        ],
        [
            ["ACT-A", "SRC-GATE-1", "PARTY-1", "S-G", "CHEM", "10", "20260528140500", "SPLIT", "L1"],
            ["ACT-B", "SRC-GATE-1", "PARTY-1", "S-G", "CHEM", "10", "20260528140600", "SPLIT", "L1"],
            ["ACT-C", "SRC-GATE-2", "PARTY-2", "S-G", "CHEM", "20", "20260528140700", "SPLIT", "L2"],
            ["ACT-D", "SRC-GATE-3", "PARTY-X", "S-G", "HEME", "30", "20260528140700", "TEMPBREACH", "L3"],
            ["ACT-E", "SRC-GATE-3", "PARTY-3", "S-G", "HEME", "31", "20260528140700", "TEMPBREACH", "L3"],
            ["ACT-F", "SRC-GATE-3", "PARTY-3", "S-G", "HEME", "30", "20260528135959", "TEMPBREACH", "L3"],
            ["ACT-G", "SRC-GATE-3", "PARTY-3", "S-G", "HEME", "30", "20260528140700", "INFO", "L3"],
            ["ACT-H", "SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140700", "RECHECK", "L4"],
        ],
        [["S-G", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert rows[1]["package_type"] == ""
    assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 7, "unmatched_amount": 191}
def test_aliases_full_keys_and_canonical_output():
    """Aliases should match full source keys and emit canonical package_type values."""
    build_program()
    write_inputs(
        [
            ["SRC-100000001", "PARTY-1", "S-A", "CHEM", "12", "20260528120500", "RECEIVED", "LOC-1"],
            ["SRC-100000002", "PARTY-2", "S-A", "HEME", "34", "20260528120600", "RECEIVED", "LOC-2"],
            ["SRC-100000003", "PARTY-3", "S-B", "MICRO", "56", "20260528130500", "RECEIVED", "LOC-3"],
        ],
        [
            ["ACT-1", "SRC-100000001", "PARTY-1", "S-A", "CMP", "12", "20260528121000", "SPLIT", "LOC-1"],
            ["ACT-2", "SRC-100000002", "PARTY-2", "S-A", "CBC", "34", "20260528121100", "TEMPBREACH", "LOC-2"],
            ["ACT-3", "SRC-100000003", "PARTY-3", "S-B", "CUL", "56", "20260528131000", "RECHECK", "LOC-3"],
        ],
        [["S-A", "20260528120000", "20260528123000", "OPEN"], ["S-B", "20260528130000", "20260528133000", "OPEN"]],
    )
    rows, summary = run_program()
    assert REPORT.read_text().splitlines()[0] == "exception_id,shipment_id,pharmacy_id,chain_id,package_type,amount,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["package_type"] for row in rows] == ["CHEM", "HEME", "MICRO"]
    assert summary == {"matched_count": 3, "matched_amount": 102, "unmatched_count": 0, "unmatched_amount": 0}
def test_window_state_malformed_times_latest_candidate_and_order():
    """Window eligibility, malformed times, latest candidate selection, order, and blank unmatched package_type should hold."""
    build_program()
    write_inputs(
        [
            ["SRC-WIN-1", "PARTY-1", "S-O", "CHEM", "1", "20260528150000", "RECEIVED", "L1"],
            ["SRC-WIN-2", "PARTY-2", "S-C", "CHEM", "2", "20260528150000", "RECEIVED", "L2"],
            ["SRC-WIN-3", "PARTY-3", "S-M", "HEME", "3", "bad-time", "RECEIVED", "L3"],
            ["SRC-DUPE", "PARTY-4", "S-O", "MICRO", "4", "20260528150100", "RECEIVED", "L4"],
            ["SRC-DUPE", "PARTY-4", "S-O", "MICRO", "4", "20260528150200", "RECEIVED", "L4"],
        ],
        [
            ["ACT-1", "SRC-WIN-1", "PARTY-1", "S-O", "CHEM", "1", "20260528150500", "SPLIT", "L1"],
            ["ACT-2", "SRC-WIN-2", "PARTY-2", "S-C", "CHEM", "2", "20260528150500", "SPLIT", "L2"],
            ["ACT-3", "SRC-WIN-3", "PARTY-3", "S-M", "HEME", "3", "20260528150500", "TEMPBREACH", "L3"],
            ["ACT-4", "SRC-DUPE", "PARTY-4", "S-O", "MICRO", "4", "20260528150600", "RECHECK", "L4"],
        ],
        [["S-O", "20260528145900", "20260528153000", "OPEN"], ["S-C", "20260528145900", "20260528153000", "CLOS"], ["S-M", "bad-time", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["exception_id"] for row in rows] == ["ACT-1", "ACT-2", "ACT-3", "ACT-4"]
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert [row["package_type"] for row in rows] == ["CHEM", "", "", "MICRO"]
    assert summary == {"matched_count": 2, "matched_amount": 5, "unmatched_count": 2, "unmatched_amount": 5}


def test_latest_scan_ts_wins_with_distinct_amounts():
    """Latest scan_ts must win when multiple unused rows qualify; distinct amounts block first-fit."""
    build_program()
    write_inputs(
        [
            ["SRC-L1", "PARTY-1", "S-W", "CHEM", "500", "20260528160000", "RECEIVED", "L1"],
            ["SRC-L2", "PARTY-1", "S-W", "CHEM", "800", "20260528170000", "RECEIVED", "L1"],
            ["SRC-L3", "PARTY-1", "S-W", "CHEM", "1200", "20260528180000", "RECEIVED", "L1"],
        ],
        [
            ["ACT-L1", "SRC-L3", "PARTY-1", "S-W", "CHEM", "1200", "20260528180500", "SPLIT", "L1"],
            ["ACT-L2", "SRC-L1", "PARTY-1", "S-W", "CHEM", "500", "20260528161000", "TEMPBREACH", "L1"],
        ],
        [["S-W", "20260528150000", "20260528190000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert summary == {
        "matched_count": 2,
        "matched_amount": 1700,
        "unmatched_count": 0,
        "unmatched_amount": 0,
    }


def test_equal_scan_ts_tie_uses_earliest_source_row():
    """When scan_ts ties, the earliest source input row must be consumed before later rows."""
    build_program()
    write_inputs(
        [
            ["SRC-EQTS-1", "PARTY-1", "S-W", "CHEM", "500", "20260528160000", "RECEIVED", "L1"],
            ["SRC-EQTS-1", "PARTY-1", "S-W", "HEME", "500", "20260528160000", "RECEIVED", "L1"],
        ],
        [
            ["ACT-EQTS-A", "SRC-EQTS-1", "PARTY-1", "S-W", "CHEM", "500", "20260528160500", "SPLIT", "L1"],
            ["ACT-EQTS-B", "SRC-EQTS-1", "PARTY-1", "S-W", "HEME", "500", "20260528160600", "RECHECK", "L1"],
        ],
        [["S-W", "20260528150000", "20260528190000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["package_type"] for row in rows] == ["CHEM", "HEME"]
    assert summary["matched_count"] == 2
