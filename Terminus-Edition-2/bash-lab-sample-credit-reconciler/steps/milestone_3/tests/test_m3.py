"""Verifier tests for the lab credit reconciliation CLI."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCES = APP / "data" / "samples.csv"
ACTIONS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"


def write_inputs(source_rows, action_rows, calendar_rows=None):
    """Replace input CSV files with a focused scenario and clear previous outputs."""
    SOURCES.write_text("sample_id,patient_id,amount_cents,status,payer,result_date\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text("sample_id,patient_id,amount_cents,payer,credit_date\n" + "\n".join(action_rows) + "\n")
    if calendar_rows is None:
        calendar_rows = ["2026-04-01 open"]
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_undated_inputs(source_rows, action_rows, calendar_rows=None):
    """Write legacy milestone 2 CSV shapes and clear previous outputs."""
    SOURCES.write_text("sample_id,patient_id,amount_cents,status,payer\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text("sample_id,patient_id,amount_cents,payer\n" + "\n".join(action_rows) + "\n")
    if calendar_rows is None:
        calendar_rows = ["2026-04-01 closed"]
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the reconciliation script and return parsed outputs."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone3:
    def test_undated_inputs_preserve_milestone_2_alias_matching(self):
        """Older CSVs without date columns should continue to use milestone 2 matching."""
        write_undated_inputs(
            [
                "SAMPLE880000001,PATIENT_ID01,0000004100,FINAL,CARD",
                "SAMPLE880000002,PATIENT_ID02,0000004200,FINAL,INSURANCE",
            ],
            [
                "SAMPLE880000001,PATIENT_ID01,0000004100,cc",
                "SAMPLE880000002,PATIENT_ID02,0000004200,ins",
            ],
            ["2026-04-01 closed"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["payer"] for row in rows] == ["CARD", "INSURANCE"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 8300

    def test_open_credit_date_and_latest_result_date_win(self):
        """Latest eligible result_date should be observable through the row left unconsumed."""
        write_inputs(
            [
                "SAMPLE900000001,PATIENT_ID01,0000005000,FINAL,CASH,2026-04-10",
                "SAMPLE900000001,PATIENT_ID01,0000005000,FINAL,CASH,2026-04-12",
                "SAMPLE900000002,PATIENT_ID02,0000006000,FINAL,CARD,2026-04-05",
            ],
            [
                "SAMPLE900000001,PATIENT_ID01,0000005000,CASH,2026-04-10",
                "SAMPLE900000001,PATIENT_ID01,0000005000,CASH,2026-04-11",
                "SAMPLE900000002,PATIENT_ID02,0000006000,CARD,2026-04-07",
            ],
            [
                "2026-04-05 open",
                "2026-04-07 open",
                "2026-04-10 open",
                "2026-04-11 open",
                "2026-04-12 open",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary["matched_amount_cents"] == 5000
        assert summary["matched_count"] == 1
        assert summary["unmatched_count"] == 2
        assert summary["unmatched_amount_cents"] == 11000

    def test_same_result_date_duplicates_are_consumed_by_row_position(self):
        """Same-date duplicate samples should be consumed as separate rows."""
        write_inputs(
            [
                "SAMPLE910000001,PATIENT_ID01,0000004100,FINAL,INSURANCE,2026-04-30",
                "SAMPLE910000001,PATIENT_ID01,0000004100,FINAL,INSURANCE,2026-04-30",
            ],
            [
                "SAMPLE910000001,PATIENT_ID01,0000004100,INSURANCE,2026-04-20",
                "SAMPLE910000001,PATIENT_ID01,0000004100,INSURANCE,2026-04-28",
                "SAMPLE910000001,PATIENT_ID01,0000004100,INSURANCE,2026-04-20",
            ],
            ["2026-04-20 open", "2026-04-29 open", "2026-04-30 open"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert summary["matched_count"] == 2
        assert summary["unmatched_count"] == 1
        assert summary["matched_amount_cents"] == 8200
        assert summary["unmatched_amount_cents"] == 4100

    def test_closed_credit_date_is_not_eligible(self):
        """Closed credit_date should not be eligible."""
        write_inputs(
            ["SAMPLE920000001,PATIENT_ID01,0000005100,FINAL,CASH,2026-04-30"],
            ["SAMPLE920000001,PATIENT_ID01,0000005100,CASH,2026-04-10"],
            ["2026-04-10 closed", "2026-04-30 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_unlisted_credit_date_is_not_eligible(self):
        """Unlisted credit_date should not be treated as open."""
        write_inputs(
            ["SAMPLE930000001,PATIENT_ID01,0000005200,FINAL,CARD,2026-04-30"],
            ["SAMPLE930000001,PATIENT_ID01,0000005200,CARD,2026-04-10"],
            ["2026-04-30 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["unmatched_amount_cents"] == 5200

    def test_unlisted_result_date_is_not_eligible(self):
        """Unlisted result_date should not be treated as open."""
        write_inputs(
            ["SAMPLE931000001,PATIENT_ID01,0000005250,FINAL,CARD,2026-04-20"],
            ["SAMPLE931000001,PATIENT_ID01,0000005250,CARD,2026-04-10"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["payer"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 5250

    def test_malformed_dates_are_not_eligible_even_if_listed_open(self):
        """Malformed date tokens should not pass the calendar gate."""
        write_inputs(
            ["SAMPLE931500001,PATIENT_ID01,0000005275,FINAL,CASH,2026-4-20"],
            ["SAMPLE931500001,PATIENT_ID01,0000005275,CASH,2026-04-10"],
            ["2026-04-10 open", "2026-4-20 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["payer"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 5275

    def test_same_day_credit_and_result_date_matches(self):
        """Same-day open credit_date and result_date should produce MATCHED."""
        write_inputs(
            ["SAMPLE932000001,PATIENT_ID01,0000006000,FINAL,CASH,2026-05-15"],
            ["SAMPLE932000001,PATIENT_ID01,0000006000,CASH,2026-05-15"],
            ["2026-05-15 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["payer"] == "CASH"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 6000

    def test_prior_trim_case_and_full_identifier_rules_still_apply_with_dates(self):
        """Dated matching should preserve trimming, case normalization, and full sample_id equality."""
        write_inputs(
            [
                "  SAMPLEM3TRIM01  ,  PATIENT_ID01  , 0000006600 , final , card ,2026-05-20",
                "SAMPLEM3FULL01,PATIENT_ID02,0000003300,FINAL,CASH,2026-05-20",
                "SAMPLEM3FULL02,PATIENT_ID02,0000003300,FINAL,CASH,2026-05-20",
            ],
            [
                " SAMPLEM3TRIM01 , PATIENT_ID01 , 0000006600 , CARD ,2026-05-19",
                "SAMPLEM3FULL03,PATIENT_ID02,0000003300,CASH,2026-05-19",
                "SAMPLEM3FULL02,PATIENT_ID02,0000003300,CASH,2026-05-19",
            ],
            ["2026-05-19 open", "2026-05-20 open"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["payer"] for row in rows] == ["CARD", "", "CASH"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 9900
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 3300

    def test_missing_credit_date_is_not_eligible(self):
        """Missing credit_date should not match."""
        write_inputs(
            ["SAMPLE940000001,PATIENT_ID01,0000005300,FINAL,CARD,2026-04-30"],
            ["SAMPLE940000001,PATIENT_ID01,0000005300,CARD,"],
            ["2026-04-30 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_source_without_result_date_is_not_eligible(self):
        """Missing source result_date should not match."""
        write_inputs(
            ["SAMPLE950000001,PATIENT_ID01,0000005400,FINAL,CASH,"],
            ["SAMPLE950000001,PATIENT_ID01,0000005400,CASH,2026-04-10"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"

    def test_credit_date_after_result_date_is_not_eligible(self):
        """credit_date later than result_date must stay UNMATCHED even when both are open."""
        write_inputs(
            ["SAMPLE951000001,PATIENT_ID01,0000005450,FINAL,CASH,2026-04-10"],
            ["SAMPLE951000001,PATIENT_ID01,0000005450,CASH,2026-04-12"],
            ["2026-04-10 open", "2026-04-12 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_calendar_open_state_is_case_insensitive(self):
        """Calendar OPEN tokens should match case-insensitively."""
        write_inputs(
            ["SAMPLE942000001,PATIENT_ID01,0000005600,FINAL,CASH,2026-04-30"],
            ["SAMPLE942000001,PATIENT_ID01,0000005600,CASH,2026-04-10"],
            ["2026-04-10 Open", "2026-04-30 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert summary["matched_count"] == 1

    def test_equal_result_date_tie_prefers_earliest_sample_row(self):
        """When multiple samples share the latest result_date, choose the earliest input row."""
        write_inputs(
            [
                "SAMPLE992000001,PATIENT_ID01,0000004100,FINAL,INSURANCE,2026-04-30",
                "SAMPLE992000001,PATIENT_ID01,0000004200,FINAL,INSURANCE,2026-04-30",
            ],
            [
                "SAMPLE992000001,PATIENT_ID01,0000004100,INSURANCE,2026-04-20",
                "SAMPLE992000001,PATIENT_ID01,0000004200,INSURANCE,2026-04-20",
            ],
            ["2026-04-20 open", "2026-04-30 open"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["amount_cents"] for row in rows] == ["0000004100", "0000004200"]
        assert summary["matched_amount_cents"] == 8300

    def test_exactly_two_open_days_before_source_date_is_eligible(self):
        """Exactly two open days after the credit_date through the result_date should still match."""
        write_inputs(
            ["SAMPLE970000001,PATIENT_ID01,0000005700,FINAL,CASH,2026-04-04"],
            ["SAMPLE970000001,PATIENT_ID01,0000005700,CASH,2026-04-01"],
            ["2026-04-01 open", "2026-04-02 open", "2026-04-03 closed", "2026-04-04 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert summary["matched_count"] == 1

    def test_three_open_days_before_source_date_is_not_eligible(self):
        """Three open days after the credit_date through the result_date should reject the match."""
        write_inputs(
            ["SAMPLE970000002,PATIENT_ID01,0000005800,FINAL,CASH,2026-04-04"],
            ["SAMPLE970000002,PATIENT_ID01,0000005800,CASH,2026-04-01"],
            ["2026-04-01 open", "2026-04-02 open", "2026-04-03 open", "2026-04-04 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 5800



    def test_closed_result_date_is_not_eligible(self):
        """A closed result_date should reject the match even when the credit_date is open and in range."""
        write_inputs(
            ["SAMPLE980000001,PATIENT_ID01,0000005900,FINAL,CASH,2026-04-04"],
            ["SAMPLE980000001,PATIENT_ID01,0000005900,CASH,2026-04-02"],
            ["2026-04-02 open", "2026-04-03 open", "2026-04-04 closed"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["payer"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 5900

    def test_alias_matches_with_dates_and_emits_canonical_payer(self):
        """Alias handling should still work with date controls."""
        write_inputs(
            ["SAMPLE960000001,PATIENT_ID01,0000005500,FINAL,CASH,2026-04-30"],
            ["SAMPLE960000001,PATIENT_ID01,0000005500,CA,2026-04-10"],
            ["2026-04-10 open", "2026-04-30 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["payer"] == "CASH"
        assert summary["matched_amount_cents"] == 5500
