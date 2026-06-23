"""Milestone 3 verifier tests for dated claim credit reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
CLAIMS = APP / "data" / "claims.csv"
CREDITS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go credit reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 3 tests."""
    build_program()


def write_inputs(claim_rows, credit_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated credit scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    CLAIMS.write_text("claim_id,patient_id,amount_cents,status,procedure,service_date\n" + "\n".join(claim_rows) + "\n")
    CREDITS.write_text("claim_id,patient_id,amount_cents,procedure,credit_date\n" + "\n".join(credit_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse its CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone3:
    """Date gates and latest eligible claim selection for credits."""

    def test_open_calendar_date_allows_matching(self):
        """Credits whose calendar date is listed as open (case-insensitive) may match eligible claims."""
        write_inputs(
            ["BILL9301,CUST9301,1000,APPROVED,RESTORATIVE,2026-04-04"],
            ["BILL9301,CUST9301,1000,RESTORATIVE,2026-04-02"],
            ["2026-04-02 OpEn"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["procedure"] == "RESTORATIVE"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 1000

    def test_three_credits_match_two_tied_claim_rows_once(self):
        """Three credits against two tied claim rows should match twice and leave one unmatched."""
        write_inputs(
            [
                "BILL9401,CUST9401,500,APPROVED,RESTORATIVE,2026-04-05",
                "BILL9401,CUST9401,500,APPROVED,RESTORATIVE,2026-04-05",
            ],
            [
                "BILL9401,CUST9401,500,REST,2026-04-04",
                "BILL9401,CUST9401,500,REST,2026-04-04",
                "BILL9401,CUST9401,500,REST,2026-04-04",
            ],
            ["2026-04-04 open", "2026-04-05 open"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["procedure"] for row in rows] == ["RESTORATIVE", "RESTORATIVE", ""]
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_preventive_credit_matches_on_open_calendar_date(self):
        """A preventive credit should match when its credit_date is listed as open."""
        write_inputs(
            ["BILL9402,CUST9402,700,APPROVED,PREVENTIVE,2026-04-05"],
            ["BILL9402,CUST9402,700,PREVENTIVE,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["procedure"] == "PREVENTIVE"
        assert summary["matched_count"] == 1

    def test_two_credits_match_two_service_date_rows(self):
        """Two credits against two eligible service_date rows for the same claim should both match."""
        write_inputs(
            [
                "BILL9501,CUST9501,800,APPROVED,RESTORATIVE,2026-04-03",
                "BILL9501,CUST9501,800,APPROVED,RESTORATIVE,2026-04-06",
            ],
            [
                "BILL9501,CUST9501,800,REST,2026-04-03",
                "BILL9501,CUST9501,800,REST,2026-04-03",
            ],
            ["2026-04-03 open"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["procedure"] for row in rows] == ["RESTORATIVE", "RESTORATIVE"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_credit_date_after_service_date_is_not_eligible(self):
        """A credit_date later than the claim service_date must not match even when the calendar is open."""
        write_inputs(
            ["BILL9671,CUST9671,500,APPROVED,RESTORATIVE,2026-04-10"],
            ["BILL9671,CUST9671,500,REST,2026-04-15"],
            ["2026-04-15 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["procedure"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_calendar_date_and_state_trim_whitespace_before_compare(self):
        """Calendar date and state tokens with surrounding spaces should still gate matching."""
        write_inputs(
            ["BILL9681,CUST9681,600,APPROVED,RESTORATIVE,2026-04-10"],
            ["BILL9681,CUST9681,600,REST,2026-04-05"],
            ["  2026-04-05   open  "],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["procedure"] == "RESTORATIVE"

    def test_closed_credit_date_is_not_eligible(self):
        """A credit whose date is listed as closed must not match."""
        write_inputs(
            ["BILL9601,CUST9601,1000,APPROVED,RESTORATIVE,2026-04-10"],
            ["BILL9601,CUST9601,1000,REST,2026-04-05"],
            ["2026-04-05   closed  "],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["procedure"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_credit_date_is_not_eligible(self):
        """A credit date absent from the calendar must not be treated as open."""
        write_inputs(
            ["BILL9651,CUST9651,500,APPROVED,RESTORATIVE,2026-04-30"],
            ["BILL9651,CUST9651,500,REST,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["procedure"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_malformed_credit_date_is_not_eligible_even_when_listed_open(self):
        """A malformed credit_date must not match even if the calendar lists that text as open."""
        write_inputs(
            ["BILL9661,CUST9661,650,APPROVED,RESTORATIVE,2026-04-30"],
            ["BILL9661,CUST9661,650,REST,0000-00-00"],
            ["0000-00-00 open", "2026-04-30 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["procedure"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 650,
        }

    def test_missing_credit_date_is_not_eligible(self):
        """A credit with an empty credit_date must not match any claim."""
        write_inputs(
            ["BILL9701,CUST9701,900,APPROVED,PREVENTIVE,2026-04-05"],
            ["BILL9701,CUST9701,900,PREVENTIVE,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["procedure"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_malformed_service_date_claim_is_not_eligible(self):
        """Malformed service_date values (invalid month/day shape) cannot be consumed."""
        write_inputs(
            ["BILL9851,CUST9851,450,APPROVED,RESTORATIVE,0000-00-00"],
            ["BILL9851,CUST9851,450,REST,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["procedure"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 450,
        }

    def test_invalid_month_service_date_claim_is_not_eligible(self):
        """A service_date with month outside 01-12 is malformed and cannot be consumed."""
        write_inputs(
            ["BILL9841,CUST9841,400,APPROVED,RESTORATIVE,2026-13-01"],
            ["BILL9841,CUST9841,400,REST,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["procedure"] == ""
        assert summary["unmatched_amount_cents"] == 400

    def test_non_numeric_credit_date_is_not_eligible(self):
        """A credit_date with non-numeric month digits is malformed and cannot match."""
        write_inputs(
            ["BILL9821,CUST9821,300,APPROVED,RESTORATIVE,2026-04-30"],
            ["BILL9821,CUST9821,300,REST,2026-ab-05"],
            ["2026-ab-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["procedure"] == ""
        assert summary["unmatched_amount_cents"] == 300

    def test_invalid_day_credit_date_is_not_eligible(self):
        """A credit_date with day outside 01-31 is malformed and cannot match."""
        write_inputs(
            ["BILL9831,CUST9831,350,APPROVED,RESTORATIVE,2026-04-30"],
            ["BILL9831,CUST9831,350,REST,2026-04-32"],
            ["2026-04-32 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["procedure"] == ""
        assert summary["unmatched_amount_cents"] == 350

    def test_claim_without_service_date_is_not_eligible(self):
        """A claim with an empty service_date cannot be consumed."""
        write_inputs(
            ["BILL9801,CUST9801,700,APPROVED,ORTHO,"],
            ["BILL9801,CUST9801,700,ORT,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["procedure"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_dated_report_preserves_credit_input_order(self):
        """Dated batches must keep credit input order in the report."""
        write_inputs(
            [
                "BILL9941,CUST9941,100,APPROVED,PREVENTIVE,2026-04-10",
                "BILL9942,CUST9942,200,APPROVED,RESTORATIVE,2026-04-10",
            ],
            [
                "BILL9942,CUST9942,200,RESTORATIVE,2026-04-05",
                "BILL9941,CUST9941,100,PREVENTIVE,2026-04-05",
            ],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert [row["claim_id"] for row in rows] == ["BILL9942", "BILL9941"]
        assert summary["matched_count"] == 2

    def test_report_schema_and_summary_fields_are_stable(self):
        """Dated batches must keep the required report header and summary JSON field names."""
        write_inputs(
            ["BILL9921,CUST9921,100,APPROVED,PREVENTIVE,2026-04-10"],
            ["BILL9921,CUST9921,100,PREV,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "claim_id,patient_id,procedure,amount_cents,status"
        assert set(summary.keys()) == {
            "matched_count",
            "matched_amount_cents",
            "unmatched_count",
            "unmatched_amount_cents",
        }
        assert all(isinstance(summary[key], int) for key in summary)
        assert rows[0]["status"] == "MATCHED"

    def test_unmatched_report_fields_are_trimmed(self):
        """Unmatched dated credits must not carry incidental surrounding spaces in report fields."""
        write_inputs(
            ["BILL9911,CUST9911,900,APPROVED,RESTORATIVE,2026-04-10"],
            [" INV9912 , CUST9912 , 700 , REST , 2026-04-05 "],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["claim_id"] == "INV9912"
        assert rows[0]["patient_id"] == "CUST9912"
        assert rows[0]["amount_cents"] == "700"
        assert rows[0]["procedure"] == ""

    def test_matching_trims_status_case_on_dated_batches(self):
        """Dated matching should still accept case-insensitive approved claim status values."""
        write_inputs(
            ["BILL9931,CUST9931,600,approved,PREVENTIVE,2026-04-10"],
            ["BILL9931,CUST9931,600,PREV,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["procedure"] == "PREVENTIVE"
        assert summary["matched_count"] == 1

    def test_prev_alias_matches_preventive_claim_and_emits_canonical_procedure(self):
        """A PREV credit should match a PREVENTIVE claim and report the canonical procedure."""
        write_inputs(
            ["BILL9951,CUST9951,550,APPROVED,PREVENTIVE,2026-04-10"],
            ["BILL9951,CUST9951,550,PREV,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["procedure"] == "PREVENTIVE"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 550,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_ort_alias_matches_ortho_claim_and_emits_canonical_procedure(self):
        """An ORT credit should match an ORTHO claim and report the canonical procedure."""
        write_inputs(
            ["BILL9901,CUST9901,600,APPROVED,ORTHO,2026-04-10"],
            ["BILL9901,CUST9901,600,ORT,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["procedure"] == "ORTHO"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
