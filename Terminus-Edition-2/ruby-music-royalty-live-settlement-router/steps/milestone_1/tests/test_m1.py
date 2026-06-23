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
            ["SRC-GATE-2", "PARTY-2", "S-G", "SELLER", "20", "20260528140100", "BAD", "L2"],
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
    assert REPORT.read_text().splitlines()[0] == "settlement_id,play_id,payee_id,trust_id,right_type,amount,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[0] == {"settlement_id": "SYNT-A", "play_id": "SRC-GATE-1", "payee_id": "PARTY-1", "trust_id": "S-G", "right_type": "SELLER", "amount": "10", "reason": "CLOSE", "status": "MATCHED"}
    assert rows[-1] == {"settlement_id": "SYNT-J", "play_id": "SRC-GATE-10", "payee_id": "PARTY-1", "trust_id": "S-G", "right_type": "SELLER", "amount": "10", "reason": "PAY", "status": "MATCHED"}
    assert all(row["right_type"] == "" for row in rows[1:-1])
    assert summary == {"matched_count": 2, "matched_amount": 20, "unmatched_count": 8, "unmatched_amount": 241}


def test_open_window_state_is_case_insensitive():
    """Lowercase or mixed-case OPEN window state values must still enable matching."""
    build_program()
    write_inputs(
        [["SRC-CI", "PARTY-CI", "S-CI", "SELLER", "25", "20260528140000", "HELD", "L1"]],
        [["SYNT-CI", "SRC-CI", "PARTY-CI", "S-CI", "SELLER", "25", "20260528140500", "CLOSE", "L1"]],
        [["S-CI", "20260528135900", "20260528143000", "open"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["right_type"] == "SELLER"
    assert summary == {"matched_count": 1, "matched_amount": 25, "unmatched_count": 0, "unmatched_amount": 0}
