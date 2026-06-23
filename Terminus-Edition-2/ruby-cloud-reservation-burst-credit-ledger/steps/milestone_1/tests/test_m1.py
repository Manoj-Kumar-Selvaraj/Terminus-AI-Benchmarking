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
    assert rows[0]["sku_type"] == "CPU"
    assert rows[1]["sku_type"] == ""
    assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 7, "unmatched_amount": 191}


def test_reserve_ts_before_window_open_is_unmatched():
    """A source timestamp before the window open_ts must stay unmatched."""
    build_program()
    write_inputs(
        [["SRC-EARLY", "PARTY-E", "S-E", "CPU", "5", "20260528115800", "ALLOCATED", "L1"]],
        [["ACT-EARLY", "SRC-EARLY", "PARTY-E", "S-E", "CPU", "5", "20260528120500", "BURST", "L1"]],
        [["S-E", "20260528120000", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["sku_type"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 5}


def test_non_numeric_timestamps_are_unmatched():
    """Non-numeric reserve_ts or credit_ts values make the candidate ineligible."""
    build_program()
    write_inputs(
        [
            ["SRC-BAD-SOURCE-TS", "PARTY-1", "S-TS", "CPU", "11", "bad-time", "ALLOCATED", "L1"],
            ["SRC-BAD-CREDIT-TS", "PARTY-2", "S-TS", "GPU", "12", "20260528140000", "ALLOCATED", "L2"],
        ],
        [
            ["ACT-BAD-SOURCE-TS", "SRC-BAD-SOURCE-TS", "PARTY-1", "S-TS", "CPU", "11", "20260528140500", "BURST", "L1"],
            ["ACT-BAD-CREDIT-TS", "SRC-BAD-CREDIT-TS", "PARTY-2", "S-TS", "GPU", "12", "bad-time", "RECLAIM", "L2"],
        ],
        [["S-TS", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
    assert [row["sku_type"] for row in rows] == ["", ""]
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 2, "unmatched_amount": 23}


def test_memory_is_not_canonical_in_milestone_1():
    """MEM and MEMORY are ineligible before the milestone 2 alias rules are introduced."""
    build_program()
    write_inputs(
        [["SRC-MEM-M1", "PARTY-M", "S-MEM", "MEM", "13", "20260528140000", "ALLOCATED", "L3"]],
        [["ACT-MEM-M1", "SRC-MEM-M1", "PARTY-M", "S-MEM", "MEMORY", "13", "20260528140500", "CORRECT", "L3"]],
        [["S-MEM", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["sku_type"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 13}


def test_credit_timestamp_after_window_close_is_unmatched():
    """A credit after the active reservation window close_ts must stay unmatched."""
    build_program()
    write_inputs(
        [["SRC-AFTER-CLOSE-M1", "PARTY-C", "S-CLOSE", "CPU", "14", "20260528140000", "ALLOCATED", "L4"]],
        [["ACT-AFTER-CLOSE-M1", "SRC-AFTER-CLOSE-M1", "PARTY-C", "S-CLOSE", "CPU", "14", "20260528143100", "BURST", "L4"]],
        [["S-CLOSE", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["sku_type"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 14}


def test_cross_sku_match_emits_source_sku_type():
    """sku_type is not a matching key; a GPU correction can match a CPU source when identity fields align."""
    build_program()
    write_inputs(
        [["SRC-X", "P-1", "R-1", "CPU", "10", "20260528140000", "ALLOCATED", "L1"]],
        [["ACT-X", "SRC-X", "P-1", "R-1", "GPU", "10", "20260528140500", "BURST", "L1"]],
        [["R-1", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["sku_type"] == "CPU"
    assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 0, "unmatched_amount": 0}


def test_region_mismatch_blocks_otherwise_valid_match():
    """Region must independently match when all other matching fields line up."""
    build_program()
    write_inputs(
        [["SRC-R", "PARTY-R", "S-R", "CPU", "10", "20260528140000", "ALLOCATED", "REGION-A"]],
        [["ACT-R", "SRC-R", "PARTY-R", "S-R", "CPU", "10", "20260528140500", "BURST", "REGION-B"]],
        [["S-R", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["sku_type"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 10}


def test_closed_and_unlisted_windows_are_ineligible():
    """Closed and unlisted reservation windows must both reject matching."""
    build_program()
    write_inputs(
        [
            ["SRC-W-CLOSED", "PARTY-W1", "S-C", "CPU", "7", "20260528140000", "ALLOCATED", "L1"],
            ["SRC-W-UNLISTED", "PARTY-W2", "S-U", "GPU", "8", "20260528140000", "ALLOCATED", "L2"],
        ],
        [
            ["ACT-W-CLOSED", "SRC-W-CLOSED", "PARTY-W1", "S-C", "CPU", "7", "20260528140500", "BURST", "L1"],
            ["ACT-W-UNLISTED", "SRC-W-UNLISTED", "PARTY-W2", "S-U", "GPU", "8", "20260528140500", "RECLAIM", "L2"],
        ],
        [["S-C", "20260528135900", "20260528143000", "CLOSED"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
    assert [row["sku_type"] for row in rows] == ["", ""]
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 2, "unmatched_amount": 15}


def test_reservation_id_must_match_independently():
    """Reservation_id must match even when event/account/sku_type/amount/region align."""
    build_program()
    write_inputs(
        [
            ["SRC-X", "PARTY-5", "RES-A", "CPU", "50", "20260528140000", "ALLOCATED", "L5"],
            ["SRC-X1", "PARTY-5", "RES-B", "CPU", "50", "20260528140000", "ALLOCATED", "L5"],
        ],
        [["ACT-P", "SRC-X", "PARTY-5", "RES-B", "CPU", "50", "20260528140500", "BURST", "L5"]],
        [["RES-A", "20260528135900", "20260528143000", "OPEN"], ["RES-B", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["sku_type"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 50}


def test_latest_reserve_ts_selects_newest_qualifying_source_row():
    """When several unused source rows qualify, the latest reserve_ts candidate must be consumed first."""
    build_program()
    write_inputs(
        [
            ["SRC-T", "PARTY-T", "S-T", "CPU", "50", "20260528150100", "ALLOCATED", "L9"],
            ["SRC-T", "PARTY-T", "S-T", "GPU", "50", "20260528150200", "ALLOCATED", "L9"],
            ["SRC-T", "PARTY-T", "S-T", "CPU", "50", "20260528150300", "ALLOCATED", "L9"],
        ],
        [
            ["ACT-T1", "SRC-T", "PARTY-T", "S-T", "CPU", "50", "20260528150600", "BURST", "L9"],
            ["ACT-T2", "SRC-T", "PARTY-T", "S-T", "CPU", "50", "20260528150610", "BURST", "L9"],
            ["ACT-T3", "SRC-T", "PARTY-T", "S-T", "CPU", "50", "20260528150620", "BURST", "L9"],
        ],
        [["S-T", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["sku_type"] for row in rows] == ["CPU", "GPU", "CPU"]
    assert summary == {"matched_count": 3, "matched_amount": 150, "unmatched_count": 0, "unmatched_amount": 0}


def test_earliest_source_input_row_wins_on_reserve_ts_tie():
    """When reserve_ts ties, the earliest source input row must be consumed first."""
    build_program()
    write_inputs(
        [
            ["SRC-TIE", "PARTY-T", "S-TIE", "CPU", "50", "20260528160000", "ALLOCATED", "L8"],
            ["SRC-TIE", "PARTY-T", "S-TIE", "GPU", "50", "20260528160000", "ALLOCATED", "L8"],
            ["SRC-TIE", "PARTY-T", "S-TIE", "CPU", "50", "20260528160000", "ALLOCATED", "L8"],
        ],
        [
            ["ACT-T1", "SRC-TIE", "PARTY-T", "S-TIE", "CPU", "50", "20260528160500", "BURST", "L8"],
            ["ACT-T2", "SRC-TIE", "PARTY-T", "S-TIE", "GPU", "50", "20260528160600", "BURST", "L8"],
        ],
        [["S-TIE", "20260528155900", "20260528163000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["sku_type"] for row in rows] == ["CPU", "GPU"]
    assert summary == {"matched_count": 2, "matched_amount": 100, "unmatched_count": 0, "unmatched_amount": 0}


def test_amounts_are_compared_as_integers():
    """Numerically equal integer amounts must match despite different text formatting."""
    build_program()
    write_inputs(
        [["SRC-AMT", "PARTY-A", "S-A", "CPU", "010", "20260528140000", "ALLOCATED", "L1"]],
        [["ACT-AMT", "SRC-AMT", "PARTY-A", "S-A", "GPU", "10", "20260528140500", "BURST", "L1"]],
        [["S-A", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["sku_type"] == "CPU"
    assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 0, "unmatched_amount": 0}
