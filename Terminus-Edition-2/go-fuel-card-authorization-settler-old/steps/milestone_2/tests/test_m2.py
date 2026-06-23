"""Verifier tests for runtime kind alias support in the fuel card reconciler."""

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
    """Compile the Go CLI for one alias-focused verifier scenario."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile/main.go"], check=True, cwd=APP, timeout=60)


def write_csv(path, header, rows):
    """Write a runtime CSV fixture with explicit headers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(source_rows, action_rows, window_rows, alias_rows=None, alias_header=None):
    """Replace source, action, window, and alias inputs for a scenario."""
    write_csv(SOURCE, ["auth_id", "fleet_id", "batch_id", "kind", "amount", "source_ts", "status", "location"], source_rows)
    write_csv(ACTION, ["action_id", "auth_id", "fleet_id", "batch_id", "kind", "amount", "action_ts", "reason", "location"], action_rows)
    write_csv(WINDOWS, ["batch_id", "open_ts", "close_ts", "state"], window_rows)
    write_csv(ALIASES, alias_header or ["alias", "canonical"], alias_rows if alias_rows is not None else [["DSL", "DIESEL"], ["PETROL", "GAS"], ["CHARGE", "EV"]])
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the binary and return parsed output artifacts."""
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


def test_m2_runtime_aliases_canonical_output_and_ev_enabled():
    """Aliases from kind_aliases.csv should unlock canonical DIESEL, GAS, and EV output."""
    build_program()
    write_inputs(
        [
            ["AUTH-D", "FLEET-A", "BATCH-A", "DIESEL", "100", "20260606100000", "SETTLED", "LOC-A"],
            ["AUTH-G", "FLEET-A", "BATCH-A", "GAS", "200", "20260606100000", "SETTLED", "LOC-A"],
            ["AUTH-E", "FLEET-A", "BATCH-A", "EV", "300", "20260606100000", "SETTLED", "LOC-A"],
        ],
        [
            ["ACT-D", "AUTH-D", "FLEET-A", "BATCH-A", "dsl", "100", "20260606100100", "VOID", "LOC-A"],
            ["ACT-G", "AUTH-G", "FLEET-A", "BATCH-A", " petrol ", "200", "20260606100100", "DUPLICATE", "LOC-A"],
            ["ACT-E", "AUTH-E", "FLEET-A", "BATCH-A", "CHARGE", "300", "20260606100100", "LIMIT", "LOC-A"],
        ],
        [["BATCH-A", "20260606095900", "20260606110000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [r["kind"] for r in rows] == ["DIESEL", "GAS", "EV"]
    assert summary == {"matched_count": 3, "matched_amount": 600, "unmatched_count": 0, "unmatched_amount": 0}


def test_m2_source_side_alias_mixed_case_and_whitespace_normalized():
    """Source-side alias values must trim and case-fold before canonical comparison."""
    build_program()
    write_inputs(
        [["AUTH-MIX", "FLEET-M", "BATCH-M", " dSl ", "81", "20260606100000", "SETTLED", "LOC-M"]],
        [["ACT-MIX", "AUTH-MIX", "FLEET-M", "BATCH-M", "DIESEL", "81", "20260606100100", "VOID", "LOC-M"]],
        [["BATCH-M", "20260606095900", "20260606110000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["kind"] == "DIESEL"
    assert summary == {"matched_count": 1, "matched_amount": 81, "unmatched_count": 0, "unmatched_amount": 0}


def test_m2_alias_file_is_runtime_authoritative_not_hardcoded_to_shipped_rows():
    """Removing a shipped alias and adding a new one should affect matching immediately."""
    build_program()
    write_inputs(
        [
            ["AUTH-REMOVED", "FLEET-R", "BATCH-R", "DIESEL", "90", "20260606100000", "SETTLED", "LOC-R"],
            ["AUTH-NEW", "FLEET-R", "BATCH-R", "GAS", "91", "20260606100000", "SETTLED", "LOC-R"],
        ],
        [
            ["ACT-REMOVED", "AUTH-REMOVED", "FLEET-R", "BATCH-R", "DSL", "90", "20260606100100", "VOID", "LOC-R"],
            ["ACT-NEW", "AUTH-NEW", "FLEET-R", "BATCH-R", "UNLEADED", "91", "20260606100100", "VOID", "LOC-R"],
        ],
        [["BATCH-R", "20260606095900", "20260606110000", "OPEN"]],
        alias_rows=[["UNLEADED", "GAS"], ["CHARGE", "EV"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["UNMATCHED", "MATCHED"]
    assert [r["kind"] for r in rows] == ["", "GAS"]
    assert summary == {"matched_count": 1, "matched_amount": 91, "unmatched_count": 1, "unmatched_amount": 90}


def test_m2_alias_header_reordering_first_valid_alias_and_invalid_target_rejection():
    """Alias rows are header-addressed; first valid alias wins and unsupported targets are ignored."""
    build_program()
    write_inputs(
        [
            ["AUTH-FIRST", "FLEET-F", "BATCH-F", "DIESEL", "77", "20260606100000", "SETTLED", "LOC-F"],
            ["AUTH-BAD", "FLEET-F", "BATCH-F", "GAS", "78", "20260606100000", "SETTLED", "LOC-F"],
        ],
        [
            ["ACT-FIRST", "AUTH-FIRST", "FLEET-F", "BATCH-F", "BIO", "77", "20260606100100", "VOID", "LOC-F"],
            ["ACT-BAD", "AUTH-BAD", "FLEET-F", "BATCH-F", "MYSTERY", "78", "20260606100100", "VOID", "LOC-F"],
        ],
        [["BATCH-F", "20260606095900", "20260606110000", "OPEN"]],
        alias_rows=[["DIESEL", "BIO", "ignored"], ["GAS", "BIO", "ignored"], ["HYDROGEN", "MYSTERY", "ignored"]],
        alias_header=["canonical", "alias", "extra"],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["MATCHED", "UNMATCHED"]
    assert rows[0]["kind"] == "DIESEL"
    assert summary == {"matched_count": 1, "matched_amount": 77, "unmatched_count": 1, "unmatched_amount": 78}


def test_m2_unknown_kinds_do_not_match_even_when_both_sides_equal():
    """Unknown normalized values remain unmatched even if source and action both use them."""
    build_program()
    write_inputs(
        [["AUTH-X", "FLEET-X", "BATCH-X", "HYDROGEN", "60", "20260606100000", "SETTLED", "LOC-X"]],
        [["ACT-X", "AUTH-X", "FLEET-X", "BATCH-X", "HYDROGEN", "60", "20260606100100", "VOID", "LOC-X"]],
        [["BATCH-X", "20260606095900", "20260606110000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["kind"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 60}


def test_m2_aliases_preserve_all_milestone1_full_key_gates_and_consumption():
    """Alias normalization must not weaken exact identity, timestamp, reason, or consumption gates."""
    build_program()
    write_inputs(
        [
            ["AUTH-CARRY", "FLEET-C", "BATCH-C", "DIESEL", "44", "20260606100000", "SETTLED", "LOC-C"],
            ["AUTH-CARRY", "FLEET-C", "BATCH-C", "DIESEL", "44", "20260606100200", "SETTLED", "OTHER"],
        ],
        [
            ["ACT-1", "AUTH-CARRY", "FLEET-C", "BATCH-C", "DSL", "44", "20260606100100", "VOID", "LOC-C"],
            ["ACT-2", "AUTH-CARRY", "FLEET-C", "BATCH-C", "DSL", "44", "20260606100100", "VOID", "LOC-C"],
            ["ACT-3", "AUTH-CARRY", "FLEET-C", "BATCH-C", "DSL", "44", "20260606100100", "INFO", "LOC-C"],
            ["ACT-4", "AUTH-CARRY", "FLEET-C", "BATCH-C", "DSL", "44", "20260606100100", "VOID", "OTHER"],
        ],
        [["BATCH-C", "20260606095900", "20260606110000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary == {"matched_count": 1, "matched_amount": 44, "unmatched_count": 3, "unmatched_amount": 132}


def test_m2_source_alias_and_action_canonical_can_match_after_normalization():
    """Normalization applies to source and action kind fields before comparison."""
    build_program()
    write_inputs(
        [["AUTH-SRC-ALIAS", "FLEET-SA", "BATCH-SA", "PETROL", "83", "20260606100000", "SETTLED", "LOC-SA"]],
        [["ACT-SRC-ALIAS", "AUTH-SRC-ALIAS", "FLEET-SA", "BATCH-SA", "GAS", "083", "20260606100100", "VOID", "LOC-SA"]],
        [["BATCH-SA", "20260606095900", "20260606110000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["kind"] == "GAS"
    assert rows[0]["amount"] == "083"
    assert summary == {"matched_count": 1, "matched_amount": 83, "unmatched_count": 0, "unmatched_amount": 0}


def test_m2_any_is_not_a_wildcard_before_milestone4():
    """The literal ANY kind remains ineligible until the later config-policy milestone."""
    build_program()
    write_inputs(
        [["AUTH-ANY", "FLEET-A", "BATCH-A", "DIESEL", "70", "20260606100000", "SETTLED", "LOC-A"]],
        [["ACT-ANY", "AUTH-ANY", "FLEET-A", "BATCH-A", "ANY", "70", "20260606100100", "VOID", "LOC-A"]],
        [["BATCH-A", "20260606095900", "20260606110000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 70}


def test_m2_blank_alias_or_canonical_rows_are_ignored():
    """Alias rows with blank alias or blank canonical values must be skipped silently."""
    build_program()
    write_inputs(
        [["AUTH-BA", "FLEET-BA", "BATCH-BA", "GAS", "62", "20260606100000", "SETTLED", "LOC-BA"]],
        [["ACT-BA", "AUTH-BA", "FLEET-BA", "BATCH-BA", "PETROL", "62", "20260606100100", "VOID", "LOC-BA"]],
        [["BATCH-BA", "20260606095900", "20260606110000", "OPEN"]],
        alias_rows=[["", "DIESEL"], ["DSL", ""], ["PETROL", "GAS"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["kind"] == "GAS"
    assert summary == {"matched_count": 1, "matched_amount": 62, "unmatched_count": 0, "unmatched_amount": 0}


def test_m2_malformed_amounts_still_count_as_unmatched_rows_not_amount_totals():
    """Alias support must retain strict amount parsing and unmatched row accounting."""
    build_program()
    write_inputs(
        [["AUTH-AMT", "FLEET-AMT", "BATCH-AMT", "DIESEL", "55", "20260606100000", "SETTLED", "LOC-AMT"]],
        [
            ["ACT-OK", "AUTH-AMT", "FLEET-AMT", "BATCH-AMT", "DSL", "055", "20260606100100", "VOID", "LOC-AMT"],
            ["ACT-BAD", "AUTH-MISS", "FLEET-AMT", "BATCH-AMT", "DSL", "5O", "20260606100200", "VOID", "LOC-AMT"],
        ],
        [["BATCH-AMT", "20260606095900", "20260606110000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["MATCHED", "UNMATCHED"]
    assert summary == {"matched_count": 1, "matched_amount": 55, "unmatched_count": 1, "unmatched_amount": 0}
