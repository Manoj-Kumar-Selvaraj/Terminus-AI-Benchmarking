"""Verifier tests for the fuel card authorization reversal reconciler baseline contract."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
GO = Path("/usr/local/go/bin/go")
BIN = APP / "build" / "reconcile"
SOURCE = APP / "data" / "authorizations.csv"
ACTION = APP / "data" / "reversals.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "fuel_reversal_report.csv"
SUMMARY = APP / "out" / "fuel_reversal_summary.txt"
REPORT_HEADER = ["action_id", "auth_id", "fleet_id", "batch_id", "kind", "amount", "reason", "status"]


def build_program():
    """Compile the Go CLI from source for the current verifier scenario."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile/main.go"], check=True, cwd=APP, timeout=60)


def write_csv(path, header, rows):
    """Write a CSV file with a caller-provided header and row order."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(source_rows, action_rows, window_rows, source_header=None, action_header=None, window_header=None):
    """Replace runtime inputs and seed stale outputs that must be regenerated."""
    write_csv(SOURCE, source_header or ["auth_id", "fleet_id", "batch_id", "kind", "amount", "source_ts", "status", "location"], source_rows)
    write_csv(ACTION, action_header or ["action_id", "auth_id", "fleet_id", "batch_id", "kind", "amount", "action_ts", "reason", "location"], action_rows)
    write_csv(WINDOWS, window_header or ["batch_id", "open_ts", "close_ts", "state"], window_rows)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("stale,report\n")
    SUMMARY.write_text("matched_count=999\n")


def run_program():
    """Execute the reconciler and parse the report and key-value summary."""
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


def test_m1_full_identifier_prefix_collision_consumption_and_schema():
    """Full identity gates and one-time source consumption must defeat prefix collisions."""
    build_program()
    write_inputs(
        [
            ["AUTH-1", "FLEET-1", "BATCH-A", "DIESEL", "100", "20260606100000", "SETTLED", "LOC-1"],
            ["AUTH-10", "FLEET-1", "BATCH-A", "DIESEL", "100", "20260606100100", "SETTLED", "LOC-1"],
            ["AUTH-2", "FLEET-2", "BATCH-A", "GAS", "200", "20260606100200", "SETTLED", "LOC-2"],
        ],
        [
            ["ACT-1", "AUTH-1", "FLEET-1", "BATCH-A", "DIESEL", "100", "20260606100500", "VOID", "LOC-1"],
            ["ACT-2", "AUTH-1", "FLEET-1", "BATCH-A", "DIESEL", "100", "20260606100600", "VOID", "LOC-1"],
            ["ACT-3", "AUTH-10", "FLEET-1", "BATCH-A", "DIESEL", "100", "20260606100700", "VOID", "LOC-1"],
            ["ACT-4", "AUTH-2", "FLEET-X", "BATCH-A", "GAS", "200", "20260606100700", "LIMIT", "LOC-2"],
        ],
        [["BATCH-A", "20260606095900", "20260606110000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["MATCHED", "UNMATCHED", "MATCHED", "UNMATCHED"]
    assert [r["kind"] for r in rows] == ["DIESEL", "", "DIESEL", ""]
    assert summary == {"matched_count": 2, "matched_amount": 200, "unmatched_count": 2, "unmatched_amount": 300}


def test_m1_location_only_mismatch_blocks_otherwise_valid_match():
    """Location must match exactly; a location-only mismatch must not match."""
    build_program()
    write_inputs(
        [["AUTH-LOC", "FLEET-L", "BATCH-L", "DIESEL", "50", "20260606100000", "SETTLED", "LOC-A"]],
        [["ACT-LOC", "AUTH-LOC", "FLEET-L", "BATCH-L", "DIESEL", "50", "20260606100100", "VOID", "LOC-B"]],
        [["BATCH-L", "20260606095900", "20260606110000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["kind"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 50}


def test_m1_header_addressed_inputs_extra_columns_and_stale_outputs_regenerated():
    """Runtime CSV parsing must use headers, ignore extras, and overwrite stale outputs."""
    build_program()
    write_inputs(
        [["ignored", "SETTLED", "LOC-9", "20260606101000", "BATCH-H", "030", "GAS", "FLEET-H", "AUTH-H"]],
        [["VOID", "LOC-9", "030", "20260606101100", "GAS", "BATCH-H", "FLEET-H", "AUTH-H", "ACT-H", "ignored"]],
        [["OPEN", "20260606100000", "BATCH-H", "20260606110000", "ignored"]],
        source_header=["extra", "status", "location", "source_ts", "batch_id", "amount", "kind", "fleet_id", "auth_id"],
        action_header=["reason", "location", "amount", "action_ts", "kind", "batch_id", "fleet_id", "auth_id", "action_id", "extra"],
        window_header=["state", "open_ts", "batch_id", "close_ts", "extra"],
    )
    rows, summary = run_program()
    assert rows == [{"action_id": "ACT-H", "auth_id": "AUTH-H", "fleet_id": "FLEET-H", "batch_id": "BATCH-H", "kind": "GAS", "amount": "030", "reason": "VOID", "status": "MATCHED"}]
    assert summary == {"matched_count": 1, "matched_amount": 30, "unmatched_count": 0, "unmatched_amount": 0}


def test_m1_amount_base10_preservation_and_invalid_unmatched_accounting():
    """Amounts compare as positive base-10 integers but report the trimmed correction string."""
    build_program()
    write_inputs(
        [["AUTH-A", "FLEET-A", "BATCH-A", "DIESEL", "7", "20260606100000", "SETTLED", "LOC-A"]],
        [
            ["ACT-A", "AUTH-A", "FLEET-A", "BATCH-A", "DIESEL", "007", "20260606100100", "VOID", "LOC-A"],
            ["ACT-B", "AUTH-B", "FLEET-A", "BATCH-A", "DIESEL", "0", "20260606100200", "VOID", "LOC-A"],
            ["ACT-C", "AUTH-C", "FLEET-A", "BATCH-A", "DIESEL", "12.5", "20260606100300", "VOID", "LOC-A"],
            ["ACT-D", "AUTH-D", "FLEET-A", "BATCH-A", "DIESEL", "-4", "20260606100400", "VOID", "LOC-A"],
        ],
        [["BATCH-A", "20260606095900", "20260606110000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["amount"] == "007"
    assert [r["status"] for r in rows[1:]] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary == {"matched_count": 1, "matched_amount": 7, "unmatched_count": 3, "unmatched_amount": 0}


def test_m1_status_reason_location_batch_and_timestamp_gates():
    """Status, reason, location, batch, and timestamp ordering are all required gates."""
    build_program()
    write_inputs(
        [
            ["AUTH-S", "FLEET-S", "BATCH-S", "DIESEL", "10", "20260606100000", "PENDING", "LOC-S"],
            ["AUTH-R", "FLEET-S", "BATCH-S", "DIESEL", "11", "20260606100000", "SETTLED", "LOC-S"],
            ["AUTH-L", "FLEET-S", "BATCH-S", "GAS", "12", "20260606100000", "SETTLED", "LOC-S"],
            ["AUTH-B", "FLEET-S", "BATCH-X", "GAS", "13", "20260606100000", "SETTLED", "LOC-S"],
            ["AUTH-T", "FLEET-S", "BATCH-S", "DIESEL", "14", "20260606101000", "SETTLED", "LOC-S"],
        ],
        [
            ["ACT-S", "AUTH-S", "FLEET-S", "BATCH-S", "DIESEL", "10", "20260606100100", "VOID", "LOC-S"],
            ["ACT-R", "AUTH-R", "FLEET-S", "BATCH-S", "DIESEL", "11", "20260606100100", "INFO", "LOC-S"],
            ["ACT-L", "AUTH-L", "FLEET-S", "BATCH-S", "GAS", "12", "20260606100100", "LIMIT", "OTHER"],
            ["ACT-B", "AUTH-B", "FLEET-S", "BATCH-S", "GAS", "13", "20260606100100", "LIMIT", "LOC-S"],
            ["ACT-T", "AUTH-T", "FLEET-S", "BATCH-S", "DIESEL", "14", "20260606100959", "VOID", "LOC-S"],
        ],
        [["BATCH-S", "20260606095900", "20260606110000", "OPEN"], ["BATCH-X", "20260606095900", "20260606110000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["UNMATCHED"] * 5
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 5, "unmatched_amount": 60}


def test_m1_rejects_ev_and_legacy_aliases_even_when_other_gates_match():
    """Milestone 1 accepts only canonical DIESEL and GAS, not EV or legacy aliases."""
    build_program()
    write_inputs(
        [
            ["AUTH-EV", "FLEET-K", "BATCH-K", "EV", "21", "20260606100000", "SETTLED", "LOC-K"],
            ["AUTH-DSL", "FLEET-K", "BATCH-K", "DSL", "22", "20260606100000", "SETTLED", "LOC-K"],
            ["AUTH-PET", "FLEET-K", "BATCH-K", "PETROL", "23", "20260606100000", "SETTLED", "LOC-K"],
        ],
        [
            ["ACT-EV", "AUTH-EV", "FLEET-K", "BATCH-K", "EV", "21", "20260606100100", "VOID", "LOC-K"],
            ["ACT-DSL", "AUTH-DSL", "FLEET-K", "BATCH-K", "DIESEL", "22", "20260606100100", "VOID", "LOC-K"],
            ["ACT-PET", "AUTH-PET", "FLEET-K", "BATCH-K", "GAS", "23", "20260606100100", "VOID", "LOC-K"],
        ],
        [["BATCH-K", "20260606095900", "20260606110000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert [r["kind"] for r in rows] == ["", "", ""]
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 3, "unmatched_amount": 66}


def test_m1_equal_candidate_tie_uses_earliest_source_row_before_later_milestones_change_selection():
    """Before dated candidate ranking is introduced, equivalent candidates use source input order."""
    build_program()
    write_inputs(
        [
            ["AUTH-TIE", "FLEET-T", "BATCH-T", "GAS", "40", "20260606100500", "SETTLED", "LOC-T"],
            ["AUTH-TIE", "FLEET-T", "BATCH-T", "DIESEL", "40", "20260606100500", "SETTLED", "LOC-T"],
        ],
        [
            ["ACT-TIE-1", "AUTH-TIE", "FLEET-T", "BATCH-T", "GAS", "40", "20260606100600", "VOID", "LOC-T"],
            ["ACT-TIE-2", "AUTH-TIE", "FLEET-T", "BATCH-T", "DIESEL", "40", "20260606100600", "VOID", "LOC-T"],
        ],
        [["BATCH-T", "20260606095900", "20260606110000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [r["kind"] for r in rows] == ["GAS", "DIESEL"]
    assert summary == {"matched_count": 2, "matched_amount": 80, "unmatched_count": 0, "unmatched_amount": 0}


def test_m1_non_numeric_source_action_or_window_timestamp_is_unmatched():
    """Source, action, and window timestamps must be numeric 14-digit UTC text."""
    build_program()
    write_inputs(
        [
            ["AUTH-TS1", "FLEET-TS", "BATCH-TS", "DIESEL", "31", "bad", "SETTLED", "LOC-TS"],
            ["AUTH-TS2", "FLEET-TS", "BATCH-TS", "GAS", "32", "20260606100200", "SETTLED", "LOC-TS"],
            ["AUTH-TS3", "FLEET-TS", "BATCH-BAD", "DIESEL", "33", "20260606100300", "SETTLED", "LOC-TS"],
        ],
        [
            ["ACT-TS1", "AUTH-TS1", "FLEET-TS", "BATCH-TS", "DIESEL", "31", "20260606100400", "VOID", "LOC-TS"],
            ["ACT-TS2", "AUTH-TS2", "FLEET-TS", "BATCH-TS", "GAS", "32", "bad-action", "VOID", "LOC-TS"],
            ["ACT-TS3", "AUTH-TS3", "FLEET-TS", "BATCH-BAD", "DIESEL", "33", "20260606100400", "VOID", "LOC-TS"],
        ],
        [["BATCH-TS", "20260606095900", "20260606110000", "OPEN"], ["BATCH-BAD", "short", "20260606110000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 3, "unmatched_amount": 96}


def test_m1_window_state_open_is_case_insensitive():
    """OPEN window state must be recognized after trimming and case folding."""
    build_program()
    write_inputs(
        [["AUTH-CF", "FLEET-CF", "BATCH-CF", "DIESEL", "10", "20260606100000", "SETTLED", "LOC-CF"]],
        [["ACT-CF", "AUTH-CF", "FLEET-CF", "BATCH-CF", "DIESEL", "10", "20260606100100", "VOID", "LOC-CF"]],
        [["BATCH-CF", "20260606095900", "20260606110000", "Open"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["kind"] == "DIESEL"
    assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 0, "unmatched_amount": 0}


def test_m1_reason_is_case_insensitive_after_trim():
    """Reversal reasons VOID, DUPLICATE, and LIMIT must match after trimming and case folding."""
    build_program()
    write_inputs(
        [["AUTH-CF", "FLEET-CF", "BATCH-CF", "DIESEL", "10", "20260606100000", "SETTLED", "LOC-CF"]],
        [["ACT-CF", "AUTH-CF", "FLEET-CF", "BATCH-CF", "DIESEL", "10", "20260606100100", "void", "LOC-CF"]],
        [["BATCH-CF", "20260606095900", "20260606110000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["reason"] == "void"
    assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 0, "unmatched_amount": 0}


def test_m1_duplicate_reason_can_match_settled_authorization():
    """A DUPLICATE reason reversal should match when all other milestone 1 gates pass."""
    build_program()
    write_inputs(
        [["AUTH-DUP", "FLEET-DUP", "BATCH-DUP", "GAS", "15", "20260606100000", "SETTLED", "LOC-DUP"]],
        [["ACT-DUP", "AUTH-DUP", "FLEET-DUP", "BATCH-DUP", "GAS", "15", "20260606100100", " duplicate ", "LOC-DUP"]],
        [["BATCH-DUP", "20260606095900", "20260606110000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["kind"] == "GAS"
    assert rows[0]["reason"].strip().lower() == "duplicate"
    assert summary == {"matched_count": 1, "matched_amount": 15, "unmatched_count": 0, "unmatched_amount": 0}


def test_m1_output_rows_preserve_action_order_and_unmatched_kind_blanks():
    """Report row order follows reversals.csv and unmatched rows have blank kind only."""
    build_program()
    write_inputs(
        [["AUTH-O1", "FLEET-O", "BATCH-O", "DIESEL", "50", "20260606100000", "SETTLED", "LOC-O"]],
        [
            ["ACT-O2", "AUTH-NO", "FLEET-O", "BATCH-O", "GAS", "60", "20260606100100", "VOID", "LOC-O"],
            ["ACT-O1", "AUTH-O1", "FLEET-O", "BATCH-O", "DIESEL", "50", "20260606100100", "VOID", "LOC-O"],
        ],
        [["BATCH-O", "20260606095900", "20260606110000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [r["action_id"] for r in rows] == ["ACT-O2", "ACT-O1"]
    assert rows[0]["kind"] == ""
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[1]["kind"] == "DIESEL"
    assert summary == {"matched_count": 1, "matched_amount": 50, "unmatched_count": 1, "unmatched_amount": 60}
