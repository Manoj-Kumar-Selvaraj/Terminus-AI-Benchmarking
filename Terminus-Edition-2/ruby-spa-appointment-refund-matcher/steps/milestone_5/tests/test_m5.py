"""Milestone 5 tests for the Ruby spa appointment refund reconciler."""
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
SELECTION = APP / "out" / "appointment_selection.csv"
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
    SELECTION.unlink(missing_ok=True)


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


def read_selection():
    """Return physical appointment-row selections emitted for matched refunds."""
    with SELECTION.open(newline="") as handle:
        return list(csv.DictReader(handle))


def assert_schema(rows):
    """Assert the public report schema exactly."""
    assert rows
    assert list(rows[0].keys()) == ["appointment_id", "client_id", "service_area", "amount_cents", "status"]

class TestMilestone5:
    """Client limit policy with all prior matching behavior."""

    def setup_method(self):
        write_calendar(["2026-04-01 open", "2026-04-04 open"])
        write_aliases([["MSG", "MASSAGE", "true"], ["FAC", "FACIAL", "true"], ["SAU", "SAUNA", "true"]])
        write_methods([["MASSAGE", "true", "2"], ["FACIAL", "true", "1"], ["SAUNA", "true", "3"]])
        write_limits([["C1", "MASSAGE", "1000", "true", "true"], ["C1", "FACIAL", "1000", "true", "true"], ["C1", "SAUNA", "1000", "true", "true"]])

    def test_exact_client_service_limit_allows_matching_under_max(self):
        """A valid exact client/service policy should allow an otherwise eligible refund."""
        write_inputs([["LIM1", "C1", "900", "COMPLETED", "MASSAGE", "2026-04-05"]], [["LIM1", "C1", "0900", "MSG", "2026-04-01"]], source_headers=DATED_APPT_HEADERS, refund_headers=DATED_REFUND_HEADERS)
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["amount_cents"] == "0900"
        assert summary["matched_amount_cents"] == 900

    def test_one_cent_over_max_refund_cents_blocks_match(self):
        """Refunds one cent above max_refund_cents must stay unmatched."""
        write_limits([["C1", "MASSAGE", "1000", "true", "true"]])
        write_inputs(
            [["LIMOVER", "C1", "1001", "COMPLETED", "MASSAGE", "2026-04-05"]],
            [["LIMOVER", "C1", "1001", "MSG", "2026-04-01"]],
            source_headers=DATED_APPT_HEADERS,
            refund_headers=DATED_REFUND_HEADERS,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 1001

    def test_exact_max_refund_cents_boundary_allows_match(self):
        """Refunds with amount_cents exactly equal to max_refund_cents should match."""
        write_limits([["C1", "MASSAGE", "1000", "true", "true"]])
        write_inputs(
            [["LIMCAP", "C1", "1000", "COMPLETED", "MASSAGE", "2026-04-05"]],
            [["LIMCAP", "C1", "1000", "MSG", "2026-04-01"]],
            source_headers=DATED_APPT_HEADERS,
            refund_headers=DATED_REFUND_HEADERS,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["amount_cents"] == "1000"
        assert summary["matched_amount_cents"] == 1000

    def test_malformed_allow_any_values_are_ignored(self):
        """Malformed allow_any values should not create eligibility for ANY refunds."""
        write_limits([["C1", "MASSAGE", "1000", "true", "maybe"]])
        write_inputs(
            [["ANYMAL", "C1", "500", "COMPLETED", "MASSAGE", "2026-04-05"]],
            [["ANYMAL", "C1", "500", "ANY", "2026-04-01"]],
            source_headers=DATED_APPT_HEADERS,
            refund_headers=DATED_REFUND_HEADERS,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["service_area"] == ""
        assert summary["matched_count"] == 0

    def test_missing_policy_row_blocks_match_without_consuming_source(self):
        """No exact client/service policy should block a match and leave source available."""
        write_limits([["C1", "FACIAL", "1000", "true", "true"]])
        write_inputs([["MISSPOL", "C1", "500", "COMPLETED", "MASSAGE", "2026-04-05"]], [["MISSPOL", "C1", "500", "MSG", "2026-04-01"], ["MISSPOL", "C1", "500", "MSG", "2026-04-01"]], source_headers=DATED_APPT_HEADERS, refund_headers=DATED_REFUND_HEADERS)
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert summary["unmatched_count"] == 2

    def test_over_limit_and_disabled_policy_rows_are_ineligible(self):
        """Amount caps and disabled policies should be enforced."""
        write_limits([["C1", "MASSAGE", "400", "true", "true"], ["C2", "FACIAL", "900", "false", "true"]])
        write_inputs([["LIM2", "C1", "500", "COMPLETED", "MASSAGE", "2026-04-05"], ["LIM3", "C2", "800", "COMPLETED", "FACIAL", "2026-04-05"]], [["LIM2", "C1", "500", "MSG", "2026-04-01"], ["LIM3", "C2", "800", "FAC", "2026-04-01"]], source_headers=DATED_APPT_HEADERS, refund_headers=DATED_REFUND_HEADERS)
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert summary["unmatched_amount_cents"] == 1300

    def test_last_wellformed_duplicate_policy_row_is_authoritative(self):
        """Duplicate client/service policies should use the last well-formed row."""
        write_limits([["C1", "MASSAGE", "400", "true", "true"], ["C1", "MASSAGE", "900", "true", "true"]])
        write_inputs([["DUPPOL", "C1", "800", "COMPLETED", "MASSAGE", "2026-04-05"]], [["DUPPOL", "C1", "800", "MSG", "2026-04-01"]], source_headers=DATED_APPT_HEADERS, refund_headers=DATED_REFUND_HEADERS)
        rows, _ = run_program()
        assert rows[0]["status"] == "MATCHED"

    def test_malformed_policy_rows_are_ignored_without_crashing(self):
        """Invalid max, enabled, service, client, or short rows should not create eligibility."""
        write_limits(
            [
                ["", "MASSAGE", "1000", "true", "true"],
                ["C1", "CHECK", "1000", "true", "true"],
                ["C1", "MASSAGE", "1x", "true", "true"],
                ["C1", "MASSAGE", "1000", "maybe", "true"],
                ["C1", "GENERAL"],
                ["C1", "MASSAGE", "500"],
            ]
        )
        write_inputs([["MALPOL", "C1", "800", "COMPLETED", "MASSAGE", "2026-04-05"]], [["MALPOL", "C1", "800", "MSG", "2026-04-01"]], source_headers=DATED_APPT_HEADERS, refund_headers=DATED_REFUND_HEADERS)
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["unmatched_count"] == 1

    def test_absent_allow_any_column_defaults_to_false(self):
        """When allow_any is absent from client_limits.csv, ANY refunds must remain unmatched."""
        write_limits([["C1", "MASSAGE", "1000", "true"]], headers=("client_id", "service_area", "max_refund_cents", "enabled"))
        write_inputs(
            [["ANYDEF", "C1", "500", "COMPLETED", "MASSAGE", "2026-04-05"]],
            [["ANYDEF", "C1", "500", "ANY", "2026-04-01"]],
            source_headers=DATED_APPT_HEADERS,
            refund_headers=DATED_REFUND_HEADERS,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["service_area"] == ""
        assert summary["matched_count"] == 0

    def test_enabled_field_is_case_insensitive(self):
        """Client limit enabled values must be parsed case-insensitively."""
        write_limits([["C1", "MASSAGE", "1000", "TRUE", "True"]])
        write_inputs(
            [["ENPOL", "C1", "900", "COMPLETED", "MASSAGE", "2026-04-05"]],
            [["ENPOL", "C1", "900", "MSG", "2026-04-01"]],
            source_headers=DATED_APPT_HEADERS,
            refund_headers=DATED_REFUND_HEADERS,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert summary["matched_count"] == 1

    def test_policy_config_is_header_addressed_and_trims_client_ids(self):
        """Client limits should use headers and trim key fields."""
        write_limits([["true", "extra", " true ", " 1000 ", " MASSAGE ", " C1 "]], headers=("enabled", "note", "allow_any", "max_refund_cents", "service_area", "client_id"))
        write_inputs([["HDRPOL", " C1 ", "900", "COMPLETED", "MASSAGE", "2026-04-05"]], [["HDRPOL", "C1", "900", "MSG", "2026-04-01"]], source_headers=DATED_APPT_HEADERS, refund_headers=DATED_REFUND_HEADERS)
        rows, _ = run_program()
        assert rows[0]["status"] == "MATCHED"

    def test_alias_service_names_in_policy_are_canonicalized(self):
        """Policy service_area values should use the same runtime alias map."""
        write_limits([["C1", "MSG", "1000", "true", "true"]])
        write_inputs([["ALPOL", "C1", "900", "COMPLETED", "MASSAGE", "2026-04-05"]], [["ALPOL", "C1", "900", "MASSAGE", "2026-04-01"]], source_headers=DATED_APPT_HEADERS, refund_headers=DATED_REFUND_HEADERS)
        rows, _ = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_area"] == "MASSAGE"

    def test_any_requires_allow_any_true_for_selected_service(self):
        """ANY refunds should require allow_any on the selected client/service policy."""
        write_limits([["C1", "FACIAL", "1000", "true", "false"], ["C1", "MASSAGE", "1000", "true", "true"]])
        write_inputs(
            [["ANYLIM", "C1", "500", "COMPLETED", "FACIAL", "2026-04-08"], ["ANYLIM", "C1", "500", "COMPLETED", "MASSAGE", "2026-04-06"]],
            [["ANYLIM", "C1", "500", "ANY", "2026-04-01"]],
            source_headers=DATED_APPT_HEADERS,
            refund_headers=DATED_REFUND_HEADERS,
        )
        rows, _ = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_area"] == "MASSAGE"
        assert read_selection() == [{"refund_row": "0", "appointment_row": "1", "service_date": "2026-04-06"}]

    def test_blocked_policy_candidate_does_not_consume_source_before_later_refund(self):
        """A policy-blocked refund must not consume the appointment row."""
        write_limits([["C1", "MASSAGE", "400", "true", "true"], ["C1", "FACIAL", "1000", "true", "true"]])
        write_inputs(
            [["NOCONS", "C1", "500", "COMPLETED", "MASSAGE", "2026-04-08"], ["NOCONS", "C1", "500", "COMPLETED", "FACIAL", "2026-04-07"]],
            [["NOCONS", "C1", "500", "MSG", "2026-04-01"], ["NOCONS", "C1", "500", "ANY", "2026-04-01"]],
            source_headers=DATED_APPT_HEADERS,
            refund_headers=DATED_REFUND_HEADERS,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[1]["service_area"] == "FACIAL"
        assert summary["matched_count"] == 1
        assert read_selection() == [{"refund_row": "1", "appointment_row": "1", "service_date": "2026-04-07"}]

    def test_any_skips_disallowed_and_over_limit_candidates_before_clearing(self):
        """ANY must skip allow_any=false and over-cap candidates before selecting a later row."""
        write_limits(
            [
                ["C1", "FACIAL", "2000", "true", "false"],
                ["C1", "MASSAGE", "500", "true", "true"],
                ["C1", "SAUNA", "1000", "true", "true"],
            ]
        )
        write_inputs(
            [
                ["INT1", "C1", "600", "COMPLETED", "FACIAL", "2026-04-10"],
                ["INT1", "C1", "600", "COMPLETED", "MASSAGE", "2026-04-09"],
                ["INT1", "C1", "600", "COMPLETED", "SAUNA", "2026-04-08"],
            ],
            [["INT1", "C1", "600", "ANY", "2026-04-01"]],
            source_headers=DATED_APPT_HEADERS,
            refund_headers=DATED_REFUND_HEADERS,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_area"] == "SAUNA"
        assert summary["matched_count"] == 1
        assert read_selection() == [{"refund_row": "0", "appointment_row": "2", "service_date": "2026-04-08"}]

    def test_client_limits_do_not_bypass_prior_reason_date_or_method_gates(self):
        """A valid policy row should not override disabled methods or closed dates."""
        write_methods([["MASSAGE", "false", "1"]])
        write_calendar(["2026-04-01 closed"])
        write_limits([["C1", "MASSAGE", "1000", "true", "true"]])
        write_inputs([["BYPASS", "C1", "500", "COMPLETED", "MASSAGE", "2026-04-05"]], [["BYPASS", "C1", "500", "MSG", "2026-04-01"]], source_headers=DATED_APPT_HEADERS, refund_headers=DATED_REFUND_HEADERS)
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["unmatched_amount_cents"] == 500

    def test_invalid_amounts_still_count_unmatched_under_limits(self):
        """Limit policy should not change invalid amount accounting."""
        write_inputs([["BADLIM", "C1", "500", "COMPLETED", "MASSAGE", "2026-04-05"]], [["BADLIM", "C1", "05x", "MSG", "2026-04-01"]], source_headers=DATED_APPT_HEADERS, refund_headers=DATED_REFUND_HEADERS)
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["amount_cents"] == "05x"
        assert summary == {"matched_count": 0, "matched_amount_cents": 0, "unmatched_count": 1, "unmatched_amount_cents": 0}
