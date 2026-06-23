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

class TestMilestone3:
    """Dated matching, calendar gates, latest-date selection, and regressions."""

    def test_latest_service_date_wins_with_two_genuinely_qualifying_candidates(self):
        """Latest service_date must be selected when multiple rows pass all prior gates."""
        write_calendar(["2026-04-04 open"])
        write_inputs(
            [
                ["D1", "C1", "500", "COMPLETED", "FACIAL", "2026-04-05"],
                ["D1", "C1", "700", "COMPLETED", "FACIAL", "2026-04-08"],
            ],
            [
                ["D1", "C1", "700", "FAC", "2026-04-04"],
                ["D1", "C1", "500", "FAC", "2026-04-04"],
            ],
            source_headers=DATED_APPT_HEADERS,
            refund_headers=DATED_REFUND_HEADERS,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["amount_cents"] for row in rows] == ["700", "500"]
        assert summary["matched_count"] == 2

    def test_same_service_date_tie_uses_earliest_appointment_row_and_consumption(self):
        """When dates tie, earliest input row order should decide and then consumption should apply."""
        write_calendar(["2026-04-04 open"])
        write_inputs(
            [
                ["TIE1", "C1", "100", "COMPLETED", "SAUNA", "2026-04-08"],
                ["TIE1", "C1", "200", "COMPLETED", "SAUNA", "2026-04-08"],
                ["TIE1", "C1", "300", "COMPLETED", "SAUNA", "2026-04-08"],
            ],
            [
                ["TIE1", "C1", "100", "SAU", "2026-04-04"],
                ["TIE1", "C1", "200", "SAU", "2026-04-04"],
            ],
            source_headers=DATED_APPT_HEADERS,
            refund_headers=DATED_REFUND_HEADERS,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["amount_cents"] for row in rows] == ["100", "200"]
        assert summary["matched_count"] == 2
        assert summary["unmatched_count"] == 0

    def test_closed_unlisted_missing_and_malformed_refund_dates_are_ineligible(self):
        """Refund dates must be valid and open in the calendar."""
        write_calendar(["# comment", "2026-04-01 open", "2026-04-02 CLOSED", "bad row here"])
        write_inputs(
            [["CAL1", "C1", "100", "COMPLETED", "MASSAGE", "2026-04-05"], ["CAL2", "C2", "200", "COMPLETED", "MASSAGE", "2026-04-05"], ["CAL3", "C3", "300", "COMPLETED", "MASSAGE", "2026-04-05"], ["CAL4", "C4", "400", "COMPLETED", "MASSAGE", "2026-04-05"], ["CAL5", "C5", "500", "COMPLETED", "MASSAGE", "2026-04-05"]],
            [["CAL1", "C1", "100", "MSG", "2026-04-01"], ["CAL2", "C2", "200", "MSG", "2026-04-02"], ["CAL3", "C3", "300", "MSG", "2026-04-03"], ["CAL4", "C4", "400", "MSG", ""], ["CAL5", "C5", "500", "MSG", "04/01/2026"]],
            source_headers=DATED_APPT_HEADERS,
            refund_headers=DATED_REFUND_HEADERS,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary["unmatched_count"] == 4

    def test_refund_after_service_date_and_missing_service_date_are_ineligible(self):
        """Refund date must not be later than service_date, and service_date is required."""
        write_calendar(["2026-04-07 open"])
        write_inputs(
            [["AFTER1", "C1", "100", "COMPLETED", "MASSAGE", "2026-04-05"], ["AFTER2", "C2", "200", "COMPLETED", "MASSAGE", ""]],
            [["AFTER1", "C1", "100", "MASSAGE", "2026-04-07"], ["AFTER2", "C2", "200", "MASSAGE", "2026-04-07"]],
            source_headers=DATED_APPT_HEADERS,
            refund_headers=DATED_REFUND_HEADERS,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert summary["unmatched_amount_cents"] == 300

    def test_invalid_iso_dates_are_rejected_even_when_calendar_text_matches(self):
        """Only exact YYYY-MM-DD valid calendar dates should be accepted."""
        write_calendar(["2026-02-30 open", "20260401 open", "2026-04-01 open"])
        write_inputs(
            [["ISO1", "C1", "100", "COMPLETED", "MASSAGE", "2026-02-30"], ["ISO2", "C2", "200", "COMPLETED", "MASSAGE", "20260401"], ["ISO3", "C3", "300", "COMPLETED", "MASSAGE", "2026-04-03"]],
            [["ISO1", "C1", "100", "MASSAGE", "2026-02-30"], ["ISO2", "C2", "200", "MASSAGE", "20260401"], ["ISO3", "C3", "300", "MASSAGE", "2026-04-01"]],
            source_headers=DATED_APPT_HEADERS,
            refund_headers=DATED_REFUND_HEADERS,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "MATCHED"]
        assert summary["matched_amount_cents"] == 300

    def test_old_schema_without_dates_preserves_alias_matching(self):
        """Earlier undated CSV shapes should continue to work."""
        write_inputs([["OLD1", "C1", "500", "COMPLETED", "SAUNA"]], [["OLD1", "C1", "500", "SAU"]])
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_area"] == "SAUNA"
        assert summary["matched_count"] == 1

    def test_multiple_open_calendar_dates_and_comments_are_supported(self):
        """Calendar parsing should tolerate comments, blanks, and multiple open dates."""
        write_calendar(["# header", "", "2026-04-01 OPEN", "2026-04-06 open"])
        write_inputs(
            [["MULTI1", "C1", "100", "COMPLETED", "MASSAGE", "2026-04-01"], ["MULTI2", "C2", "200", "COMPLETED", "FACIAL", "2026-04-08"]],
            [["MULTI1", "C1", "100", "MSG", "2026-04-01"], ["MULTI2", "C2", "200", "FAC", "2026-04-06"]],
            source_headers=DATED_APPT_HEADERS,
            refund_headers=DATED_REFUND_HEADERS,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert summary["matched_amount_cents"] == 300

    def test_service_mismatch_still_blocks_match_with_valid_dates(self):
        """Date validity should not override service equality."""
        write_calendar(["2026-04-01 open"])
        write_inputs([["MIS1", "C1", "700", "COMPLETED", "SAUNA", "2026-04-02"]], [["MIS1", "C1", "700", "FAC", "2026-04-01"]], source_headers=DATED_APPT_HEADERS, refund_headers=DATED_REFUND_HEADERS)
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["unmatched_amount_cents"] == 700

    def test_header_reordered_dated_inputs_still_match(self):
        """Dated matching should remain header-addressed."""
        write_calendar(["2026-04-01 open"])
        write_inputs(
            [["2026-04-03", "COMPLETED", "HDRD1", "FACIAL", "C1", "900", "extra"]],
            [["FAC", "C1", "2026-04-01", "900", "HDRD1", "extra"]],
            source_headers=["service_date", "status", "appointment_id", "service_area", "client_id", "amount_cents", "unused"],
            refund_headers=["service_area", "client_id", "refund_date", "amount_cents", "appointment_id", "unused"],
        )
        rows, _ = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_area"] == "FACIAL"

    def test_latest_date_selection_happens_after_consumption(self):
        """Latest-date selection must consume the later row first and leave earlier rows for later refunds."""
        write_calendar(["2026-04-01 open"])
        write_inputs(
            [
                ["CONS1", "C1", "100", "COMPLETED", "MASSAGE", "2026-04-06"],
                ["CONS1", "C1", "200", "COMPLETED", "MASSAGE", "2026-04-08"],
                ["CONS1", "C1", "100", "COMPLETED", "MASSAGE", "2026-04-10"],
            ],
            [
                ["CONS1", "C1", "100", "MSG", "2026-04-01"],
                ["CONS1", "C1", "200", "MSG", "2026-04-01"],
            ],
            source_headers=DATED_APPT_HEADERS,
            refund_headers=DATED_REFUND_HEADERS,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["amount_cents"] for row in rows] == ["100", "200"]
        assert summary["matched_count"] == 2

    def test_invalid_amount_counting_carries_forward_in_dated_mode(self):
        """Malformed amounts remain unmatched-count only in dated mode."""
        write_calendar(["2026-04-01 open"])
        write_inputs([["DINV", "C1", "100", "COMPLETED", "MASSAGE", "2026-04-02"]], [["DINV", "C1", "1x0", "MSG", "2026-04-01"]], source_headers=DATED_APPT_HEADERS, refund_headers=DATED_REFUND_HEADERS)
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary == {"matched_count": 0, "matched_amount_cents": 0, "unmatched_count": 1, "unmatched_amount_cents": 0}

    def test_outputs_remain_deterministic_after_rerun_with_new_inputs(self):
        """Fresh runs with changed inputs should not retain prior rows."""
        write_calendar(["2026-04-01 open"])
        write_inputs([["RERUN1", "C1", "100", "COMPLETED", "MASSAGE", "2026-04-02"]], [["RERUN1", "C1", "100", "MSG", "2026-04-01"]], source_headers=DATED_APPT_HEADERS, refund_headers=DATED_REFUND_HEADERS)
        first_rows, _ = run_program()
        write_inputs([["RERUN2", "C2", "200", "COMPLETED", "FACIAL", "2026-04-02"]], [["RERUN2", "C2", "200", "FAC", "2026-04-01"]], source_headers=DATED_APPT_HEADERS, refund_headers=DATED_REFUND_HEADERS)
        second_rows, summary = run_program()
        assert first_rows[0]["appointment_id"] == "RERUN1"
        assert [row["appointment_id"] for row in second_rows] == ["RERUN2"]
        assert summary["matched_amount_cents"] == 200
