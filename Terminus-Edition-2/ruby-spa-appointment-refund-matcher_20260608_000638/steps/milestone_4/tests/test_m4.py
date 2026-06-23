"""Verifier tests for the Ruby spa appointment refund reconciler."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
APPOINTMENTS = APP / "data" / "appointments.csv"
REFUNDS = APP / "data" / "refunds.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
ALIASES = APP / "config" / "service_aliases.csv"
METHODS = APP / "config" / "methods.csv"
LIMITS = APP / "config" / "client_limits.csv"
REPORT = APP / "out" / "refund_report.csv"
SUMMARY = APP / "out" / "refund_summary.json"
BASE_APPT_HEADERS = ["appointment_id", "client_id", "amount_cents", "status", "service_area"]
BASE_REFUND_HEADERS = ["appointment_id", "client_id", "amount_cents", "service_area"]
DATED_APPT_HEADERS = BASE_APPT_HEADERS + ["service_date"]
DATED_REFUND_HEADERS = BASE_REFUND_HEADERS + ["refund_date"]


def write_csv(path, headers, rows):
    """Write a CSV file using the supplied headers and row arrays."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def write_inputs(source_rows, refund_rows, source_headers=None, refund_headers=None):
    """Replace appointment and refund inputs with a scenario-specific dataset."""
    write_csv(APPOINTMENTS, source_headers or BASE_APPT_HEADERS, source_rows)
    write_csv(REFUNDS, refund_headers or BASE_REFUND_HEADERS, refund_rows)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_calendar(lines):
    """Replace the open-date calendar text file."""
    CALENDAR.parent.mkdir(parents=True, exist_ok=True)
    CALENDAR.write_text("\n".join(lines) + "\n")


def write_aliases(rows, headers=("alias", "canonical", "enabled")):
    """Replace the runtime service alias configuration."""
    write_csv(ALIASES, list(headers), rows)


def write_methods(rows, headers=("service_area", "enabled", "priority")):
    """Replace the runtime service policy configuration."""
    write_csv(METHODS, list(headers), rows)


def write_limits(rows, headers=("client_id", "service_area", "max_refund_cents", "enabled", "allow_any")):
    """Replace the runtime client limit policy configuration."""
    write_csv(LIMITS, list(headers), rows)


def run_program():
    """Run the batch command and return parsed report rows plus JSON summary."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


def assert_schema(rows):
    """Assert the public report schema exactly."""
    assert rows
    assert list(rows[0].keys()) == ["appointment_id", "client_id", "service_area", "amount_cents", "status"]

class TestMilestone4:
    """Service policy, ANY matching, priority, and previous behavior."""

    def setup_method(self):
        write_calendar(["2026-04-01 open", "2026-04-04 open", "2026-04-05 open"])
        write_methods([["MASSAGE", "true", "2"], ["FACIAL", "true", "1"], ["SAUNA", "true", "3"], ["CHECK", "false", "4"]])

    def test_disabled_configured_service_rejects_otherwise_valid_refund(self):
        """A disabled service must not match even when all base gates pass."""
        write_methods([["MASSAGE", "true", "1"], ["FACIAL", "false", "2"], ["SAUNA", "true", "3"]])
        write_inputs([["POL1", "C1", "1000", "COMPLETED", "FACIAL", "2026-04-03"]], [["POL1", "C1", "1000", "FAC", "2026-04-01"]], source_headers=DATED_APPT_HEADERS, refund_headers=DATED_REFUND_HEADERS)
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["unmatched_amount_cents"] == 1000

    def test_any_selects_latest_eligible_appointment_and_emits_canonical_service(self):
        """ANY should choose the latest service_date among fully eligible candidates."""
        write_inputs(
            [["ANY1", "C1", "500", "COMPLETED", "MASSAGE", "2026-04-05"], ["ANY1", "C1", "500", "COMPLETED", "FACIAL", "2026-04-08"], ["ANY1", "C1", "500", "COMPLETED", "SAUNA", "2026-04-06"]],
            [["ANY1", "C1", "500", "ANY", "2026-04-01"]],
            source_headers=DATED_APPT_HEADERS,
            refund_headers=DATED_REFUND_HEADERS,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_area"] == "FACIAL"
        assert summary["matched_count"] == 1

    def test_any_same_date_uses_priority_before_source_order(self):
        """When service dates tie, lower configured priority should win before source order."""
        write_methods([["MASSAGE", "true", "5"], ["FACIAL", "true", "1"], ["SAUNA", "true", "2"]])
        write_inputs(
            [["ANYP1", "C1", "500", "COMPLETED", "SAUNA", "2026-04-08"], ["ANYP1", "C1", "500", "COMPLETED", "MASSAGE", "2026-04-08"], ["ANYP1", "C1", "500", "COMPLETED", "FACIAL", "2026-04-08"]],
            [["ANYP1", "C1", "500", "ANY", "2026-04-01"]],
            source_headers=DATED_APPT_HEADERS,
            refund_headers=DATED_REFUND_HEADERS,
        )
        rows, _ = run_program()
        assert rows[0]["service_area"] == "FACIAL"

    def test_any_same_date_same_priority_uses_earliest_source_row(self):
        """When date and priority tie, earliest appointment input row is the final tie-breaker."""
        write_methods([["MASSAGE", "true", "1"], ["FACIAL", "true", "1"], ["SAUNA", "true", "1"]])
        write_inputs(
            [["ANYR", "C1", "500", "COMPLETED", "SAUNA", "2026-04-08"], ["ANYR", "C1", "500", "COMPLETED", "FACIAL", "2026-04-08"], ["ANYR", "C1", "500", "COMPLETED", "MASSAGE", "2026-04-08"]],
            [["ANYR", "C1", "500", "ANY", "2026-04-01"]],
            source_headers=DATED_APPT_HEADERS,
            refund_headers=DATED_REFUND_HEADERS,
        )
        rows, _ = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_area"] == "SAUNA"

    def test_any_consumes_selected_row_and_next_refund_uses_next_best_candidate(self):
        """Consumed rows should be removed before ranking the next ANY refund."""
        write_methods([["MASSAGE", "true", "1"], ["FACIAL", "true", "2"]])
        write_inputs(
            [["ANYC", "C1", "100", "COMPLETED", "MASSAGE", "2026-04-06"], ["ANYC", "C1", "100", "COMPLETED", "FACIAL", "2026-04-05"]],
            [["ANYC", "C1", "100", "ANY", "2026-04-01"], ["ANYC", "C1", "100", "ANY", "2026-04-01"], ["ANYC", "C1", "100", "ANY", "2026-04-01"]],
            source_headers=DATED_APPT_HEADERS,
            refund_headers=DATED_REFUND_HEADERS,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["service_area"] for row in rows] == ["MASSAGE", "FACIAL", ""]
        assert summary["matched_count"] == 2

    def test_non_any_still_requires_exact_canonical_service_under_policy(self):
        """Non-ANY refunds should not use priority to switch services."""
        write_inputs([["EXACT", "C1", "900", "COMPLETED", "MASSAGE", "2026-04-05"]], [["EXACT", "C1", "900", "FAC", "2026-04-01"]], source_headers=DATED_APPT_HEADERS, refund_headers=DATED_REFUND_HEADERS)
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["unmatched_amount_cents"] == 900

    def test_methods_config_is_header_addressed_and_last_wellformed_row_wins(self):
        """Policy rows should use headers and last valid duplicate service row."""
        write_methods([["false", "old", "9", "MASSAGE"], ["true", "new", "4", "MASSAGE"]], headers=("enabled", "note", "priority", "service_area"))
        write_inputs([["METH1", "C1", "1000", "COMPLETED", "MASSAGE", "2026-04-05"]], [["METH1", "C1", "1000", "MSG", "2026-04-01"]], source_headers=DATED_APPT_HEADERS, refund_headers=DATED_REFUND_HEADERS)
        rows, _ = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_area"] == "MASSAGE"

    def test_methods_config_trims_case_folds_aliases_and_ignores_malformed_rows(self):
        """Method policy should canonicalize services and skip malformed rows."""
        write_methods([[" MSG ", " TRUE ", "1"], ["", "true", "2"], ["CHECK", "true", "3"], ["FACIAL", "maybe", "4"]])
        write_inputs([["METH2", "C1", "1000", "COMPLETED", "MASSAGE", "2026-04-05"], ["METH3", "C2", "2000", "COMPLETED", "FACIAL", "2026-04-05"]], [["METH2", "C1", "1000", "MASSAGE", "2026-04-01"], ["METH3", "C2", "2000", "FAC", "2026-04-01"]], source_headers=DATED_APPT_HEADERS, refund_headers=DATED_REFUND_HEADERS)
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert summary["matched_amount_cents"] == 1000

    def test_missing_and_malformed_priorities_rank_after_numeric_priorities(self):
        """Numeric priority should beat missing or malformed priority on same-date ANY candidates."""
        write_methods([["MASSAGE", "true", "bad"], ["FACIAL", "true", ""], ["SAUNA", "true", "7"]])
        write_inputs(
            [["PRI", "C1", "500", "COMPLETED", "MASSAGE", "2026-04-08"], ["PRI", "C1", "500", "COMPLETED", "FACIAL", "2026-04-08"], ["PRI", "C1", "500", "COMPLETED", "SAUNA", "2026-04-08"]],
            [["PRI", "C1", "500", "ANY", "2026-04-01"]],
            source_headers=DATED_APPT_HEADERS,
            refund_headers=DATED_REFUND_HEADERS,
        )
        rows, _ = run_program()
        assert rows[0]["service_area"] == "SAUNA"

    def test_any_rejects_disabled_or_missing_policy_services(self):
        """ANY should only consider services enabled by methods.csv."""
        write_methods([["MASSAGE", "false", "1"], ["FACIAL", "true", "2"]])
        write_inputs(
            [["DISANY", "C1", "500", "COMPLETED", "MASSAGE", "2026-04-09"], ["DISANY", "C1", "500", "COMPLETED", "SAUNA", "2026-04-08"], ["DISANY", "C1", "500", "COMPLETED", "FACIAL", "2026-04-07"]],
            [["DISANY", "C1", "500", "ANY", "2026-04-01"]],
            source_headers=DATED_APPT_HEADERS,
            refund_headers=DATED_REFUND_HEADERS,
        )
        rows, _ = run_program()
        assert rows[0]["service_area"] == "FACIAL"

    def test_any_is_not_emitted_and_invalid_amount_accounting_remains(self):
        """ANY should emit selected canonical service and invalid amounts stay count-only."""
        write_inputs([["ANYBAD", "C1", "500", "COMPLETED", "SAUNA", "2026-04-08"]], [["ANYBAD", "C1", "05x", "ANY", "2026-04-01"]], source_headers=DATED_APPT_HEADERS, refund_headers=DATED_REFUND_HEADERS)
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["service_area"] == ""
        assert summary == {"matched_count": 0, "matched_amount_cents": 0, "unmatched_count": 1, "unmatched_amount_cents": 0}

    def test_alias_file_changes_still_apply_under_methods_policy(self):
        """Runtime alias configuration should still be authoritative with methods enabled."""
        write_aliases([["MS", "MASSAGE", "true"]])
        write_methods([["MASSAGE", "true", "1"]])
        write_inputs([["ALM", "C1", "100", "COMPLETED", "MASSAGE", "2026-04-05"]], [["ALM", "C1", "100", "MSG", "2026-04-01"], ["ALM", "C1", "100", "MS", "2026-04-01"]], source_headers=DATED_APPT_HEADERS, refund_headers=DATED_REFUND_HEADERS)
        rows, _ = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
