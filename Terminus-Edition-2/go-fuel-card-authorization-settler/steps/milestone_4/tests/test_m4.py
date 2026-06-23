"""Verifier tests for config-driven reason and kind policy plus ANY selection."""

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
    """Compile the Go CLI for config-policy checks."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile/main.go"], check=True, cwd=APP, timeout=60)


def write_csv(path, header, rows):
    """Write a header-addressed CSV fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def default_policy_rows(action_rows):
    """Create permissive exact policies for the action rows in a scenario."""
    seen = set()
    rows = []
    for row in action_rows:
        key = (row[2].strip(), row[3].strip(), row[8].strip())
        if key in seen:
            continue
        seen.add(key)
        rows.append([key[0], key[1], key[2], "999999", "true", "true"])
    return rows


def write_inputs(source_rows, action_rows, window_rows, alias_rows=None, kind_rows=None, reason_rows=None, policy_rows=None, kind_header=None, reason_header=None, policy_header=None):
    """Install all runtime inputs and config files used by milestone 4."""
    write_csv(SOURCE, ["auth_id", "fleet_id", "batch_id", "kind", "amount", "source_ts", "status", "location", "candidate_ref"], source_rows)
    write_csv(ACTION, ["action_id", "auth_id", "fleet_id", "batch_id", "kind", "amount", "action_ts", "reason", "location", "candidate_ref"], action_rows)
    write_csv(WINDOWS, ["batch_id", "open_ts", "close_ts", "state"], window_rows)
    write_csv(ALIASES, ["alias", "canonical"], alias_rows if alias_rows is not None else [["DSL", "DIESEL"], ["PETROL", "GAS"], ["CHARGE", "EV"]])
    write_csv(KINDS, kind_header or ["kind", "enabled", "priority"], kind_rows if kind_rows is not None else [["DIESEL", "true", "2"], ["GAS", "true", "3"], ["EV", "true", "1"]])
    write_csv(REASONS, reason_header or ["reason", "eligible"], reason_rows if reason_rows is not None else [["VOID", "Y"], ["DUPLICATE", "Y"], ["LIMIT", "Y"]])
    write_csv(POLICIES, policy_header or ["fleet_id", "batch_id", "location", "max_reversal_amount", "allow_any", "enabled"], policy_rows if policy_rows is not None else default_policy_rows(action_rows))
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the reconciler and parse report/summary outputs."""
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


def test_m4_reasons_file_is_runtime_authoritative_and_casefolded():
    """Only reasons with eligible=Y in reasons.csv are allowed, after trimming/case folding."""
    build_program()
    write_inputs(
        [["AUTH-R1", "FLEET-R", "BATCH-R", "DIESEL", "100", "20260606100000", "SETTLED", "LOC-R"], ["AUTH-R2", "FLEET-R", "BATCH-R", "DIESEL", "101", "20260606100000", "SETTLED", "LOC-R"]],
        [["ACT-R1", "AUTH-R1", "FLEET-R", "BATCH-R", "DIESEL", "100", "20260606100100", " void ", "LOC-R"], ["ACT-R2", "AUTH-R2", "FLEET-R", "BATCH-R", "DIESEL", "101", "20260606100100", "DUPLICATE", "LOC-R"]],
        [["BATCH-R", "20260606095900", "20260606110000", "OPEN"]],
        reason_rows=[["VOID", "y"], ["DUPLICATE", "N"], ["LIMIT", "Y"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["MATCHED", "UNMATCHED"]
    assert summary == {"matched_count": 1, "matched_amount": 100, "unmatched_count": 1, "unmatched_amount": 101}


def test_m4_reasons_file_is_header_addressed():
    """Reordered reason columns must retain eligible and ineligible decisions."""
    build_program()
    write_inputs(
        [
            ["AUTH-RH1", "FLEET-RH", "BATCH-RH", "DIESEL", "80", "20260606100000", "SETTLED", "LOC-RH"],
            ["AUTH-RH2", "FLEET-RH", "BATCH-RH", "DIESEL", "81", "20260606100000", "SETTLED", "LOC-RH"],
        ],
        [
            ["ACT-RH1", "AUTH-RH1", "FLEET-RH", "BATCH-RH", "DIESEL", "80", "20260606100100", "VOID", "LOC-RH"],
            ["ACT-RH2", "AUTH-RH2", "FLEET-RH", "BATCH-RH", "DIESEL", "81", "20260606100100", "DUPLICATE", "LOC-RH"],
        ],
        [["BATCH-RH", "20260606095900", "20260606110000", "OPEN"]],
        reason_header=["eligible", "reason"],
        reason_rows=[["Y", "VOID"], ["N", "DUPLICATE"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["MATCHED", "UNMATCHED"]
    assert summary == {"matched_count": 1, "matched_amount": 80, "unmatched_count": 1, "unmatched_amount": 81}


def test_m4_kinds_file_enabled_gate_rejects_disabled_otherwise_valid_kind():
    """Enabled kinds.csv rows are required even when all other gates are valid."""
    build_program()
    write_inputs(
        [["AUTH-K", "FLEET-K", "BATCH-K", "EV", "200", "20260606100000", "SETTLED", "LOC-K"]],
        [["ACT-K", "AUTH-K", "FLEET-K", "BATCH-K", "CHARGE", "200", "20260606100100", "VOID", "LOC-K"]],
        [["BATCH-K", "20260606095900", "20260606110000", "OPEN"]],
        kind_rows=[["DIESEL", "true", "2"], ["GAS", "true", "3"], ["EV", "false", "1"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["kind"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 200}


def test_m4_kind_config_header_reordered_duplicate_last_row_and_malformed_rows():
    """Kind config is header-addressed; malformed rows are ignored and last valid duplicate wins."""
    build_program()
    write_inputs(
        [["AUTH-K1", "FLEET-K", "BATCH-K", "DIESEL", "70", "20260606100000", "SETTLED", "LOC-K"], ["AUTH-K2", "FLEET-K", "BATCH-K", "GAS", "71", "20260606100000", "SETTLED", "LOC-K"]],
        [["ACT-K1", "AUTH-K1", "FLEET-K", "BATCH-K", "DSL", "70", "20260606100100", "VOID", "LOC-K"], ["ACT-K2", "AUTH-K2", "FLEET-K", "BATCH-K", "PETROL", "71", "20260606100100", "VOID", "LOC-K"]],
        [["BATCH-K", "20260606095900", "20260606110000", "OPEN"]],
        kind_rows=[["2", "true", "DIESEL"], ["1", "maybe", "GAS"], ["3", "true", "GAS"], ["4", "false", "DIESEL"]],
        kind_header=["priority", "enabled", "kind"],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["UNMATCHED", "MATCHED"]
    assert [r["kind"] for r in rows] == ["", "GAS"]
    assert summary == {"matched_count": 1, "matched_amount": 71, "unmatched_count": 1, "unmatched_amount": 70}


def test_m4_any_latest_source_ts_wins_over_better_kind_priority():
    """ANY must choose the latest source_ts before configured kind priority."""
    build_program()
    write_inputs(
        [
            ["AUTH-TS", "FLEET-A", "BATCH-A", "EV", "95", "20260606100000", "SETTLED", "LOC-A"],
            ["AUTH-TS", "FLEET-A", "BATCH-A", "DIESEL", "95", "20260606100800", "SETTLED", "LOC-A"],
        ],
        [["ACT-TS", "AUTH-TS", "FLEET-A", "BATCH-A", "ANY", "95", "20260606100900", "VOID", "LOC-A"]],
        [["BATCH-A", "20260606095900", "20260606110000", "OPEN"]],
        kind_rows=[["DIESEL", "true", "5"], ["GAS", "true", "3"], ["EV", "true", "1"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["kind"] == "DIESEL"
    assert summary == {"matched_count": 1, "matched_amount": 95, "unmatched_count": 0, "unmatched_amount": 0}


def test_m4_any_same_timestamp_uses_kind_priority_before_source_order():
    """ANY ties on source_ts are ranked by lower configured kind priority."""
    build_program()
    write_inputs(
        [["AUTH-ANY", "FLEET-A", "BATCH-A", "DIESEL", "90", "20260606100000", "SETTLED", "LOC-A"], ["AUTH-ANY", "FLEET-A", "BATCH-A", "GAS", "90", "20260606100000", "SETTLED", "LOC-A"], ["AUTH-ANY", "FLEET-A", "BATCH-A", "EV", "90", "20260606100000", "SETTLED", "LOC-A"]],
        [["ACT-ANY", "AUTH-ANY", "FLEET-A", "BATCH-A", "ANY", "90", "20260606100100", "VOID", "LOC-A"]],
        [["BATCH-A", "20260606095900", "20260606110000", "OPEN"]],
        kind_rows=[["DIESEL", "true", "5"], ["GAS", "true", "3"], ["EV", "true", "1"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["kind"] == "EV"
    assert summary["matched_amount"] == 90


def test_m4_any_equal_priority_tie_uses_earliest_source_row():
    """ANY ties after timestamp and priority should use source input row order."""
    build_program()
    write_inputs(
        [["AUTH-ANY2", "FLEET-A", "BATCH-A", "GAS", "91", "20260606100000", "SETTLED", "LOC-A"], ["AUTH-ANY2", "FLEET-A", "BATCH-A", "DIESEL", "91", "20260606100000", "SETTLED", "LOC-A"]],
        [["ACT-ANY2", "AUTH-ANY2", "FLEET-A", "BATCH-A", "ANY", "91", "20260606100100", "VOID", "LOC-A"]],
        [["BATCH-A", "20260606095900", "20260606110000", "OPEN"]],
        kind_rows=[["DIESEL", "true", "2"], ["GAS", "true", "2"], ["EV", "true", "9"]],
    )
    rows, summary = run_program()
    assert rows[0]["kind"] == "GAS"
    assert summary["matched_count"] == 1


def test_m4_any_rejects_disabled_kind_in_candidate_pool():
    """ANY may match only enabled source kinds even when a disabled kind has the latest timestamp."""
    build_program()
    write_inputs(
        [
            ["AUTH-DIS", "FLEET-D", "BATCH-D", "EV", "88", "20260606100800", "SETTLED", "LOC-D"],
            ["AUTH-DIS", "FLEET-D", "BATCH-D", "GAS", "88", "20260606100000", "SETTLED", "LOC-D"],
        ],
        [["ACT-DIS", "AUTH-DIS", "FLEET-D", "BATCH-D", "ANY", "88", "20260606100900", "VOID", "LOC-D"]],
        [["BATCH-D", "20260606095900", "20260606110000", "OPEN"]],
        kind_rows=[["DIESEL", "true", "9"], ["GAS", "true", "5"], ["EV", "false", "1"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["kind"] == "GAS"
    assert summary == {"matched_count": 1, "matched_amount": 88, "unmatched_count": 0, "unmatched_amount": 0}


def test_m4_any_consumes_selected_row_and_reranks_remaining_candidates():
    """ANY matches consume one source row and re-rank the remaining candidates per action."""
    build_program()
    write_inputs(
        [["AUTH-C", "FLEET-C", "BATCH-C", "EV", "60", "20260606100000", "SETTLED", "LOC-C"], ["AUTH-C", "FLEET-C", "BATCH-C", "DIESEL", "60", "20260606100000", "SETTLED", "LOC-C"]],
        [["ACT-C1", "AUTH-C", "FLEET-C", "BATCH-C", "ANY", "60", "20260606100100", "VOID", "LOC-C"], ["ACT-C2", "AUTH-C", "FLEET-C", "BATCH-C", "ANY", "60", "20260606100200", "VOID", "LOC-C"], ["ACT-C3", "AUTH-C", "FLEET-C", "BATCH-C", "ANY", "60", "20260606100300", "VOID", "LOC-C"]],
        [["BATCH-C", "20260606095900", "20260606110000", "OPEN"]],
        kind_rows=[["DIESEL", "true", "2"], ["GAS", "true", "3"], ["EV", "true", "1"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
    assert [r["kind"] for r in rows] == ["EV", "DIESEL", ""]
    assert summary == {"matched_count": 2, "matched_amount": 120, "unmatched_count": 1, "unmatched_amount": 60}


def test_m4_non_any_still_requires_exact_canonical_kind():
    """Config priority must not turn named-kind corrections into wildcard matches."""
    build_program()
    write_inputs(
        [["AUTH-N", "FLEET-N", "BATCH-N", "DIESEL", "44", "20260606100000", "SETTLED", "LOC-N"]],
        [["ACT-N", "AUTH-N", "FLEET-N", "BATCH-N", "GAS", "44", "20260606100100", "VOID", "LOC-N"]],
        [["BATCH-N", "20260606095900", "20260606110000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["kind"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 44}


def test_m4_runtime_alias_file_still_normalizes_before_kind_policy():
    """Aliases from kind_aliases.csv normalize before enabled kind checks."""
    build_program()
    write_inputs(
        [["AUTH-BIO", "FLEET-B", "BATCH-B", "DIESEL", "35", "20260606100000", "SETTLED", "LOC-B"]],
        [["ACT-BIO", "AUTH-BIO", "FLEET-B", "BATCH-B", "BIO", "35", "20260606100100", "VOID", "LOC-B"]],
        [["BATCH-B", "20260606095900", "20260606110000", "OPEN"]],
        alias_rows=[["BIO", "DIESEL"]],
        kind_rows=[["DIESEL", "true", "1"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["kind"] == "DIESEL"
    assert summary["matched_amount"] == 35


def test_m4_enabled_kind_and_reason_do_not_bypass_closed_window_or_latest_selection():
    """Config gates must preserve prior window-state and latest-source requirements."""
    build_program()
    write_inputs(
        [["AUTH-W", "FLEET-W", "BATCH-W", "DIESEL", "22", "20260606100000", "SETTLED", "LOC-W"], ["AUTH-L", "FLEET-L", "BATCH-L", "DIESEL", "23", "20260606100000", "SETTLED", "LOC-L"], ["AUTH-L", "FLEET-L", "BATCH-L", "DIESEL", "23", "20260606100500", "SETTLED", "LOC-L"]],
        [["ACT-W", "AUTH-W", "FLEET-W", "BATCH-W", "DIESEL", "22", "20260606100100", "VOID", "LOC-W"], ["ACT-L", "AUTH-L", "FLEET-L", "BATCH-L", "DIESEL", "23", "20260606100600", "VOID", "LOC-L"]],
        [["BATCH-W", "20260606095900", "20260606110000", "CLOSED"], ["BATCH-L", "20260606095900", "20260606110000", "OPEN"]],
        kind_rows=[["DIESEL", "true", "1"]],
        reason_rows=[["VOID", "Y"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["UNMATCHED", "MATCHED"]
    assert summary == {"matched_count": 1, "matched_amount": 23, "unmatched_count": 1, "unmatched_amount": 22}


def test_m4_duplicate_reason_rows_last_well_formed_row_wins():
    """When duplicate reason rows conflict, the last well-formed eligible value is authoritative."""
    build_program()
    write_inputs(
        [["AUTH-DR", "FLEET-DR", "BATCH-DR", "DIESEL", "52", "20260606100000", "SETTLED", "LOC-DR"]],
        [["ACT-DR", "AUTH-DR", "FLEET-DR", "BATCH-DR", "DIESEL", "52", "20260606100100", "VOID", "LOC-DR"]],
        [["BATCH-DR", "20260606095900", "20260606110000", "OPEN"]],
        reason_rows=[["VOID", "N"], ["VOID", "Y"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert summary == {"matched_count": 1, "matched_amount": 52, "unmatched_count": 0, "unmatched_amount": 0}


def test_m4_malformed_or_missing_priority_ranks_after_numeric_priorities():
    """Blank or malformed kind priorities must rank after valid numeric priorities on ANY ties."""
    build_program()
    write_inputs(
        [
            ["AUTH-MP", "FLEET-MP", "BATCH-MP", "DIESEL", "64", "20260606100000", "SETTLED", "LOC-MP"],
            ["AUTH-MP", "FLEET-MP", "BATCH-MP", "GAS", "64", "20260606100000", "SETTLED", "LOC-MP"],
            ["AUTH-MP", "FLEET-MP", "BATCH-MP", "EV", "64", "20260606100000", "SETTLED", "LOC-MP"],
        ],
        [["ACT-MP", "AUTH-MP", "FLEET-MP", "BATCH-MP", "ANY", "64", "20260606100100", "VOID", "LOC-MP"]],
        [["BATCH-MP", "20260606095900", "20260606110000", "OPEN"]],
        kind_rows=[["DIESEL", "true", ""], ["GAS", "true", "5"], ["EV", "true", "abc"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["kind"] == "GAS"
    assert summary["matched_amount"] == 64


def test_m4_missing_or_malformed_config_does_not_enable_reason_or_kind():
    """Malformed config rows are ignored rather than treated as permissive defaults."""
    build_program()
    write_inputs(
        [["AUTH-M1", "FLEET-M", "BATCH-M", "DIESEL", "11", "20260606100000", "SETTLED", "LOC-M"], ["AUTH-M2", "FLEET-M", "BATCH-M", "GAS", "12", "20260606100000", "SETTLED", "LOC-M"]],
        [["ACT-M1", "AUTH-M1", "FLEET-M", "BATCH-M", "DIESEL", "11", "20260606100100", "VOID", "LOC-M"], ["ACT-M2", "AUTH-M2", "FLEET-M", "BATCH-M", "GAS", "12", "20260606100100", "DUPLICATE", "LOC-M"]],
        [["BATCH-M", "20260606095900", "20260606110000", "OPEN"]],
        kind_rows=[["DIESEL", "maybe", "1"], ["", "true", "2"]],
        reason_rows=[["VOID", "maybe"], ["", "Y"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["UNMATCHED", "UNMATCHED"]
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 2, "unmatched_amount": 23}


def test_m4_fleet_policy_is_required_exact_and_amount_limited():
    """Fleet policy rows gate otherwise valid reversals by exact key, enabled flag, and amount limit."""
    build_program()
    write_inputs(
        [
            ["AUTH-P1", "FLEET-P", "BATCH-P", "DIESEL", "80", "20260606100000", "SETTLED", "LOC-1"],
            ["AUTH-P2", "FLEET-P", "BATCH-P", "DIESEL", "81", "20260606100000", "SETTLED", "LOC-2"],
            ["AUTH-P3", "FLEET-P", "BATCH-P", "DIESEL", "82", "20260606100000", "SETTLED", "LOC-3"],
            ["AUTH-P4", "FLEET-P", "BATCH-P", "DIESEL", "83", "20260606100000", "SETTLED", "LOC-4"],
        ],
        [
            ["ACT-P1", "AUTH-P1", "FLEET-P", "BATCH-P", "DIESEL", "80", "20260606100100", "VOID", "LOC-1"],
            ["ACT-P2", "AUTH-P2", "FLEET-P", "BATCH-P", "DIESEL", "81", "20260606100100", "VOID", "LOC-2"],
            ["ACT-P3", "AUTH-P3", "FLEET-P", "BATCH-P", "DIESEL", "82", "20260606100100", "VOID", "LOC-3"],
            ["ACT-P4", "AUTH-P4", "FLEET-P", "BATCH-P", "DIESEL", "83", "20260606100100", "VOID", "LOC-4"],
        ],
        [["BATCH-P", "20260606095900", "20260606110000", "OPEN"]],
        policy_rows=[
            ["FLEET-P", "BATCH-P", "LOC-1", "80", "true", "true"],
            ["FLEET-P", "BATCH-P", "LOC-3", "999", "true", "false"],
            ["FLEET-P", "BATCH-P", "LOC-4", "50", "true", "true"],
        ],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary == {"matched_count": 1, "matched_amount": 80, "unmatched_count": 3, "unmatched_amount": 246}


def test_m4_policy_allow_any_false_does_not_consume_source_for_later_named_match():
    """A policy that blocks ANY must not consume the source row needed by a later named reversal."""
    build_program()
    write_inputs(
        [["AUTH-PA", "FLEET-PA", "BATCH-PA", "DIESEL", "77", "20260606100000", "SETTLED", "LOC-PA"]],
        [
            ["ACT-PA1", "AUTH-PA", "FLEET-PA", "BATCH-PA", "ANY", "77", "20260606100100", "VOID", "LOC-PA"],
            ["ACT-PA2", "AUTH-PA", "FLEET-PA", "BATCH-PA", "DIESEL", "77", "20260606100200", "VOID", "LOC-PA"],
        ],
        [["BATCH-PA", "20260606095900", "20260606110000", "OPEN"]],
        policy_rows=[["FLEET-PA", "BATCH-PA", "LOC-PA", "100", "false", "true"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["UNMATCHED", "MATCHED"]
    assert [r["kind"] for r in rows] == ["", "DIESEL"]
    assert summary == {"matched_count": 1, "matched_amount": 77, "unmatched_count": 1, "unmatched_amount": 77}


def test_m4_policy_header_reordered_duplicate_last_well_formed_row_wins():
    """Policy parsing is header-addressed, ignores malformed rows, and uses the last valid duplicate."""
    build_program()
    write_inputs(
        [["AUTH-PD", "FLEET-PD", "BATCH-PD", "GAS", "66", "20260606100000", "SETTLED", "LOC-PD"]],
        [["ACT-PD", "AUTH-PD", "FLEET-PD", "BATCH-PD", "ANY", "66", "20260606100100", "VOID", "LOC-PD"]],
        [["BATCH-PD", "20260606095900", "20260606110000", "OPEN"]],
        policy_header=["allow_any", "max_reversal_amount", "location", "batch_id", "fleet_id", "enabled", "extra"],
        policy_rows=[
            ["true", "100", "LOC-PD", "BATCH-PD", "FLEET-PD", "true", "old"],
            ["maybe", "100", "LOC-PD", "BATCH-PD", "FLEET-PD", "true", "malformed"],
            ["false", "100", "LOC-PD", "BATCH-PD", "FLEET-PD", "true", "last"],
        ],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 66}


def test_m4_zero_policy_limit_is_malformed_and_does_not_override_valid_policy():
    """Zero limits are ignored, preserving prior valid rows and enabling no new key."""
    build_program()
    write_inputs(
        [
            ["AUTH-Z1", "FLEET-Z1", "BATCH-Z", "DIESEL", "50", "20260606100000", "SETTLED", "LOC-Z"],
            ["AUTH-Z2", "FLEET-Z2", "BATCH-Z", "DIESEL", "50", "20260606100000", "SETTLED", "LOC-Z"],
        ],
        [
            ["ACT-Z1", "AUTH-Z1", "FLEET-Z1", "BATCH-Z", "DIESEL", "50", "20260606100100", "VOID", "LOC-Z"],
            ["ACT-Z2", "AUTH-Z2", "FLEET-Z2", "BATCH-Z", "DIESEL", "50", "20260606100100", "VOID", "LOC-Z"],
        ],
        [["BATCH-Z", "20260606095900", "20260606110000", "OPEN"]],
        policy_rows=[
            ["FLEET-Z1", "BATCH-Z", "LOC-Z", "100", "true", "true"],
            ["FLEET-Z1", "BATCH-Z", "LOC-Z", "0", "true", "false"],
            ["FLEET-Z2", "BATCH-Z", "LOC-Z", "0", "true", "true"],
        ],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["MATCHED", "UNMATCHED"]
    assert summary == {"matched_count": 1, "matched_amount": 50, "unmatched_count": 1, "unmatched_amount": 50}


def test_m4_candidate_ref_gate_precedes_any_policy_and_consumption():
    """A reference-blocked ANY reversal must leave the row for a named match."""
    build_program()
    write_inputs(
        [["AUTH-REF", "FLEET-REF", "BATCH-REF", "DIESEL", "72", "20260606100000", "SETTLED", "LOC-REF", "ROW-A"]],
        [
            ["ACT-REF1", "AUTH-REF", "FLEET-REF", "BATCH-REF", "ANY", "72", "20260606100100", "VOID", "LOC-REF", "ROW-B"],
            ["ACT-REF2", "AUTH-REF", "FLEET-REF", "BATCH-REF", "DIESEL", "72", "20260606100200", "VOID", "LOC-REF", "ROW-A"],
        ],
        [["BATCH-REF", "20260606095900", "20260606110000", "OPEN"]],
        policy_rows=[["FLEET-REF", "BATCH-REF", "LOC-REF", "100", "true", "true"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["UNMATCHED", "MATCHED"]
    assert [r["kind"] for r in rows] == ["", "DIESEL"]
    assert summary == {"matched_count": 1, "matched_amount": 72, "unmatched_count": 1, "unmatched_amount": 72}
