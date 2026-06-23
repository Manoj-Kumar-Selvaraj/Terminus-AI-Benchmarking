"""Milestone 3 verifier tests for dated trip credit reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
BILLS = APP / "data" / "trips.csv"
REFUNDS = APP / "data" / "credits.csv"
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


def write_inputs(bill_rows, credit_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated credit scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    BILLS.write_text("trip_id,rider_id,amount_cents,status,pass_type,ride_date\n" + "\n".join(bill_rows) + "\n")
    REFUNDS.write_text("trip_id,rider_id,amount_cents,pass_type,credit_date\n" + "\n".join(credit_rows) + "\n")
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
    """Date gates and latest eligible trip selection for credits."""

    def test_open_credit_date_and_latest_ride_date_win(self):
        """Open credit dates should gate matching and latest eligible due date should win."""
        write_inputs(
            [
                "BILL9301,CUST9301,1000,COMPLETED,DAY,2026-04-03",
                "BILL9301,CUST9301,1000,COMPLETED,MONTH,2026-04-04",
                "BILL9302,CUST9302,2000,COMPLETED,MONTH,2026-04-02",
                "BILL9303,CUST9303,3000,COMPLETED,ANNUAL,2026-04-05",
                "BILL9304,CUST9304,4000,COMPLETED,ANNUAL,2026-04-05",
            ],
            [
                "BILL9301,CUST9301,1000,MO,2026-04-02",
                "BILL9302,CUST9302,2000,MO,2026-04-04",
                "BILL9303,CUST9303,3000,AN,2026-04-06",
                "BILL9304,CUST9304,4000,ANNUAL,2026-04-07",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
                "2026-04-05 open",
                "2026-04-06 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert rows[0]["pass_type"] == "MONTH"
        assert [row["pass_type"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_ride_date_tie_uses_record_order_and_consumption(self):
        """Same-date candidates should use trip order and still enforce consumption."""
        write_inputs(
            [
                "BILL9401,CUST9401,500,COMPLETED,MONTH,2026-04-05",
                "BILL9401,CUST9401,500,COMPLETED,MONTH,2026-04-05",
                "BILL9402,CUST9402,700,COMPLETED,DAY,2026-04-05",
            ],
            [
                "BILL9401,CUST9401,500,MO,2026-04-04",
                "BILL9401,CUST9401,500,MO,2026-04-04",
                "BILL9401,CUST9401,500,MO,2026-04-04",
                "BILL9402,CUST9402,700,DAY,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["pass_type"] for row in rows] == ["MONTH", "MONTH", "", "DAY"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_ride_date_wins_before_older_record_is_used(self):
        """Latest ride_date must win when the later input row carries the later date."""
        write_inputs(
            [
                "BILL9501,CUST9501,500,COMPLETED,DAY,2026-04-03",
                "BILL9501,CUST9501,800,COMPLETED,MONTH,2026-04-06",
                "BILL9501,CUST9501,700,COMPLETED,MONTH,2026-04-05",
            ],
            [
                "BILL9501,CUST9501,800,MO,2026-04-02",
                "BILL9501,CUST9501,700,MO,2026-04-04",
                "BILL9501,CUST9501,500,DY,2026-04-03",
            ],
            [
                "2026-04-02 open",
                "2026-04-03 open",
                "2026-04-04 open",
                "2026-04-05 open",
                "2026-04-06 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 2000,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_closed_credit_date_is_not_eligible(self):
        """A credit whose date is listed as closed must not match."""
        write_inputs(
            ["BILL9601,CUST9601,1000,COMPLETED,MONTH,2026-04-10"],
            ["BILL9601,CUST9601,1000,MO,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["pass_type"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_credit_date_is_not_eligible(self):
        """A credit date absent from the calendar must not be treated as open."""
        write_inputs(
            ["BILL9651,CUST9651,500,COMPLETED,MONTH,2026-04-30"],
            ["BILL9651,CUST9651,500,MO,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["pass_type"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_credit_date_is_not_eligible(self):
        """A credit with an empty credit_date must not match any trip."""
        write_inputs(
            ["BILL9701,CUST9701,900,COMPLETED,DAY,2026-04-05"],
            ["BILL9701,CUST9701,900,DAY,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["pass_type"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_record_without_ride_date_is_not_eligible(self):
        """A trip with an empty ride_date cannot be consumed."""
        write_inputs(
            ["BILL9801,CUST9801,700,COMPLETED,ANNUAL,"],
            ["BILL9801,CUST9801,700,AN,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["pass_type"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_an_alias_matches_annual_record_and_emits_canonical_pass_type(self):
        """A AN credit should match a ANNUAL trip and report the canonical pass_type."""
        write_inputs(
            ["BILL9901,CUST9901,600,COMPLETED,ANNUAL,2026-04-10"],
            ["BILL9901,CUST9901,600,AN,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["pass_type"] == "ANNUAL"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }


    def test_mismatched_pass_type_does_not_match_even_with_valid_dates(self):
        """Date logic must not bypass the original pass_type equality requirement."""
        write_inputs(
            ["BILL9851,CUST9851,775,COMPLETED,DAY,2026-04-10"],
            ["BILL9851,CUST9851,775,MONTH,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["pass_type"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 775

    def test_dy_alias_matches_day_record_with_dated_matching(self):
        """The DY alias should still normalize to DAY when date gates are present."""
        write_inputs(
            ["BILL9951,CUST9951,650,COMPLETED,DAY,2026-04-10"],
            ["BILL9951,CUST9951,650,DY,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["pass_type"] == "DAY"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 650,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
