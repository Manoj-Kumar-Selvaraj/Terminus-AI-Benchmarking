"""Verifier tests for realtime cloud reservation burst credit reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "seat_events.csv"
ACTION = APP / "data" / "credits.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "seat_credit_report.csv"
SUMMARY = APP / "out" / "seat_credit_summary.txt"


def build_program():
    """No build step is required for the Ruby entrypoint."""
    pass


def write_csv(path, header, rows):
    """Write one CSV fixture."""
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(source, action, windows):
    """Overwrite all input files at runtime."""
    write_csv(SOURCE, ["event_id", "account_id", "reservation_id", "sku_type", "amount", "reserve_ts", "status", "region"], source)
    write_csv(ACTION, ["credit_id", "event_id", "account_id", "reservation_id", "sku_type", "amount", "credit_ts", "reason", "region"], action)
    write_csv(WINDOWS, ["reservation_id", "open_ts", "close_ts", "state"], windows)
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
            ["SRC-GATE-1", "PARTY-1", "S-G", "CPU", "10", "20260528140000", "ALLOCATED", "L1"],
            ["SRC-GATE-2", "PARTY-2", "S-G", "CPU", "20", "20260528140100", "BAD", "L2"],
            ["SRC-GATE-3", "PARTY-3", "S-G", "GPU", "30", "20260528140200", "ALLOCATED", "L3"],
            ["SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140300", "ALLOCATED", "L4"],
        ],
        [
            ["ACT-A", "SRC-GATE-1", "PARTY-1", "S-G", "CPU", "10", "20260528140500", "BURST", "L1"],
            ["ACT-B", "SRC-GATE-1", "PARTY-1", "S-G", "CPU", "10", "20260528140600", "BURST", "L1"],
            ["ACT-C", "SRC-GATE-2", "PARTY-2", "S-G", "CPU", "20", "20260528140700", "BURST", "L2"],
            ["ACT-D", "SRC-GATE-3", "PARTY-X", "S-G", "GPU", "30", "20260528140700", "RECLAIM", "L3"],
            ["ACT-M", "SRC-GATE-3", "PARTY-3", "S-G", "GPU", "31", "20260528140700", "RECLAIM", "L3"],
            ["ACT-F", "SRC-GATE-3", "PARTY-3", "S-G", "GPU", "30", "20260528135959", "RECLAIM", "L3"],
            ["ACT-G", "SRC-GATE-3", "PARTY-3", "S-G", "GPU", "30", "20260528140700", "INFO", "L3"],
            ["ACT-H", "SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140700", "CORRECT", "L4"],
        ],
        [["S-G", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert rows[1]["sku_type"] == ""
    assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 7, "unmatched_amount": 191}


def test_aliases_full_keys_and_canonical_output():
    """Aliases should match full source keys and emit canonical sku_type values."""
    build_program()
    write_inputs(
        [
            ["SRC-100000001", "PARTY-1", "S-A", "CPU", "12", "20260528120500", "ALLOCATED", "LOC-1"],
            ["SRC-100000002", "PARTY-2", "S-A", "GPU", "34", "20260528120600", "ALLOCATED", "LOC-2"],
            ["SRC-100000003", "PARTY-3", "S-B", "MEM", "56", "20260528130500", "ALLOCATED", "LOC-3"],
        ],
        [
            ["ACT-1", "SRC-100000001", "PARTY-1", "S-A", "C", "12", "20260528121000", "BURST", "LOC-1"],
            ["ACT-2", "SRC-100000002", "PARTY-2", "S-A", "GPUF", "34", "20260528121100", "RECLAIM", "LOC-2"],
            ["ACT-3", "SRC-100000003", "PARTY-3", "S-B", "MEMORY", "56", "20260528131000", "CORRECT", "LOC-3"],
        ],
        [["S-A", "20260528120000", "20260528123000", "OPEN"], ["S-B", "20260528130000", "20260528133000", "OPEN"]],
    )
    rows, summary = run_program()
    assert REPORT.read_text().splitlines()[0] == "credit_id,event_id,account_id,reservation_id,sku_type,amount,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["sku_type"] for row in rows] == ["CPU", "GPU", "MEM"]
    assert summary == {"matched_count": 3, "matched_amount": 102, "unmatched_count": 0, "unmatched_amount": 0}


def test_window_state_malformed_times_latest_candidate_and_order():
    """Window eligibility, malformed times, latest candidate selection, order, and blank unmatched sku_type should hold."""
    build_program()
    write_inputs(
        [
            ["SRC-WIN-1", "PARTY-1", "S-O", "CPU", "1", "20260528150000", "ALLOCATED", "L1"],
            ["SRC-WIN-2", "PARTY-2", "S-C", "CPU", "2", "20260528150000", "ALLOCATED", "L2"],
            ["SRC-WIN-3", "PARTY-3", "S-M", "GPU", "3", "bad-time", "ALLOCATED", "L3"],
            ["SRC-DUPE", "PARTY-4", "S-O", "MEM", "4", "20260528150100", "ALLOCATED", "L4"],
            ["SRC-DUPE", "PARTY-4", "S-O", "MEM", "4", "20260528150200", "ALLOCATED", "L4"],
        ],
        [
            ["ACT-1", "SRC-WIN-1", "PARTY-1", "S-O", "CPU", "1", "20260528150500", "BURST", "L1"],
            ["ACT-2", "SRC-WIN-2", "PARTY-2", "S-C", "CPU", "2", "20260528150500", "BURST", "L2"],
            ["ACT-3", "SRC-WIN-3", "PARTY-3", "S-M", "GPU", "3", "20260528150500", "RECLAIM", "L3"],
            ["ACT-4", "SRC-DUPE", "PARTY-4", "S-O", "MEM", "4", "20260528150600", "CORRECT", "L4"],
        ],
        [["S-O", "20260528145900", "20260528153000", "OPEN"], ["S-C", "20260528145900", "20260528153000", "CLOSED"], ["S-M", "bad-time", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["credit_id"] for row in rows] == ["ACT-1", "ACT-2", "ACT-3", "ACT-4"]
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert [row["sku_type"] for row in rows] == ["CPU", "", "", "MEM"]
    assert summary == {"matched_count": 2, "matched_amount": 5, "unmatched_count": 2, "unmatched_amount": 5}


def test_credit_timestamp_after_window_close_is_unmatched():
    """A credit after the reservation window close_ts must stay unmatched."""
    build_program()
    write_inputs(
        [["SRC-AFTER-CLOSE", "PARTY-C", "S-CLOSE", "MEM", "21", "20260528150000", "ALLOCATED", "L5"]],
        [["ACT-AFTER-CLOSE", "SRC-AFTER-CLOSE", "PARTY-C", "S-CLOSE", "MEMORY", "21", "20260528153100", "CORRECT", "L5"]],
        [["S-CLOSE", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["sku_type"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 21}


def test_non_numeric_credit_timestamp_is_unmatched_inside_open_window():
    """A non-numeric credit_ts must stay unmatched even when the source window is open."""
    build_program()
    write_inputs(
        [["SRC-BAD-CREDIT-M3", "PARTY-N", "S-NUM", "CPU", "22", "20260528150000", "ALLOCATED", "L6"]],
        [["ACT-BAD-CREDIT-M3", "SRC-BAD-CREDIT-M3", "PARTY-N", "S-NUM", "CPU", "22", "bad-time", "BURST", "L6"]],
        [["S-NUM", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["sku_type"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 22}


def test_non_canonical_correction_sku_type_is_unmatched():
    """Both source and correction sku_type values must be canonical after alias normalization."""
    build_program()
    write_inputs(
        [["SRC-X", "PARTY-X", "S-X", "CPU", "9", "20260528150000", "ALLOCATED", "L1"]],
        [["ACT-X", "SRC-X", "PARTY-X", "S-X", "BAD", "9", "20260528150500", "BURST", "L1"]],
        [["S-X", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["sku_type"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 9}


def test_region_mismatch_is_unmatched_when_all_other_fields_match():
    """Region must be enforced as a required matching key under milestone 3."""
    build_program()
    write_inputs(
        [["SRC-R", "PARTY-R", "S-O", "CPU", "5", "20260528150000", "ALLOCATED", "REGION-A"]],
        [["ACT-R", "SRC-R", "PARTY-R", "S-O", "CPU", "5", "20260528150500", "BURST", "REGION-B"]],
        [["S-O", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["sku_type"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 5}


def test_latest_timestamp_candidates_are_consumed_before_older_candidate():
    """Latest reserve_ts candidates should be consumed before an older still-eligible row."""
    build_program()
    write_inputs(
        [
            ["SRC-T", "PARTY-T", "S-T", "CPU", "50", "20260528150100", "ALLOCATED", "L9"],
            ["SRC-T", "PARTY-T", "S-T", "GPU", "50", "20260528150200", "ALLOCATED", "L9"],
            ["SRC-T", "PARTY-T", "S-T", "MEM", "50", "20260528150300", "ALLOCATED", "L9"],
        ],
        [
            ["ACT-T1", "SRC-T", "PARTY-T", "S-T", "MEMORY", "50", "20260528150600", "CORRECT", "L9"],
            ["ACT-T2", "SRC-T", "PARTY-T", "S-T", "MEMORY", "50", "20260528150610", "CORRECT", "L9"],
            ["ACT-T3", "SRC-T", "PARTY-T", "S-T", "MEMORY", "50", "20260528150620", "CORRECT", "L9"],
        ],
        [["S-T", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["amount"] for row in rows] == ["50", "50", "50"]
    assert [row["sku_type"] for row in rows] == ["MEM", "GPU", "CPU"]
    assert summary == {"matched_count": 3, "matched_amount": 150, "unmatched_count": 0, "unmatched_amount": 0}


def test_earliest_source_input_row_wins_on_timestamp_tie():
    """When reserve_ts ties, the earliest source input row should be consumed first."""
    build_program()
    write_inputs(
        [
            ["SRC-TIE", "PARTY-T", "S-TIE", "CPU", "50", "20260528160000", "ALLOCATED", "L8"],
            ["SRC-TIE", "PARTY-T", "S-TIE", "GPU", "60", "20260528160000", "ALLOCATED", "L8"],
            ["SRC-TIE", "PARTY-T", "S-TIE", "MEM", "70", "20260528160000", "ALLOCATED", "L8"],
        ],
        [
            ["ACT-T1", "SRC-TIE", "PARTY-T", "S-TIE", "CPU", "50", "20260528160500", "BURST", "L8"],
            ["ACT-T2", "SRC-TIE", "PARTY-T", "S-TIE", "C", "60", "20260528160600", "BURST", "L8"],
        ],
        [["S-TIE", "20260528155900", "20260528163000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["sku_type"] for row in rows] == ["CPU", "GPU"]
    assert [row["amount"] for row in rows] == ["50", "60"]
    assert summary == {"matched_count": 2, "matched_amount": 110, "unmatched_count": 0, "unmatched_amount": 0}


def test_alias_window_and_tie_break_combined_regression():
    """Aliases, OPEN windows, and earliest-row tie breaks must work together."""
    build_program()
    write_inputs(
        [
            ["SRC-MIX-1", "PARTY-M", "S-MIX", "C", "11", "20260528150000", "ALLOCATED", "L1"],
            ["SRC-MIX-1", "PARTY-M", "S-MIX", "GPUF", "22", "20260528150000", "ALLOCATED", "L1"],
            ["SRC-MIX-2", "PARTY-M", "S-MISS", "MEMORY", "33", "20260528150000", "ALLOCATED", "L1"],
        ],
        [
            ["ACT-M1", "SRC-MIX-1", "PARTY-M", "S-MIX", "CPU", "11", "20260528150500", "BURST", "L1"],
            ["ACT-M2", "SRC-MIX-1", "PARTY-M", "S-MIX", "GPU", "22", "20260528150600", "RECLAIM", "L1"],
            ["ACT-M3", "SRC-MIX-2", "PARTY-M", "S-MISS", "MEM", "33", "20260528150700", "CORRECT", "L1"],
        ],
        [["S-MIX", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["sku_type"] for row in rows] == ["CPU", "GPU", ""]
    assert summary == {"matched_count": 2, "matched_amount": 33, "unmatched_count": 1, "unmatched_amount": 33}


def test_unlisted_reservation_is_unmatched():
    """A reservation_id with no window row must stay unmatched."""
    build_program()
    write_inputs(
        [["SRC-U", "PARTY-U", "S-UNLISTED", "CPU", "7", "20260528150000", "ALLOCATED", "L1"]],
        [["ACT-U", "SRC-U", "PARTY-U", "S-UNLISTED", "CPU", "7", "20260528150500", "BURST", "L1"]],
        [["S-OTHER", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["sku_type"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 7}


def test_memory_alias_consumption_blocks_second_credit():
    """Alias-normalized MEM rows must still obey one-event-per-source consumption."""
    build_program()
    write_inputs(
        [["SRC-CON", "PARTY-C", "S-W", "MEM", "55", "20260528160000", "ALLOCATED", "L1"]],
        [
            ["ACT-1", "SRC-CON", "PARTY-C", "S-W", "MEMORY", "55", "20260528160500", "BURST", "L1"],
            ["ACT-2", "SRC-CON", "PARTY-C", "S-W", "MEM", "55", "20260528160600", "RECLAIM", "L1"],
        ],
        [["S-W", "20260528155900", "20260528163000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert [row["sku_type"] for row in rows] == ["MEM", ""]
    assert summary == {"matched_count": 1, "matched_amount": 55, "unmatched_count": 1, "unmatched_amount": 55}
