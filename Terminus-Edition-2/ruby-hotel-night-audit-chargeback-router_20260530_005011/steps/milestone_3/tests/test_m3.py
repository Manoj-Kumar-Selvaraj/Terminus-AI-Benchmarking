"""Verifier tests for realtime hotel night audit chargeback reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "folios.csv"
ACTION = APP / "data" / "chargebacks.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "chargeback_report.csv"
SUMMARY = APP / "out" / "chargeback_summary.txt"


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
    write_csv(SOURCE, ["folio_id", "guest_id", "property_id", "kind", "amount", "source_ts", "status", "location"], source)
    write_csv(ACTION, ["action_id", "folio_id", "guest_id", "property_id", "kind", "amount", "action_ts", "reason", "location"], action)
    write_csv(WINDOWS, ["property_id", "open_ts", "close_ts", "state"], windows)
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
            ["SRC-GATE-1", "PARTY-1", "S-G", "CARD", "10", "20260528140000", "POSTED", "L1"],
            ["SRC-GATE-2", "PARTY-2", "S-G", "CARD", "20", "20260528140100", "BAD", "L2"],
            ["SRC-GATE-3", "PARTY-3", "S-G", "CASH", "30", "20260528140200", "POSTED", "L3"],
            ["SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140300", "POSTED", "L4"],
        ],
        [
            ["ACT-A", "SRC-GATE-1", "PARTY-1", "S-G", "CARD", "10", "20260528140500", "DISPUTE", "L1"],
            ["ACT-B", "SRC-GATE-1", "PARTY-1", "S-G", "CARD", "10", "20260528140600", "DISPUTE", "L1"],
            ["ACT-C", "SRC-GATE-2", "PARTY-2", "S-G", "CARD", "20", "20260528140700", "DISPUTE", "L2"],
            ["ACT-D", "SRC-GATE-3", "PARTY-X", "S-G", "CASH", "30", "20260528140700", "DUPLICATE", "L3"],
            ["ACT-E", "SRC-GATE-3", "PARTY-3", "S-G", "CASH", "31", "20260528140700", "DUPLICATE", "L3"],
            ["ACT-F", "SRC-GATE-3", "PARTY-3", "S-G", "CASH", "30", "20260528135959", "DUPLICATE", "L3"],
            ["ACT-G", "SRC-GATE-3", "PARTY-3", "S-G", "CASH", "30", "20260528140700", "INFO", "L3"],
            ["ACT-H", "SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140700", "NOAUTH", "L4"],
        ],
        [["S-G", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert rows[1]["kind"] == ""
    assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 7, "unmatched_amount": 191}
def test_aliases_full_keys_and_canonical_output():
    """Aliases should match full source keys and emit canonical kind values."""
    build_program()
    write_inputs(
        [
            ["SRC-100000001", "PARTY-1", "S-A", "CARD", "12", "20260528120500", "POSTED", "LOC-1"],
            ["SRC-100000002", "PARTY-2", "S-A", "CASH", "34", "20260528120600", "POSTED", "LOC-2"],
            ["SRC-100000003", "PARTY-3", "S-B", "POINTS", "56", "20260528130500", "POSTED", "LOC-3"],
        ],
        [
            ["ACT-1", "SRC-100000001", "PARTY-1", "S-A", "CC", "12", "20260528121000", "DISPUTE", "LOC-1"],
            ["ACT-2", "SRC-100000002", "PARTY-2", "S-A", "CSH", "34", "20260528121100", "DUPLICATE", "LOC-2"],
            ["ACT-3", "SRC-100000003", "PARTY-3", "S-B", "PTS", "56", "20260528131000", "NOAUTH", "LOC-3"],
        ],
        [["S-A", "20260528120000", "20260528123000", "OPEN"], ["S-B", "20260528130000", "20260528133000", "OPEN"]],
    )
    rows, summary = run_program()
    assert REPORT.read_text().splitlines()[0] == "action_id,folio_id,guest_id,property_id,kind,amount,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["kind"] for row in rows] == ["CARD", "CASH", "POINTS"]
    assert summary == {"matched_count": 3, "matched_amount": 102, "unmatched_count": 0, "unmatched_amount": 0}
def test_window_state_malformed_times_latest_candidate_and_order():
    """Window eligibility, malformed times, latest candidate selection, order, and blank unmatched kind should hold."""
    build_program()
    write_inputs(
        [
            ["SRC-WIN-1", "PARTY-1", "S-O", "CARD", "1", "20260528150000", "POSTED", "L1"],
            ["SRC-WIN-2", "PARTY-2", "S-C", "CARD", "2", "20260528150000", "POSTED", "L2"],
            ["SRC-WIN-3", "PARTY-3", "S-M", "CASH", "3", "bad-time", "POSTED", "L3"],
            ["SRC-DUPE", "PARTY-4", "S-O", "POINTS", "4", "20260528150100", "POSTED", "L4"],
            ["SRC-DUPE", "PARTY-4", "S-O", "POINTS", "4", "20260528150200", "POSTED", "L4"],
            ["SRC-LOC", "PARTY-5", "S-O", "CARD", "6", "20260528150300", "POSTED", "L-ORIG"],
            ["SRC-LATE", "PARTY-6", "S-O", "CARD", "7", "20260528150400", "POSTED", "L6"],
            ["SRC-MISS", "PARTY-7", "S-N", "CASH", "8", "20260528150500", "POSTED", "L7"],
        ],
        [
            ["ACT-1", "SRC-WIN-1", "PARTY-1", "S-O", "CARD", "1", "20260528150500", "DISPUTE", "L1"],
            ["ACT-2", "SRC-WIN-2", "PARTY-2", "S-C", "CARD", "2", "20260528150500", "DISPUTE", "L2"],
            ["ACT-3", "SRC-WIN-3", "PARTY-3", "S-M", "CASH", "3", "20260528150500", "DUPLICATE", "L3"],
            ["ACT-4", "SRC-DUPE", "PARTY-4", "S-O", "POINTS", "4", "20260528150600", "NOAUTH", "L4"],
            ["ACT-5", "SRC-LOC", "PARTY-5", "S-O", "CARD", "6", "20260528150600", "DISPUTE", "L-OTHER"],
            ["ACT-6", "SRC-LATE", "PARTY-6", "S-O", "CARD", "7", "20260528153100", "DISPUTE", "L6"],
            ["ACT-7", "SRC-MISS", "PARTY-7", "S-N", "CASH", "8", "20260528150600", "DUPLICATE", "L7"],
        ],
        [["S-O", "20260528145900", "20260528153000", "OPEN"], ["S-C", "20260528145900", "20260528153000", "CLOS"], ["S-M", "bad-time", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["action_id"] for row in rows] == ["ACT-1", "ACT-2", "ACT-3", "ACT-4", "ACT-5", "ACT-6", "ACT-7"]
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert [row["kind"] for row in rows] == ["CARD", "", "", "POINTS", "", "", ""]
    assert summary == {"matched_count": 2, "matched_amount": 5, "unmatched_count": 5, "unmatched_amount": 26}
