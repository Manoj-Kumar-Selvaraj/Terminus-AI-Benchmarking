"""Verifier tests for fleet policy controls in the fuel card reconciler."""

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
KINDS = APP / "config" / "kinds.csv"
REASONS = APP / "config" / "reasons.csv"
POLICIES = APP / "config" / "fleet_policies.csv"
REPORT = APP / "out" / "fuel_reversal_report.csv"
SUMMARY = APP / "out" / "fuel_reversal_summary.txt"
REPORT_HEADER = ["action_id", "auth_id", "fleet_id", "batch_id", "kind", "amount", "reason", "status"]


def build_program():
    """Compile the Go CLI for fleet-policy checks."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile/main.go"], check=True, cwd=APP, timeout=60)


def write_csv(path, header, rows):
    """Write a CSV file, preserving comments or blank-like rows supplied by tests."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(source_rows, action_rows, window_rows, policy_rows, policy_header=None, kind_rows=None, reason_rows=None, alias_rows=None):
    """Install data plus all config files used through the final milestone."""
    write_csv(SOURCE, ["auth_id", "fleet_id", "batch_id", "kind", "amount", "source_ts", "status", "location"], source_rows)
    write_csv(ACTION, ["action_id", "auth_id", "fleet_id", "batch_id", "kind", "amount", "action_ts", "reason", "location"], action_rows)
    write_csv(WINDOWS, ["batch_id", "open_ts", "close_ts", "state"], window_rows)
    write_csv(ALIASES, ["alias", "canonical"], alias_rows if alias_rows is not None else [["DSL", "DIESEL"], ["PETROL", "GAS"], ["CHARGE", "EV"]])
    write_csv(KINDS, ["kind", "enabled", "priority"], kind_rows if kind_rows is not None else [["DIESEL", "true", "2"], ["GAS", "true", "3"], ["EV", "true", "1"]])
    write_csv(REASONS, ["reason", "eligible"], reason_rows if reason_rows is not None else [["VOID", "Y"], ["DUPLICATE", "Y"], ["LIMIT", "Y"]])
    write_csv(POLICIES, policy_header or ["fleet_id", "batch_id", "location", "max_reversal_amount", "allow_any", "enabled"], policy_rows)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("old,output\n")
    SUMMARY.write_text("matched_count=999\n")


def run_program():
    """Run the reconciler and parse output report and summary."""
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


def test_m5_policy_is_required_and_exactly_keyed_by_fleet_batch_location():
    """A matching fleet policy row for the exact fleet, batch, and location is required."""
    build_program()
    write_inputs(
        [["AUTH-P1", "FLEET-P", "BATCH-P", "DIESEL", "100", "20260606100000", "SETTLED", "LOC-P"], ["AUTH-P2", "FLEET-P", "BATCH-P", "DIESEL", "101", "20260606100000", "SETTLED", "LOC-X"]],
        [["ACT-P1", "AUTH-P1", "FLEET-P", "BATCH-P", "DIESEL", "100", "20260606100100", "VOID", "LOC-P"], ["ACT-P2", "AUTH-P2", "FLEET-P", "BATCH-P", "DIESEL", "101", "20260606100100", "VOID", "LOC-X"]],
        [["BATCH-P", "20260606095900", "20260606110000", "OPEN"]],
        [["FLEET-P", "BATCH-P", "LOC-P", "100", "true", "true"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["MATCHED", "UNMATCHED"]
    assert summary == {"matched_count": 1, "matched_amount": 100, "unmatched_count": 1, "unmatched_amount": 101}


def test_m5_max_reversal_amount_is_inclusive_and_uses_base10_action_amount():
    """Policy max_reversal_amount is an inclusive positive integer ceiling."""
    build_program()
    write_inputs(
        [["AUTH-MAX1", "FLEET-M", "BATCH-M", "DIESEL", "75", "20260606100000", "SETTLED", "LOC-M"], ["AUTH-MAX2", "FLEET-M", "BATCH-M", "DIESEL", "76", "20260606100000", "SETTLED", "LOC-M"]],
        [["ACT-MAX1", "AUTH-MAX1", "FLEET-M", "BATCH-M", "DIESEL", "075", "20260606100100", "VOID", "LOC-M"], ["ACT-MAX2", "AUTH-MAX2", "FLEET-M", "BATCH-M", "DIESEL", "76", "20260606100100", "VOID", "LOC-M"]],
        [["BATCH-M", "20260606095900", "20260606110000", "OPEN"]],
        [["FLEET-M", "BATCH-M", "LOC-M", "75", "true", "true"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["MATCHED", "UNMATCHED"]
    assert rows[0]["amount"] == "075"
    assert summary == {"matched_count": 1, "matched_amount": 75, "unmatched_count": 1, "unmatched_amount": 76}


def test_m5_last_well_formed_policy_row_is_authoritative_even_when_disabled():
    """For duplicate policy keys, the last well-formed row decides enabled/max/ANY behavior."""
    build_program()
    write_inputs(
        [["AUTH-DUP", "FLEET-D", "BATCH-D", "GAS", "50", "20260606100000", "SETTLED", "LOC-D"]],
        [["ACT-DUP", "AUTH-DUP", "FLEET-D", "BATCH-D", "GAS", "50", "20260606100100", "VOID", "LOC-D"]],
        [["BATCH-D", "20260606095900", "20260606110000", "OPEN"]],
        [["FLEET-D", "BATCH-D", "LOC-D", "100", "true", "true"], ["FLEET-D", "BATCH-D", "LOC-D", "100", "true", "false"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 50}


def test_m5_malformed_policy_rows_are_ignored_without_overriding_previous_valid_policy():
    """Blank, commented, invalid boolean, or invalid max rows must not override valid policy state."""
    build_program()
    write_inputs(
        [["AUTH-MAL", "FLEET-MAL", "BATCH-MAL", "DIESEL", "40", "20260606100000", "SETTLED", "LOC-MAL"]],
        [["ACT-MAL", "AUTH-MAL", "FLEET-MAL", "BATCH-MAL", "DIESEL", "40", "20260606100100", "VOID", "LOC-MAL"]],
        [["BATCH-MAL", "20260606095900", "20260606110000", "OPEN"]],
        [["FLEET-MAL", "BATCH-MAL", "LOC-MAL", "40", "true", "true"], ["# comment", "", "", "", "", ""], ["FLEET-MAL", "BATCH-MAL", "LOC-MAL", "bad", "true", "false"], ["FLEET-MAL", "BATCH-MAL", "LOC-MAL", "40", "maybe", "false"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert summary == {"matched_count": 1, "matched_amount": 40, "unmatched_count": 0, "unmatched_amount": 0}


def test_m5_policy_header_reordering_and_whitespace_trimming():
    """Policy parsing is header-addressed and trims policy key/value fields."""
    build_program()
    write_inputs(
        [["AUTH-H", "FLEET-H", "BATCH-H", "GAS", "33", "20260606100000", "SETTLED", "LOC-H"]],
        [["ACT-H", "AUTH-H", "FLEET-H", "BATCH-H", "PETROL", "33", "20260606100100", "VOID", "LOC-H"]],
        [["BATCH-H", "20260606095900", "20260606110000", "OPEN"]],
        [["true", " 33 ", " LOC-H ", " BATCH-H ", " FLEET-H ", "true", "ignored"]],
        policy_header=["allow_any", "max_reversal_amount", "location", "batch_id", "fleet_id", "enabled", "extra"],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["kind"] == "GAS"
    assert summary["matched_amount"] == 33


def test_m5_allow_any_false_blocks_any_but_not_named_kind():
    """allow_any=false rejects ANY corrections while permitting exact named-kind corrections."""
    build_program()
    write_inputs(
        [["AUTH-A1", "FLEET-A", "BATCH-A", "EV", "60", "20260606100000", "SETTLED", "LOC-A"], ["AUTH-A2", "FLEET-A", "BATCH-A", "EV", "61", "20260606100000", "SETTLED", "LOC-A"]],
        [["ACT-A1", "AUTH-A1", "FLEET-A", "BATCH-A", "ANY", "60", "20260606100100", "VOID", "LOC-A"], ["ACT-A2", "AUTH-A2", "FLEET-A", "BATCH-A", "CHARGE", "61", "20260606100100", "VOID", "LOC-A"]],
        [["BATCH-A", "20260606095900", "20260606110000", "OPEN"]],
        [["FLEET-A", "BATCH-A", "LOC-A", "100", "false", "true"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["UNMATCHED", "MATCHED"]
    assert [r["kind"] for r in rows] == ["", "EV"]
    assert summary == {"matched_count": 1, "matched_amount": 61, "unmatched_count": 1, "unmatched_amount": 60}


def test_m5_any_true_still_uses_latest_timestamp_then_kind_priority():
    """A policy that allows ANY must preserve milestone 4 candidate ranking."""
    build_program()
    write_inputs(
        [["AUTH-RANK", "FLEET-R", "BATCH-R", "DIESEL", "80", "20260606100000", "SETTLED", "LOC-R"], ["AUTH-RANK", "FLEET-R", "BATCH-R", "GAS", "80", "20260606100200", "SETTLED", "LOC-R"], ["AUTH-RANK", "FLEET-R", "BATCH-R", "EV", "80", "20260606100200", "SETTLED", "LOC-R"]],
        [["ACT-RANK", "AUTH-RANK", "FLEET-R", "BATCH-R", "ANY", "80", "20260606100300", "VOID", "LOC-R"]],
        [["BATCH-R", "20260606095900", "20260606110000", "OPEN"]],
        [["FLEET-R", "BATCH-R", "LOC-R", "100", "true", "true"]],
        kind_rows=[["DIESEL", "true", "1"], ["GAS", "true", "5"], ["EV", "true", "2"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["kind"] == "EV"
    assert summary["matched_count"] == 1


def test_m5_policy_gate_does_not_bypass_reason_kind_or_window_config():
    """Enabled policies must not weaken previous reason, kind, or window gates."""
    build_program()
    write_inputs(
        [["AUTH-G1", "FLEET-G", "BATCH-G", "DIESEL", "20", "20260606100000", "SETTLED", "LOC-G"], ["AUTH-G2", "FLEET-G", "BATCH-C", "DIESEL", "21", "20260606100000", "SETTLED", "LOC-G"], ["AUTH-G3", "FLEET-G", "BATCH-G", "EV", "22", "20260606100000", "SETTLED", "LOC-G"]],
        [["ACT-G1", "AUTH-G1", "FLEET-G", "BATCH-G", "DIESEL", "20", "20260606100100", "INFO", "LOC-G"], ["ACT-G2", "AUTH-G2", "FLEET-G", "BATCH-C", "DIESEL", "21", "20260606100100", "VOID", "LOC-G"], ["ACT-G3", "AUTH-G3", "FLEET-G", "BATCH-G", "CHARGE", "22", "20260606100100", "VOID", "LOC-G"]],
        [["BATCH-G", "20260606095900", "20260606110000", "OPEN"], ["BATCH-C", "20260606095900", "20260606110000", "CLOSED"]],
        [["FLEET-G", "BATCH-G", "LOC-G", "100", "true", "true"], ["FLEET-G", "BATCH-C", "LOC-G", "100", "true", "true"]],
        kind_rows=[["DIESEL", "true", "1"], ["GAS", "true", "2"], ["EV", "false", "3"]],
        reason_rows=[["VOID", "Y"], ["INFO", "N"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 3, "unmatched_amount": 63}


def test_m5_source_consumption_after_policy_filtering_uses_remaining_eligible_rows():
    """Rows blocked by policy must not consume sources; later eligible actions can still match."""
    build_program()
    write_inputs(
        [["AUTH-CONS", "FLEET-C", "BATCH-C", "DIESEL", "90", "20260606100000", "SETTLED", "LOC-C"], ["AUTH-CONS", "FLEET-C", "BATCH-C", "DIESEL", "90", "20260606100100", "SETTLED", "LOC-C"]],
        [["ACT-C1", "AUTH-CONS", "FLEET-C", "BATCH-C", "ANY", "90", "20260606100200", "VOID", "LOC-C"], ["ACT-C2", "AUTH-CONS", "FLEET-C", "BATCH-C", "DIESEL", "90", "20260606100300", "VOID", "LOC-C"], ["ACT-C3", "AUTH-CONS", "FLEET-C", "BATCH-C", "DIESEL", "90", "20260606100400", "VOID", "LOC-C"]],
        [["BATCH-C", "20260606095900", "20260606110000", "OPEN"]],
        [["FLEET-C", "BATCH-C", "LOC-C", "90", "false", "true"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["UNMATCHED", "MATCHED", "MATCHED"]
    assert summary == {"matched_count": 2, "matched_amount": 180, "unmatched_count": 1, "unmatched_amount": 90}


def test_m5_policy_boolean_fields_are_case_insensitive():
    """Policy allow_any and enabled must accept mixed-case true and false text values."""
    build_program()
    write_inputs(
        [["AUTH-CI", "FLEET-X", "BATCH-X", "DIESEL", "50", "20260606100000", "SETTLED", "LOC-X"]],
        [["ACT-CI", "AUTH-CI", "FLEET-X", "BATCH-X", "DIESEL", "50", "20260606100100", "VOID", "LOC-X"]],
        [["BATCH-X", "20260606095900", "20260606110000", "OPEN"]],
        [["FLEET-X", "BATCH-X", "LOC-X", "50", "True", "TRUE"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert summary == {"matched_count": 1, "matched_amount": 50, "unmatched_count": 0, "unmatched_amount": 0}


def test_m5_outputs_are_regenerated_after_policy_changes_between_runs():
    """Policy changes between runs should be reflected without stale output reuse."""
    build_program()
    common_source = [["AUTH-RE", "FLEET-RE", "BATCH-RE", "DIESEL", "45", "20260606100000", "SETTLED", "LOC-RE"]]
    common_action = [["ACT-RE", "AUTH-RE", "FLEET-RE", "BATCH-RE", "DIESEL", "45", "20260606100100", "VOID", "LOC-RE"]]
    common_window = [["BATCH-RE", "20260606095900", "20260606110000", "OPEN"]]
    write_inputs(common_source, common_action, common_window, [["FLEET-RE", "BATCH-RE", "LOC-RE", "45", "true", "false"]])
    rows1, summary1 = run_program()
    write_inputs(common_source, common_action, common_window, [["FLEET-RE", "BATCH-RE", "LOC-RE", "45", "true", "true"]])
    rows2, summary2 = run_program()
    assert rows1[0]["status"] == "UNMATCHED"
    assert rows2[0]["status"] == "MATCHED"
    assert summary1 == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 45}
    assert summary2 == {"matched_count": 1, "matched_amount": 45, "unmatched_count": 0, "unmatched_amount": 0}
