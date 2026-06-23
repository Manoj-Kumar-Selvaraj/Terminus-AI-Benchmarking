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
            ["SRC-100000001", "PARTY-1", "S-A", " slr ", "12", "20260528120500", "HELD", "LOC-1"],
            ["SRC-100000002", "PARTY-2", "S-A", " broker ", "34", "20260528120600", "HELD", "LOC-2"],
            ["SRC-100000003", "PARTY-3", "S-B", "TAX", "56", "20260528130500", "HELD", "LOC-3"],
        ],
        [
            ["SYNT-1", "SRC-100000001", "PARTY-1", "S-A", " seller ", "12", "20260528121000", "CLOSE", "LOC-1"],
            ["SYNT-2", "SRC-100000002", "PARTY-2", "S-A", " bRk ", "34", "20260528121100", "CORRECT", "LOC-2"],
            ["SYNT-3", "SRC-100000003", "PARTY-3", "S-B", " taxauth ", "56", "20260528131000", "PAY", "LOC-3"],
        ],
        [["S-A", "20260528120000", "20260528123000", "OPEN"], ["S-B", "20260528130000", "20260528133000", "OPEN"]],
    )
    rows, summary = run_program()
    assert REPORT.read_text().splitlines()[0] == "settlement_id,play_id,payee_id,trust_id,right_type,amount,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["right_type"] for row in rows] == ["SELLER", "BROKER", "TAX"]
    assert summary == {"matched_count": 3, "matched_amount": 102, "unmatched_count": 0, "unmatched_amount": 0}


def test_source_holds_alias_with_canonical_settlement_right_type():
    """Aliases on holds rows must normalize before matching canonical settlement right_type values."""
    build_program()
    write_inputs(
        [
            ["SRC-2001", "PARTY-1", "S-A", "SLR", "12", "20260528120500", "HELD", "LOC-1"],
            ["SRC-2002", "PARTY-2", "S-A", "BRK", "34", "20260528120600", "HELD", "LOC-2"],
        ],
        [
            ["SYNT-1", "SRC-2001", "PARTY-1", "S-A", "SELLER", "12", "20260528121000", "CLOSE", "LOC-1"],
            ["SYNT-2", "SRC-2002", "PARTY-2", "S-A", "BROKER", "34", "20260528121100", "CORRECT", "LOC-2"],
        ],
        [["S-A", "20260528120000", "20260528123000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["right_type"] for row in rows] == ["SELLER", "BROKER"]
    assert summary["matched_count"] == 2


def test_alias_hold_with_bad_status_stays_unmatched():
    """Alias normalization must not bypass the HELD status gate."""
    build_program()
    write_inputs(
        [["SRC-BAD", "PARTY-BAD", "S-BAD", "SLR", "40", "20260528140000", "BAD", "L1"]],
        [["SYNT-BAD", "SRC-BAD", "PARTY-BAD", "S-BAD", "SELLER", "40", "20260528140500", "CLOSE", "L1"]],
        [["S-BAD", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["right_type"] == ""
    assert summary["unmatched_count"] == 1
