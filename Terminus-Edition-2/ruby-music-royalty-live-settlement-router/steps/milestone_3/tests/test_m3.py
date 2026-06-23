"""Verifier tests for realtime music royalty live settlement reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "holds.csv"
SETTLEMENTS_CSV = APP / "data" / "settlements.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "royalty_settlement_report.csv"
SUMMARY = APP / "out" / "royalty_settlement_summary.txt"


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
    write_csv(SOURCE, ["play_id", "payee_id", "trust_id", "right_type", "amount", "play_ts", "status", "market"], source)
    write_csv(SETTLEMENTS_CSV, ["settlement_id", "play_id", "payee_id", "trust_id", "right_type", "amount", "settle_ts", "reason", "market"], action)
    write_csv(WINDOWS, ["trust_id", "open_ts", "close_ts", "state"], windows)
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
            ["SRC-GATE-1", "PARTY-1", "S-G", "SELLER", "010", "20260528140000", "HELD", "L1"],
            ["SRC-GATE-10", "PARTY-1", "S-G", "SELLER", "010", "20260528140100", "HELD", "L1"],
            ["SRC-GATE-2", "PARTY-2", "S-G", "SELLER", "20", "20260528140200", "BAD", "L2"],
            ["SRC-GATE-3", "PARTY-3", "S-G", "BROKER", "30", "20260528140200", "HELD", "L3"],
            ["SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140300", "HELD", "L4"],
            ["SRC-GATE-5", "PARTY-5", "S-G", "SELLER", "50", "not-a-time", "HELD", "L5"],
        ],
        [
            ["SYNT-A", "SRC-GATE-1", "PARTY-1", "S-G", "SELLER", "10", "20260528140500", "CLOSE", "L1"],
            ["SYNT-B", "SRC-GATE-1", "PARTY-1", "S-G", "SELLER", "10", "20260528140600", "CLOSE", "L1"],
            ["SYNT-C", "SRC-GATE-2", "PARTY-2", "S-G", "SELLER", "20", "20260528140700", "CLOSE", "L2"],
            ["SYNT-D", "SRC-GATE-3", "PARTY-X", "S-G", "BROKER", "30", "20260528140700", "CORRECT", "L3"],
            ["SYNT-E", "SRC-GATE-3", "PARTY-3", "S-G", "BROKER", "31", "20260528140700", "CORRECT", "L3"],
            ["SYNT-F", "SRC-GATE-3", "PARTY-3", "S-G", "BROKER", "30", "20260528135959", "CORRECT", "L3"],
            ["SYNT-G", "SRC-GATE-3", "PARTY-3", "S-G", "BROKER", "30", "20260528140700", "INFO", "L3"],
            ["SYNT-H", "SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140700", "PAY", "L4"],
            ["SYNT-I", "SRC-GATE-5", "PARTY-5", "S-G", "SELLER", "50", "20260528140700", "PAY", "L5"],
            ["SYNT-J", "SRC-GATE-10", "PARTY-1", "S-G", "SELLER", "10", "20260528140800", "PAY", "L1"],
        ],
        [["S-G", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert all(row["right_type"] == "" for row in rows[1:-1])
    assert summary == {"matched_count": 2, "matched_amount": 20, "unmatched_count": 8, "unmatched_amount": 241}
def test_aliases_full_keys_and_canonical_output():
    """Aliases should match full source keys and emit canonical right_type values."""
    build_program()
    write_inputs(
        [
            ["SRC-100000001", "PARTY-1", "S-A", "SELLER", "12", "20260528120500", "HELD", "LOC-1"],
            ["SRC-100000002", "PARTY-2", "S-A", "BROKER", "34", "20260528120600", "HELD", "LOC-2"],
            ["SRC-100000003", "PARTY-3", "S-B", "TAX", "56", "20260528130500", "HELD", "LOC-3"],
        ],
        [
            ["SYNT-1", "SRC-100000001", "PARTY-1", "S-A", "SLR", "12", "20260528121000", "CLOSE", "LOC-1"],
            ["SYNT-2", "SRC-100000002", "PARTY-2", "S-A", "BRK", "34", "20260528121100", "CORRECT", "LOC-2"],
            ["SYNT-3", "SRC-100000003", "PARTY-3", "S-B", "TAXAUTH", "56", "20260528131000", "PAY", "LOC-3"],
        ],
        [["S-A", "20260528120000", "20260528123000", "OPEN"], ["S-B", "20260528130000", "20260528133000", "OPEN"]],
    )
    rows, summary = run_program()
    assert REPORT.read_text().splitlines()[0] == "settlement_id,play_id,payee_id,trust_id,right_type,amount,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["right_type"] for row in rows] == ["SELLER", "BROKER", "TAX"]
    assert summary == {"matched_count": 3, "matched_amount": 102, "unmatched_count": 0, "unmatched_amount": 0}
def test_window_state_malformed_times_latest_candidate_and_order():
    """Window eligibility, malformed times, latest candidate selection, order, and blank unmatched right_type should hold."""
    build_program()
    write_inputs(
        [
            ["SRC-WIN-1", "PARTY-1", "S-O", "SELLER", "1", "20260528150000", "HELD", "L1"],
            ["SRC-WIN-2", "PARTY-2", "S-C", "SELLER", "2", "20260528150000", "HELD", "L2"],
            ["SRC-WIN-3", "PARTY-3", "S-M", "BROKER", "3", "bad-time", "HELD", "L3"],
            ["SRC-DUPE", "PARTY-4", "S-O", "SELLER", "4", "20260528150100", "HELD", "L4"],
            ["SRC-DUPE", "PARTY-4", "S-O", "BROKER", "4", "20260528150200", "HELD", "L4"],
            ["SRC-DUPE", "PARTY-4", "S-O", "TAX", "4", "20260528150200", "HELD", "L4"],
            ["SRC-LATE", "PARTY-5", "S-O", "SELLER", "5", "20260528150300", "HELD", "L5"],
            ["SRC-ORDER", "PARTY-6", "S-O", "SELLER", "6", "20260528150100", "HELD", "L6"],
            ["SRC-ORDER", "PARTY-6", "S-O", "SELLER", "6", "20260528150300", "HELD", "L6"],
        ],
        [
            ["SYNT-1", "SRC-WIN-1", "PARTY-1", "S-O", "SELLER", "1", "20260528150500", "CLOSE", "L1"],
            ["SYNT-2", "SRC-WIN-2", "PARTY-2", "S-C", "SELLER", "2", "20260528150500", "CLOSE", "L2"],
            ["SYNT-3", "SRC-WIN-3", "PARTY-3", "S-M", "BROKER", "3", "20260528150500", "CORRECT", "L3"],
            ["SYNT-4", "SRC-DUPE", "PARTY-4", "S-O", "BROKER", "4", "20260528150600", "PAY", "L4"],
            ["SYNT-5", "SRC-LATE", "PARTY-5", "S-O", "SELLER", "5", "20260528153100", "CLOSE", "L5"],
            ["SYNT-6", "SRC-ORDER", "PARTY-6", "S-O", "SELLER", "6", "20260528150600", "PAY", "L6"],
            ["SYNT-7", "SRC-ORDER", "PARTY-6", "S-O", "SELLER", "6", "20260528150200", "PAY", "L6"],
        ],
        [["S-O", "20260528145900", "20260528153000", "OPEN"], ["S-C", "20260528145900", "20260528153000", "CLOS"], ["S-M", "bad-time", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["settlement_id"] for row in rows] == ["SYNT-1", "SYNT-2", "SYNT-3", "SYNT-4", "SYNT-5", "SYNT-6", "SYNT-7"]
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "MATCHED", "UNMATCHED", "MATCHED", "MATCHED"]
    assert [row["right_type"] for row in rows] == ["SELLER", "", "", "BROKER", "", "SELLER", "SELLER"]
    assert summary == {"matched_count": 4, "matched_amount": 17, "unmatched_count": 3, "unmatched_amount": 10}


def test_equal_timestamp_candidates_use_source_row_order_and_consumption():
    """Equal source timestamp candidates should consume rows in source input order."""
    build_program()
    write_inputs(
        [
            ["SRC-TIE", "PARTY-T", "S-O", "SELLER", "6", "20260528150100", "HELD", "L-T"],
            ["SRC-TIE", "PARTY-T", "S-O", "SLR", "6", "20260528150100", "HELD", "L-T"],
        ],
        [
            ["SYNT-T1", "SRC-TIE", "PARTY-T", "S-O", "SELLER", "6", "20260528150500", "PAY", "L-T"],
            ["SYNT-T2", "SRC-TIE", "PARTY-T", "S-O", "SLR", "6", "20260528150600", "PAY", "L-T"],
            ["SYNT-T3", "SRC-TIE", "PARTY-T", "S-O", "SELLER", "6", "20260528150700", "PAY", "L-T"],
        ],
        [["S-O", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["settlement_id"] for row in rows] == ["SYNT-T1", "SYNT-T2", "SYNT-T3"]
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["right_type"] for row in rows] == ["SELLER", "SELLER", ""]
    assert summary == {"matched_count": 2, "matched_amount": 12, "unmatched_count": 1, "unmatched_amount": 6}


def test_invalid_settlement_right_type_rejects_valid_source_row():
    """A valid source right_type must not match an unknown settlement-side right_type."""
    build_program()
    write_inputs(
        [["SRC-ACTION-BAD", "PARTY-B", "S-O", "SELLER", "8", "20260528150100", "HELD", "L-B"]],
        [["SYNT-ACTION-BAD", "SRC-ACTION-BAD", "PARTY-B", "S-O", "BAD", "8", "20260528150600", "PAY", "L-B"]],
        [["S-O", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["right_type"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 8}
