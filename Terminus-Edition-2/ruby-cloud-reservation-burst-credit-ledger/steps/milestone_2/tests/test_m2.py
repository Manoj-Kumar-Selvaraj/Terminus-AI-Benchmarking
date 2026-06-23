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


def test_source_alias_normalization_matches_canonical_correction():
    """Source rows with alias sku_type values must normalize before matching."""
    build_program()
    write_inputs(
        [
            ["SRC-ALIAS-SRC", "PARTY-X", "S-A", "C", "12", "20260528120500", "ALLOCATED", "LOC-1"],
            ["SRC-CANON", "PARTY-Y", "S-A", "GPU", "34", "20260528120600", "ALLOCATED", "LOC-2"],
        ],
        [
            ["ACT-1", "SRC-ALIAS-SRC", "PARTY-X", "S-A", "CPU", "12", "20260528121000", "BURST", "LOC-1"],
            ["ACT-2", "SRC-CANON", "PARTY-Y", "S-A", "GPUF", "34", "20260528121100", "RECLAIM", "LOC-2"],
        ],
        [["S-A", "20260528120000", "20260528123000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["sku_type"] for row in rows] == ["CPU", "GPU"]
    assert summary == {"matched_count": 2, "matched_amount": 46, "unmatched_count": 0, "unmatched_amount": 0}


def test_full_event_id_selects_exact_row_not_prefix_distractor():
    """Full event_id equality must choose the exact row, not a shared-prefix distractor."""
    build_program()
    write_inputs(
        [
            ["SRC-X", "PARTY-5", "S-G", "GPU", "99", "20260528140000", "ALLOCATED", "L5"],
            ["SRC-X1", "PARTY-5", "S-G", "CPU", "50", "20260528140000", "ALLOCATED", "L5"],
        ],
        [["ACT-P", "SRC-X1", "PARTY-5", "S-G", "CPU", "50", "20260528140500", "BURST", "L5"]],
        [["S-G", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["sku_type"] == "CPU"
    assert summary == {"matched_count": 1, "matched_amount": 50, "unmatched_count": 0, "unmatched_amount": 0}


def test_alias_case_folding_and_trim_are_required():
    """Aliases must normalize after trimming and case folding."""
    build_program()
    write_inputs(
        [
            ["SRC-CF1", "P-CF", "S-CF", "CPU", "10", "20260528140000", "ALLOCATED", "L1"],
            ["SRC-CF2", "P-CF", "S-CF", "GPU", "20", "20260528140100", "ALLOCATED", "L1"],
            ["SRC-CF3", "P-CF", "S-CF", "MEM", "30", "20260528140200", "ALLOCATED", "L1"],
        ],
        [
            ["ACT-CF1", "SRC-CF1", "P-CF", "S-CF", " c ", "10", "20260528140500", "BURST", "L1"],
            ["ACT-CF2", "SRC-CF2", "P-CF", "S-CF", " gpuf ", "20", "20260528140600", "RECLAIM", "L1"],
            ["ACT-CF3", "SRC-CF3", "P-CF", "S-CF", " Memory ", "30", "20260528140700", "CORRECT", "L1"],
        ],
        [["S-CF", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["sku_type"] for row in rows] == ["CPU", "GPU", "MEM"]
    assert summary == {"matched_count": 3, "matched_amount": 60, "unmatched_count": 0, "unmatched_amount": 0}


def test_closed_window_rejects_otherwise_valid_alias_match():
    """Closed windows must reject matches even when alias normalization and other keys align."""
    build_program()
    write_inputs(
        [["SRC-W", "P-W", "S-W", "C", "40", "20260528140000", "ALLOCATED", "L1"]],
        [["ACT-W", "SRC-W", "P-W", "S-W", "CPU", "40", "20260528140500", "BURST", "L1"]],
        [["S-W", "20260528120000", "20260528130000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["sku_type"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 40}


def test_region_mismatch_blocks_otherwise_valid_alias_match():
    """Region must independently match in milestone 2 too."""
    build_program()
    write_inputs(
        [["SRC-R", "PARTY-R", "S-G", "CPU", "15", "20260528140000", "ALLOCATED", "REGION-A"]],
        [["ACT-R", "SRC-R", "PARTY-R", "S-G", "C", "15", "20260528140500", "BURST", "REGION-B"]],
        [["S-G", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["sku_type"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 15}


def test_shared_unknown_sku_alias_on_both_sides_stays_unmatched():
    """Unknown normalized sku_type values must not match even when both sides share the alias."""
    build_program()
    write_inputs(
        [["SRC-UNK", "PARTY-U", "S-U", "BAD", "18", "20260528170000", "ALLOCATED", "L1"]],
        [["ACT-UNK", "SRC-UNK", "PARTY-U", "S-U", "BAD", "18", "20260528170100", "BURST", "L1"]],
        [["S-U", "20260528165900", "20260528173000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["sku_type"] == ""
    assert summary["matched_count"] == 0


def test_alias_consumption_prevents_second_match_on_same_source():
    """Alias normalization must not bypass source-row consumption."""
    build_program()
    write_inputs(
        [["SRC-CON", "PARTY-C", "S-C", "C", "25", "20260528140000", "ALLOCATED", "L1"]],
        [
            ["ACT-1", "SRC-CON", "PARTY-C", "S-C", "CPU", "25", "20260528140500", "BURST", "L1"],
            ["ACT-2", "SRC-CON", "PARTY-C", "S-C", "CPU", "25", "20260528140600", "BURST", "L1"],
        ],
        [["S-C", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert rows[0]["sku_type"] == "CPU"
    assert rows[1]["sku_type"] == ""
    assert summary == {"matched_count": 1, "matched_amount": 25, "unmatched_count": 1, "unmatched_amount": 25}


def test_source_aliases_are_trimmed_and_case_folded():
    """Source-side aliases must normalize after trimming and case folding."""
    build_program()
    write_inputs(
        [
            ["SRC-S1", "P-S", "S-S", " c ", "10", "20260528140000", "ALLOCATED", "L1"],
            ["SRC-S2", "P-S", "S-S", " gpuf ", "20", "20260528140100", "ALLOCATED", "L1"],
            ["SRC-S3", "P-S", "S-S", " Memory ", "30", "20260528140200", "ALLOCATED", "L1"],
        ],
        [
            ["ACT-S1", "SRC-S1", "P-S", "S-S", "GPU", "10", "20260528140500", "BURST", "L1"],
            ["ACT-S2", "SRC-S2", "P-S", "S-S", "CPU", "20", "20260528140600", "RECLAIM", "L1"],
            ["ACT-S3", "SRC-S3", "P-S", "S-S", "CPU", "30", "20260528140700", "CORRECT", "L1"],
        ],
        [["S-S", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["sku_type"] for row in rows] == ["CPU", "GPU", "MEM"]
    assert summary == {"matched_count": 3, "matched_amount": 60, "unmatched_count": 0, "unmatched_amount": 0}
