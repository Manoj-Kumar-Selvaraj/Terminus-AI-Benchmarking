"""Verifier tests for realtime window ranking in the fuel card reconciler."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
GO = Path("/usr/local/go/bin/go")
BIN = APP / "build" / "reconcile"
SOURCE = APP / "data" / "authorizations.csv"
ACTION = APP / "data" / "reversals.csv"
WINDOWS = APP / "config" / "windows.csv"
ALIASES = APP / "config" / "kind_aliases.csv"
REPORT = APP / "out" / "fuel_reversal_report.csv"
SUMMARY = APP / "out" / "fuel_reversal_summary.txt"
REPORT_HEADER = ["action_id", "auth_id", "fleet_id", "batch_id", "kind", "amount", "reason", "status"]


def build_program():
    """Compile the Go reconciler for a window-focused scenario."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile/main.go"], check=True, cwd=APP, timeout=60)


def write_csv(path, header, rows):
    """Write one runtime CSV file for verifier-controlled data."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(source_rows, action_rows, window_rows, alias_rows=None, window_header=None):
    """Install source, reversal, alias, and window fixtures."""
    write_csv(SOURCE, ["auth_id", "fleet_id", "batch_id", "kind", "amount", "source_ts", "status", "location"], source_rows)
    write_csv(ACTION, ["action_id", "auth_id", "fleet_id", "batch_id", "kind", "amount", "action_ts", "reason", "location"], action_rows)
    write_csv(WINDOWS, window_header or ["batch_id", "open_ts", "close_ts", "state"], window_rows)
    write_csv(ALIASES, ["alias", "canonical"], alias_rows if alias_rows is not None else [["DSL", "DIESEL"], ["PETROL", "GAS"], ["CHARGE", "EV"]])
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the reconciler and return parsed report rows and summary values."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == REPORT_HEADER
        rows = list(reader)
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        summary[key] = int(value)
    return rows, summary


def test_m3_latest_source_timestamp_selected_then_consumed_in_order():
    """When multiple unused candidates qualify, the latest source_ts wins and is consumed."""
    build_program()
    write_inputs(
        [
            ["AUTH-LATE", "FLEET-L", "BATCH-L", "DIESEL", "100", "20260606100000", "SETTLED", "LOC-L"],
            ["AUTH-LATE", "FLEET-L", "BATCH-L", "DIESEL", "100", "20260606100400", "SETTLED", "LOC-L"],
            ["AUTH-LATE", "FLEET-L", "BATCH-L", "DIESEL", "100", "20260606100200", "SETTLED", "LOC-L"],
        ],
        [
            ["ACT-1", "AUTH-LATE", "FLEET-L", "BATCH-L", "DSL", "100", "20260606100500", "VOID", "LOC-L"],
            ["ACT-2", "AUTH-LATE", "FLEET-L", "BATCH-L", "DSL", "100", "20260606100600", "VOID", "LOC-L"],
            ["ACT-3", "AUTH-LATE", "FLEET-L", "BATCH-L", "DSL", "100", "20260606100700", "VOID", "LOC-L"],
            ["ACT-4", "AUTH-LATE", "FLEET-L", "BATCH-L", "DSL", "100", "20260606100800", "VOID", "LOC-L"],
        ],
        [["BATCH-L", "20260606095900", "20260606110000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert summary == {"matched_count": 3, "matched_amount": 300, "unmatched_count": 1, "unmatched_amount": 100}


def test_m3_equal_latest_timestamp_tie_uses_earliest_source_row():
    """Equal latest source_ts candidates should be resolved by earliest source input row order."""
    build_program()
    write_inputs(
        [
            ["AUTH-TIE", "FLEET-T", "BATCH-T", "GAS", "100", "20260606100400", "SETTLED", "LOC-T"],
            ["AUTH-TIE", "FLEET-T", "BATCH-T", "GAS", "200", "20260606100400", "SETTLED", "LOC-T"],
            ["AUTH-TIE", "FLEET-T", "BATCH-T", "GAS", "300", "20260606100400", "SETTLED", "LOC-T"],
        ],
        [
            ["ACT-TIE-1", "AUTH-TIE", "FLEET-T", "BATCH-T", "PETROL", "100", "20260606100500", "VOID", "LOC-T"],
            ["ACT-TIE-2", "AUTH-TIE", "FLEET-T", "BATCH-T", "PETROL", "200", "20260606100600", "VOID", "LOC-T"],
        ],
        [["BATCH-T", "20260606095900", "20260606110000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["MATCHED", "MATCHED"]
    assert [r["amount"] for r in rows] == ["100", "200"]
    assert summary == {"matched_count": 2, "matched_amount": 300, "unmatched_count": 0, "unmatched_amount": 0}


def test_m3_inclusive_window_boundaries_allow_source_and_action_on_edges():
    """open_ts, source_ts, action_ts, and close_ts boundaries are inclusive."""
    build_program()
    write_inputs(
        [["AUTH-BND", "FLEET-B", "BATCH-B", "EV", "120", "20260606100000", "SETTLED", "LOC-B"]],
        [["ACT-BND", "AUTH-BND", "FLEET-B", "BATCH-B", "CHARGE", "120", "20260606101000", "LIMIT", "LOC-B"]],
        [["BATCH-B", "20260606100000", "20260606101000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["kind"] == "EV"
    assert summary == {"matched_count": 1, "matched_amount": 120, "unmatched_count": 0, "unmatched_amount": 0}


def test_m3_closed_unlisted_malformed_or_reversed_windows_are_ineligible():
    """Only well-formed OPEN windows for the same batch may make a source eligible."""
    build_program()
    write_inputs(
        [
            ["AUTH-CLOSED", "FLEET-W", "BATCH-CLOSED", "DIESEL", "21", "20260606100000", "SETTLED", "LOC-W"],
            ["AUTH-MISSING", "FLEET-W", "BATCH-MISSING", "DIESEL", "22", "20260606100000", "SETTLED", "LOC-W"],
            ["AUTH-BAD", "FLEET-W", "BATCH-BAD", "DIESEL", "23", "20260606100000", "SETTLED", "LOC-W"],
            ["AUTH-REV", "FLEET-W", "BATCH-REV", "DIESEL", "24", "20260606100000", "SETTLED", "LOC-W"],
        ],
        [
            ["ACT-CLOSED", "AUTH-CLOSED", "FLEET-W", "BATCH-CLOSED", "DSL", "21", "20260606100100", "VOID", "LOC-W"],
            ["ACT-MISSING", "AUTH-MISSING", "FLEET-W", "BATCH-MISSING", "DSL", "22", "20260606100100", "VOID", "LOC-W"],
            ["ACT-BAD", "AUTH-BAD", "FLEET-W", "BATCH-BAD", "DSL", "23", "20260606100100", "VOID", "LOC-W"],
            ["ACT-REV", "AUTH-REV", "FLEET-W", "BATCH-REV", "DSL", "24", "20260606100100", "VOID", "LOC-W"],
        ],
        [
            ["BATCH-CLOSED", "20260606095900", "20260606110000", "CLOSED"],
            ["BATCH-BAD", "not-a-ts", "20260606110000", "OPEN"],
            ["BATCH-REV", "20260606110000", "20260606100000", "OPEN"],
        ],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["UNMATCHED"] * 4
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 4, "unmatched_amount": 90}


def test_m3_window_file_is_header_addressed_and_state_casefolded():
    """Windows are parsed by header names, with OPEN state trimmed and case-folded."""
    build_program()
    write_inputs(
        [["AUTH-H", "FLEET-H", "BATCH-H", "DIESEL", "55", "20260606100000", "SETTLED", "LOC-H"]],
        [["ACT-H", "AUTH-H", "FLEET-H", "BATCH-H", "DSL", "55", "20260606100100", "VOID", "LOC-H"]],
        [["ignored", " open ", "20260606110000", "BATCH-H", "20260606095900"]],
        window_header=["extra", "state", "close_ts", "batch_id", "open_ts"],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert summary["matched_amount"] == 55


def test_m3_action_after_close_and_action_before_source_are_unmatched():
    """Corrections must satisfy source_ts <= action_ts <= close_ts."""
    build_program()
    write_inputs(
        [
            ["AUTH-AFTER", "FLEET-A", "BATCH-A", "DIESEL", "40", "20260606100000", "SETTLED", "LOC-A"],
            ["AUTH-BEFORE", "FLEET-A", "BATCH-A", "GAS", "41", "20260606100500", "SETTLED", "LOC-A"],
        ],
        [
            ["ACT-AFTER", "AUTH-AFTER", "FLEET-A", "BATCH-A", "DSL", "40", "20260606110100", "VOID", "LOC-A"],
            ["ACT-BEFORE", "AUTH-BEFORE", "FLEET-A", "BATCH-A", "PETROL", "41", "20260606100459", "VOID", "LOC-A"],
        ],
        [["BATCH-A", "20260606095900", "20260606110000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["UNMATCHED", "UNMATCHED"]
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 2, "unmatched_amount": 81}


def test_m3_multiple_windows_for_same_batch_use_any_valid_open_window():
    """Multiple window rows can exist; any valid OPEN row for the batch may qualify."""
    build_program()
    write_inputs(
        [["AUTH-MULTI", "FLEET-M", "BATCH-M", "GAS", "66", "20260606150000", "SETTLED", "LOC-M"]],
        [["ACT-MULTI", "AUTH-MULTI", "FLEET-M", "BATCH-M", "PETROL", "66", "20260606150100", "VOID", "LOC-M"]],
        [
            ["BATCH-M", "20260606100000", "20260606110000", "OPEN"],
            ["BATCH-M", "20260606145900", "20260606160000", "OPEN"],
        ],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert summary == {"matched_count": 1, "matched_amount": 66, "unmatched_count": 0, "unmatched_amount": 0}


def test_m3_alias_runtime_changes_still_apply_inside_window_logic():
    """Milestone 2 runtime aliases must still work when window eligibility is applied."""
    build_program()
    write_inputs(
        [["AUTH-BIO", "FLEET-BIO", "BATCH-BIO", "DIESEL", "88", "20260606100000", "SETTLED", "LOC-BIO"]],
        [["ACT-BIO", "AUTH-BIO", "FLEET-BIO", "BATCH-BIO", "BIO", "088", "20260606100100", "VOID", "LOC-BIO"]],
        [["BATCH-BIO", "20260606095900", "20260606110000", "OPEN"]],
        alias_rows=[["BIO", "DIESEL"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["amount"] == "088"
    assert summary == {"matched_count": 1, "matched_amount": 88, "unmatched_count": 0, "unmatched_amount": 0}


def test_m3_blank_and_comment_rows_in_windows_are_skipped():
    """Blank, whitespace-only, and comment-like window rows must be ignored during parsing."""
    build_program()
    write_inputs(
        [["AUTH-BW", "FLEET-BW", "BATCH-BW", "DIESEL", "47", "20260606100000", "SETTLED", "LOC-BW"]],
        [["ACT-BW", "AUTH-BW", "FLEET-BW", "BATCH-BW", "DSL", "47", "20260606100100", "VOID", "LOC-BW"]],
        [],
    )
    WINDOWS.write_text(
        "batch_id,open_ts,close_ts,state\n"
        "\n"
        "# this is a comment\n"
        "BATCH-BW,20260606095900,20260606110000,OPEN\n"
        "  \n"
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert summary == {"matched_count": 1, "matched_amount": 47, "unmatched_count": 0, "unmatched_amount": 0}


def test_m3_non_14digit_source_or_action_timestamps_are_ineligible():
    """Source and action timestamps must be exactly 14 numeric UTC digits to qualify."""
    build_program()
    write_inputs(
        [["AUTH-TS", "FLEET-TS", "BATCH-TS", "DIESEL", "10", "2026060610", "SETTLED", "LOC-TS"]],
        [["ACT-TS", "AUTH-TS", "FLEET-TS", "BATCH-TS", "DIESEL", "10", "20260606100100", "VOID", "LOC-TS"]],
        [["BATCH-TS", "20260606095900", "20260606110000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 10}


def test_m3_repeated_runs_are_deterministic_and_outputs_are_regenerated():
    """Two runs with changed inputs should not append stale report or summary data."""
    build_program()
    write_inputs(
        [["AUTH-R1", "FLEET-R", "BATCH-R", "DIESEL", "30", "20260606100000", "SETTLED", "LOC-R"]],
        [["ACT-R1", "AUTH-R1", "FLEET-R", "BATCH-R", "DSL", "30", "20260606100100", "VOID", "LOC-R"]],
        [["BATCH-R", "20260606095900", "20260606110000", "OPEN"]],
    )
    rows1, summary1 = run_program()
    write_inputs(
        [["AUTH-R2", "FLEET-R", "BATCH-R", "DIESEL", "31", "20260606100000", "SETTLED", "LOC-R"]],
        [["ACT-R2", "AUTH-MISS", "FLEET-R", "BATCH-R", "DSL", "31", "20260606100100", "VOID", "LOC-R"]],
        [["BATCH-R", "20260606095900", "20260606110000", "OPEN"]],
    )
    rows2, summary2 = run_program()
    assert [r["action_id"] for r in rows1] == ["ACT-R1"]
    assert [r["action_id"] for r in rows2] == ["ACT-R2"]
    assert summary1 == {"matched_count": 1, "matched_amount": 30, "unmatched_count": 0, "unmatched_amount": 0}
    assert summary2 == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 31}
