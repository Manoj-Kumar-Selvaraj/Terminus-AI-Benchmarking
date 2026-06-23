"""Milestone 2 tests for the Ruby spa appointment refund reconciler."""
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

class TestMilestone2:
    """Runtime alias behavior plus selected base-regression checks."""

    def setup_method(self):
        write_aliases([["MSG", "MASSAGE", "true"], ["FAC", "FACIAL", "true"], ["SAU", "SAUNA", "true"]])

    def test_carries_forward_full_identifier_and_consumption_rules(self):
        """Prefix collisions and one-time appointment consumption should still hold."""
        write_inputs(
            [["ALPHA0001", "C1", "500", "COMPLETED", "MASSAGE"], ["ALPHA0002", "C1", "500", "COMPLETED", "MASSAGE"]],
            [["ALPHA0003", "C1", "500", "MSG"], ["ALPHA0002", "C1", "500", "MSG"], ["ALPHA0002", "C1", "500", "MSG"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 1

    def test_runtime_aliases_match_and_emit_canonical_values(self):
        """The shipped runtime aliases should normalize to canonical service values."""
        write_inputs(
            [["A1", "C1", "3100", "COMPLETED", "MASSAGE"], ["A2", "C2", "3200", "COMPLETED", "FACIAL"], ["A3", "C3", "3300", "COMPLETED", "SAUNA"]],
            [["A1", "C1", "3100", "msg"], ["A2", "C2", "3200", "FAC"], ["A3", "C3", "3300", "SAU"]],
        )
        rows, summary = run_program()
        assert [row["service_area"] for row in rows] == ["MASSAGE", "FACIAL", "SAUNA"]
        assert summary["matched_amount_cents"] == 9600

    def test_appointment_alias_is_normalized_before_matching(self):
        """Appointment-side aliases must normalize before matching canonical refund services."""
        write_inputs(
            [["X1", "C1", "5000", "COMPLETED", "MSG"]],
            [["X1", "C1", "5000", "MASSAGE"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_area"] == "MASSAGE"
        assert summary["matched_count"] == 1

    def test_aliases_valid_when_enabled_column_absent(self):
        """Alias rows without an enabled column should remain eligible."""
        write_aliases([["MSG", "MASSAGE"]], headers=("alias", "canonical"))
        write_inputs(
            [["E1", "C1", "1000", "COMPLETED", "MASSAGE"]],
            [["E1", "C1", "1000", "MSG"]],
        )
        rows, _ = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_area"] == "MASSAGE"

    def test_padded_alias_token_is_trimmed_before_lookup(self):
        """Alias lookup specifically should trim surrounding spaces before matching."""
        write_inputs([["TRIM1", "C1", "1000", "COMPLETED", "MASSAGE"]], [["TRIM1", "C1", "1000", " MSG "]])
        rows, _ = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_area"] == "MASSAGE"

    def test_runtime_alias_file_is_authoritative_not_hardcoded(self):
        """Removing FAC from the runtime alias file should make FAC refunds unmatched."""
        write_aliases([["MSG", "MASSAGE", "true"], ["SAU", "SAUNA", "true"]])
        write_inputs([["AUTH1", "C1", "2000", "COMPLETED", "FACIAL"], ["AUTH2", "C2", "2100", "COMPLETED", "MASSAGE"]], [["AUTH1", "C1", "2000", "FAC"], ["AUTH2", "C2", "2100", "MSG"]])
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert summary["matched_amount_cents"] == 2100

    def test_invalid_alias_targets_and_disabled_aliases_are_ignored(self):
        """Unsupported canonical targets and disabled aliases should not make rows eligible."""
        write_aliases([["BAD", "CHECK", "true"], ["OFF", "MASSAGE", "false"], ["OK", "SAUNA", "true"]])
        write_inputs([["IA1", "C1", "100", "COMPLETED", "CHECK"], ["IA2", "C2", "200", "COMPLETED", "MASSAGE"], ["IA3", "C3", "300", "COMPLETED", "SAUNA"]], [["IA1", "C1", "100", "BAD"], ["IA2", "C2", "200", "OFF"], ["IA3", "C3", "300", "OK"]])
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "MATCHED"]
        assert summary["matched_count"] == 1

    def test_first_valid_duplicate_alias_row_wins(self):
        """The first valid alias row should remain authoritative for duplicate aliases."""
        write_aliases([["DUPE", "MASSAGE", "true"], ["DUPE", "FACIAL", "true"]])
        write_inputs([["DUPA", "C1", "1000", "COMPLETED", "MASSAGE"], ["DUPA", "C1", "1000", "COMPLETED", "FACIAL"]], [["DUPA", "C1", "1000", "DUPE"]])
        rows, _ = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_area"] == "MASSAGE"

    def test_alias_config_is_header_addressed_with_extra_columns(self):
        """Alias config should be read by header name even when columns move."""
        write_aliases([["FACIAL", "note", "true", "FACE"]], headers=("canonical", "unused", "enabled", "alias"))
        write_inputs([["HDRALIAS", "C1", "1000", "COMPLETED", "FACIAL"]], [["HDRALIAS", "C1", "1000", "FACE"]])
        rows, _ = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_area"] == "FACIAL"

    def test_canonical_service_names_work_without_alias_rows(self):
        """Canonical service names should remain valid identities."""
        write_aliases([])
        write_inputs([["CAN1", "C1", "1000", "COMPLETED", "SAUNA"]], [["CAN1", "C1", "1000", " sauna "]])
        rows, _ = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_area"] == "SAUNA"

    def test_unknown_alias_leaves_blank_unmatched_service_and_counts_amount(self):
        """Unknown aliases should not leak raw service values into the report."""
        write_inputs([["UNK1", "C1", "1000", "COMPLETED", "MASSAGE"]], [["UNK1", "C1", "1000", "ZZZ"]])
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["service_area"] == ""
        assert summary["unmatched_amount_cents"] == 1000

    def test_invalid_amount_accounting_still_applies_with_aliases(self):
        """Alias support should not change invalid amount accounting."""
        write_inputs([["BADAMT", "C1", "1000", "COMPLETED", "MASSAGE"]], [["BADAMT", "C1", "010x", "MSG"]])
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["amount_cents"] == "010x"
        assert summary == {"matched_count": 0, "matched_amount_cents": 0, "unmatched_count": 1, "unmatched_amount_cents": 0}
