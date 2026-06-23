"""Tests for realtime ski resort lift gate release reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "lift_sessions.csv"
ACTION = APP / "data" / "gate_releases.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "lift_gate_release_report.csv"
SUMMARY = APP / "out" / "lift_gate_release_summary.txt"


def build_program():
    """Prepare the reconciler for one test scenario."""
    pass


def write_csv(path, header, rows):
    """Write one CSV fixture."""
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(source, action, windows):
    """Overwrite all input files at runtime."""
    write_csv(SOURCE, ["pass_id", "skier_id", "lift_id", "pass_tier", "amount", "scan_ts", "status", "slope"], source)
    write_csv(ACTION, ["release_id", "pass_id", "skier_id", "lift_id", "pass_tier", "amount", "release_ts", "reason", "slope"], action)
    write_csv(WINDOWS, ["lift_id", "open_ts", "close_ts", "state"], windows)
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
        if not line.strip():
            continue
        key, value = line.split("=", 1)
        summary[key.strip()] = int(value.strip())
    return rows, summary


def test_all_gates_consumption_and_positive_unmatched_totals():
    """Every identity, status, timestamp, reason, and consumption gate should reject bad candidates."""
    build_program()
    write_inputs(
        [
            ["SRC-GATE-1", "PARTY-1", "S-G", "DAY", "10", "20260528140000", "SCANNED", "L1"],
            ["SRC-GATE-2", "PARTY-2", "S-G", "DAY", "20", "20260528140100", "BAD", "L2"],
            ["SRC-GATE-3", "PARTY-3", "S-G", "SEASON", "30", "20260528140200", "SCANNED", "L3"],
            ["SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140300", "SCANNED", "L4"],
        ],
        [
            ["ACT-A", "SRC-GATE-1", "PARTY-1", "S-G", "DAY", "10", "20260528140500", "VOID", "L1"],
            ["ACT-B", "SRC-GATE-1", "PARTY-1", "S-G", "DAY", "10", "20260528140600", "VOID", "L1"],
            ["ACT-C", "SRC-GATE-2", "PARTY-2", "S-G", "DAY", "20", "20260528140700", "VOID", "L2"],
            ["ACT-D", "SRC-GATE-3", "PARTY-X", "S-G", "SEASON", "30", "20260528140700", "COMP", "L3"],
            ["ACT-E", "SRC-GATE-3", "PARTY-3", "S-G", "SEASON", "31", "20260528140700", "COMP", "L3"],
            ["ACT-F", "SRC-GATE-3", "PARTY-3", "S-G", "SEASON", "30", "20260528135959", "COMP", "L3"],
            ["ACT-G", "SRC-GATE-3", "PARTY-3", "S-G", "SEASON", "30", "20260528140700", "INFO", "L3"],
            ["ACT-H", "SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140700", "GUEST", "L4"],
        ],
        [["S-G", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert rows[1]["pass_tier"] == ""
    assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 7, "unmatched_amount": 191}


def test_full_pass_id_required():
    """A correction must not match when only the leading pass_id prefix overlaps."""
    build_program()
    write_inputs(
        [
            ["SRC-PFX-001", "PARTY-1", "S-P", "DAY", "15", "20260528150000", "SCANNED", "L1"],
            ["SRC-PFX-002", "PARTY-1", "S-P", "DAY", "15", "20260528150100", "SCANNED", "L1"],
        ],
        [
            ["ACT-PFX-1", "SRC-PFX-999", "PARTY-1", "S-P", "DAY", "15", "20260528150500", "VOID", "L1"],
            ["ACT-PFX-2", "SRC-PFX-002", "PARTY-1", "S-P", "DAY", "15", "20260528150600", "VOID", "L1"],
        ],
        [["S-P", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert summary["matched_count"] == 1


def test_release_ts_before_scan_ts_is_rejected():
    """release_ts earlier than scan_ts must leave the correction unmatched."""
    build_program()
    write_inputs(
        [["SRC-EARLY-1", "PARTY-1", "S-E", "SEASON", "25", "20260528160000", "SCANNED", "L1"]],
        [["ACT-EARLY-1", "SRC-EARLY-1", "PARTY-1", "S-E", "SEASON", "25", "20260528155959", "COMP", "L1"]],
        [["S-E", "20260528155800", "20260528163000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["pass_tier"] == ""
    assert summary["matched_count"] == 0


def test_slope_mismatch_rejects_otherwise_matching_rows():
    """A correction must stay unmatched when slope is the only mismatched identity field."""
    build_program()
    write_inputs(
        [["SRC-SLP", "P-1", "S-1", "DAY", "10", "20260528140000", "SCANNED", "NORTH"]],
        [["ACT-SLP", "SRC-SLP", "P-1", "S-1", "DAY", "10", "20260528140500", "VOID", "SOUTH"]],
        [["S-1", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["pass_tier"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 10}


def test_pass_tier_case_folding_and_trimming():
    """Canonical DAY and SEASON pass_tier values should match after trim and case folding."""
    build_program()
    write_inputs(
        [
            ["SRC-CF", "P-1", "S-1", " day ", "10", "20260528140000", "SCANNED", "NORTH"],
            ["SRC-CS", "P-2", "S-1", "Season", "20", "20260528140100", "SCANNED", "SOUTH"],
        ],
        [
            ["ACT-CF", "SRC-CF", "P-1", "S-1", "DAY", "10", "20260528140500", "VOID", "NORTH"],
            ["ACT-CS", "SRC-CS", "P-2", "S-1", " season ", "20", "20260528140600", "COMP", "SOUTH"],
        ],
        [["S-1", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["pass_tier"] for row in rows] == ["DAY", "SEASON"]
    assert summary == {"matched_count": 2, "matched_amount": 30, "unmatched_count": 0, "unmatched_amount": 0}


def test_non_numeric_timestamps_stay_unmatched():
    """Non-numeric scan_ts or release_ts values must reject matching."""
    build_program()
    write_inputs(
        [["SRC-BAD-TS", "PARTY-1", "S-1", "DAY", "10", "bad-ts", "SCANNED", "L1"]],
        [["ACT-BAD-TS", "SRC-BAD-TS", "PARTY-1", "S-1", "DAY", "10", "20260528140500", "VOID", "L1"]],
        [["S-1", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["pass_tier"] == ""
    assert summary["matched_count"] == 0


def test_milestone1_closed_unlisted_and_malformed_windows_are_rejected():
    """Window state, lift_id coverage, and malformed window timestamps are required in milestone 1."""
    build_program()
    write_inputs(
        [
            ["SRC-WIN-CLOSED", "PARTY-1", "S-CLOSED", "DAY", "10", "20260528140000", "SCANNED", "L1"],
            ["SRC-WIN-MISS", "PARTY-2", "S-MISSING", "DAY", "20", "20260528140100", "SCANNED", "L2"],
            ["SRC-WIN-BAD", "PARTY-3", "S-BAD", "SEASON", "30", "20260528140200", "SCANNED", "L3"],
            ["SRC-WIN-OPEN", "PARTY-4", "S-OPEN", "SEASON", "40", "20260528140300", "SCANNED", "L4"],
        ],
        [
            ["ACT-CLOSED", "SRC-WIN-CLOSED", "PARTY-1", "S-CLOSED", "DAY", "10", "20260528140500", "VOID", "L1"],
            ["ACT-MISS", "SRC-WIN-MISS", "PARTY-2", "S-MISSING", "DAY", "20", "20260528140600", "VOID", "L2"],
            ["ACT-BAD", "SRC-WIN-BAD", "PARTY-3", "S-BAD", "SEASON", "30", "20260528140700", "COMP", "L3"],
            ["ACT-OPEN", "SRC-WIN-OPEN", "PARTY-4", "S-OPEN", "SEASON", "40", "20260528140800", "GUEST", "L4"],
        ],
        [
            ["S-CLOSED", "20260528135900", "20260528143000", "CLOSED"],
            ["S-BAD", "bad-open", "20260528143000", "OPEN"],
            ["S-OPEN", "20260528135900", "20260528143000", "OPEN"],
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert [row["pass_tier"] for row in rows] == ["", "", "", "SEASON"]
    assert summary == {"matched_count": 1, "matched_amount": 40, "unmatched_count": 3, "unmatched_amount": 60}


def test_milestone1_release_after_window_close_is_rejected():
    """A release after the OPEN window close must not match even when it is after scan_ts."""
    build_program()
    write_inputs(
        [["SRC-LATE-1", "PARTY-L", "S-LATE", "DAY", "17", "20260528150000", "SCANNED", "L1"]],
        [["ACT-LATE-1", "SRC-LATE-1", "PARTY-L", "S-LATE", "DAY", "17", "20260528153100", "VOID", "L1"]],
        [["S-LATE", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["pass_tier"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 17}


def test_milestone1_latest_scan_ts_wins_then_earliest_source_row():
    """Latest scan_ts must win first so later corrections can still consume older eligible rows."""
    build_program()
    write_inputs(
        [
            ["SRC-DUPE", "PARTY-D", "S-D", "DAY", "11", "20260528160000", "SCANNED", "L1"],
            ["SRC-DUPE", "PARTY-D", "S-D", "DAY", "11", "20260528160200", "SCANNED", "L1"],
        ],
        [
            ["ACT-DUPE-1", "SRC-DUPE", "PARTY-D", "S-D", "DAY", "11", "20260528160300", "VOID", "L1"],
            ["ACT-DUPE-2", "SRC-DUPE", "PARTY-D", "S-D", "DAY", "11", "20260528160100", "VOID", "L1"],
        ],
        [["S-D", "20260528155900", "20260528163000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["pass_tier"] for row in rows] == ["DAY", "DAY"]
    assert summary == {"matched_count": 2, "matched_amount": 22, "unmatched_count": 0, "unmatched_amount": 0}


def test_latest_scan_ts_row_consumed_before_older_scan_ts_row():
    """A later correction can match only if the highest scan_ts source row was consumed first."""
    build_program()
    write_inputs(
        [
            ["SRC-ST", "P-1", "S-ST", "DAY", "11", "20260528160000", "SCANNED", "L1"],
            ["SRC-ST", "P-1", "S-ST", "DAY", "11", "20260528160200", "SCANNED", "L1"],
        ],
        [
            ["ACT-LATE", "SRC-ST", "P-1", "S-ST", "DAY", "11", "20260528160300", "VOID", "L1"],
            ["ACT-EARLIER", "SRC-ST", "P-1", "S-ST", "DAY", "11", "20260528160100", "VOID", "L1"],
        ],
        [["S-ST", "20260528155900", "20260528163000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert summary["matched_count"] == 2


def test_tied_scan_ts_uses_earliest_source_input_row():
    """When scan_ts values tie, the earliest lift_sessions.csv row must be chosen first."""
    build_program()
    write_inputs(
        [
            ["SRC-T0", "P-1", "S-TT", "DAY", "11", "20260528160200", "SCANNED", "L1"],
            ["SRC-T1", "P-1", "S-TT", "DAY", "11", "20260528160200", "SCANNED", "L1"],
        ],
        [
            ["ACT-ONE", "SRC-T0", "P-1", "S-TT", "DAY", "11", "20260528160300", "VOID", "L1"],
            ["ACT-TWO", "SRC-T1", "P-1", "S-TT", "DAY", "11", "20260528160300", "VOID", "L1"],
        ],
        [["S-TT", "20260528155900", "20260528163000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert summary["matched_count"] == 2


def test_summary_amounts_are_positive_integers():
    """Summary matched and unmatched amount fields must be non-negative integers."""
    build_program()
    write_inputs(
        [["SRC-POS", "P-1", "S-P", "DAY", "10", "20260528140000", "SCANNED", "L1"]],
        [["ACT-POS", "SRC-POS", "P-1", "S-P", "DAY", "10", "20260528140500", "VOID", "L1"]],
        [["S-P", "20260528135900", "20260528143000", "OPEN"]],
    )
    _, summary = run_program()
    assert summary["matched_amount"] >= 0
    assert summary["unmatched_amount"] >= 0


def test_empty_input_files_produce_zero_totals():
    """Empty session and release files should yield zero summary totals."""
    build_program()
    write_inputs([], [], [])
    rows, summary = run_program()
    assert rows == []
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 0, "unmatched_amount": 0}


def test_report_header_exact():
    """Report CSV header must match the milestone contract exactly."""
    build_program()
    write_inputs(
        [["SRC-H", "P-1", "S-H", "DAY", "5", "20260528140000", "SCANNED", "L1"]],
        [["ACT-H", "SRC-H", "P-1", "S-H", "DAY", "5", "20260528140500", "VOID", "L1"]],
        [["S-H", "20260528135900", "20260528143000", "OPEN"]],
    )
    run_program()
    assert REPORT.read_text().splitlines()[0] == "release_id,pass_id,skier_id,lift_id,pass_tier,amount,reason,status"


def test_vip_and_hr_ineligible_in_milestone1():
    """VIP and HR pass_tier values must stay unmatched in milestone 1.

    kind_aliases.csv may exist in the image but must not be applied until milestone 3.
    """
    build_program()
    write_inputs(
        [
            ["SRC-V", "P-1", "S-1", "VIP", "10", "20260528140000", "SCANNED", "L1"],
            ["SRC-R", "P-2", "S-1", "HR", "20", "20260528140100", "SCANNED", "L2"],
        ],
        [
            ["ACT-V", "SRC-V", "P-1", "S-1", "VIP", "10", "20260528140500", "VOID", "L1"],
            ["ACT-R", "SRC-R", "P-2", "S-1", "HR", "20", "20260528140600", "VOID", "L2"],
        ],
        [["S-1", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
    assert summary["matched_count"] == 0


def test_release_ts_equal_scan_ts_matches():
    """release_ts equal to scan_ts on the boundary should match when inside the window."""
    build_program()
    write_inputs(
        [["SRC-EQ", "P-1", "S-E", "DAY", "14", "20260528150000", "SCANNED", "L1"]],
        [["ACT-EQ", "SRC-EQ", "P-1", "S-E", "DAY", "14", "20260528150000", "VOID", "L1"]],
        [["S-E", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, _ = run_program()
    assert rows[0]["status"] == "MATCHED"


def test_window_state_case_folding_open():
    """Window state OpEn after trim and case fold should behave as OPEN."""
    build_program()
    write_inputs(
        [["SRC-OC", "P-1", "S-O", "SEASON", "16", "20260528140000", "SCANNED", "L1"]],
        [["ACT-OC", "SRC-OC", "P-1", "S-O", "SEASON", "16", "20260528140500", "COMP", "L1"]],
        [["S-O", "20260528135900", "20260528143000", "OpEn"]],
    )
    rows, _ = run_program()
    assert rows[0]["status"] == "MATCHED"


def test_identity_fields_trim_before_match():
    """Leading and trailing spaces on identity fields must trim before comparison."""
    build_program()
    write_inputs(
        [["SRC-TR", " P-1 ", "S-1", "DAY", "10", "20260528140000", "SCANNED", " L1 "]],
        [["ACT-TR", " SRC-TR ", " P-1 ", "S-1", " day ", "10", "20260528140500", "VOID", " L1 "]],
        [["S-1", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, _ = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["pass_tier"] == "DAY"


def test_second_correction_consumes_older_row_after_latest_taken():
    """After the latest scan_ts row is consumed, the next correction should take the older row."""
    build_program()
    write_inputs(
        [
            ["SRC-SEQ", "P-1", "S-S", "DAY", "11", "20260528160000", "SCANNED", "L1"],
            ["SRC-SEQ", "P-1", "S-S", "DAY", "11", "20260528160200", "SCANNED", "L1"],
        ],
        [
            ["ACT-1", "SRC-SEQ", "P-1", "S-S", "DAY", "11", "20260528160300", "VOID", "L1"],
            ["ACT-2", "SRC-SEQ", "P-1", "S-S", "DAY", "11", "20260528160100", "VOID", "L1"],
        ],
        [["S-S", "20260528155900", "20260528163000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert summary["matched_count"] == 2


def test_scan_ts_before_window_open_is_unmatched():
    """scan_ts before window open_ts must reject matching even when release_ts is in range."""
    build_program()
    write_inputs(
        [["SRC-BEFORE", "P-1", "S-B", "DAY", "18", "20260528135800", "SCANNED", "L1"]],
        [["ACT-BEFORE", "SRC-BEFORE", "P-1", "S-B", "DAY", "18", "20260528140500", "VOID", "L1"]],
        [["S-B", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, _ = run_program()
    assert rows[0]["status"] == "UNMATCHED"


def test_wrong_length_numeric_timestamps_stay_unmatched():
    """Timestamps must be exactly 14 digits, not merely numeric strings."""
    build_program()
    write_inputs(
        [["SRC-LEN", "P-1", "S-L", "DAY", "10", "202605281400", "SCANNED", "L1"]],
        [["ACT-LEN", "SRC-LEN", "P-1", "S-L", "DAY", "10", "20260528140500", "VOID", "L1"]],
        [["S-L", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, _ = run_program()
    assert rows[0]["status"] == "UNMATCHED"
