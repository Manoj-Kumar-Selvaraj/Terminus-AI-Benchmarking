"""Milestone 3 verifier tests for dated booking credit reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
BILLS = APP / "data" / "bookings.csv"
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
    BILLS.write_text("booking_id,guest_id,amount_cents,status,tour_type,tour_date\n" + "\n".join(bill_rows) + "\n")
    REFUNDS.write_text("booking_id,guest_id,amount_cents,tour_type,credit_date\n" + "\n".join(credit_rows) + "\n")
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
    """Date gates and latest eligible booking selection for credits."""

    def test_open_credit_date_and_latest_tour_date_win(self):
        """Open credit dates should gate matching and latest eligible due date should win."""
        write_inputs(
            [
                "BILL9301,CUST9301,1000,SAILED,HARBOR,2026-04-03",
                "BILL9301,CUST9301,1000,SAILED,SUNSET,2026-04-04",
                "BILL9302,CUST9302,2000,SAILED,SUNSET,2026-04-02",
                "BILL9303,CUST9303,3000,SAILED,WHALE,2026-04-05",
                "BILL9304,CUST9304,4000,SAILED,WHALE,2026-04-05",
            ],
            [
                "BILL9301,CUST9301,1000,SUN,2026-04-02",
                "BILL9302,CUST9302,2000,SUN,2026-04-04",
                "BILL9303,CUST9303,3000,WHL,2026-04-06",
                "BILL9304,CUST9304,4000,WHALE,2026-04-07",
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
        assert rows[0]["tour_type"] == "SUNSET"
        assert [row["tour_type"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_tour_date_tie_uses_record_order_and_consumption(self):
        """Same-date candidates should use booking order and still enforce consumption."""
        write_inputs(
            [
                "BILL9401,CUST9401,500,SAILED,SUNSET,2026-04-05",
                "BILL9401,CUST9401,500,SAILED,SUNSET,2026-04-05",
                "BILL9402,CUST9402,700,SAILED,HARBOR,2026-04-05",
            ],
            [
                "BILL9401,CUST9401,500,SUN,2026-04-04",
                "BILL9401,CUST9401,500,SUN,2026-04-04",
                "BILL9401,CUST9401,500,SUN,2026-04-04",
                "BILL9402,CUST9402,700,HARBOR,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["tour_type"] for row in rows] == ["SUNSET", "SUNSET", "", "HARBOR"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_tour_date_wins_before_older_record_is_used(self):
        """A later eligible due date should be consumed before an older eligible source row."""
        write_inputs(
            [
                "BILL9501,CUST9501,800,SAILED,SUNSET,2026-04-06",
                "BILL9501,CUST9501,800,SAILED,SUNSET,2026-04-03",
            ],
            [
                "BILL9501,CUST9501,800,SUN,2026-04-02",
                "BILL9501,CUST9501,800,SUN,2026-04-04",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["tour_type"] for row in rows] == ["SUNSET", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_closed_credit_date_is_not_eligible(self):
        """A credit whose date is listed as closed must not match."""
        write_inputs(
            ["BILL9601,CUST9601,1000,SAILED,SUNSET,2026-04-10"],
            ["BILL9601,CUST9601,1000,SUN,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["tour_type"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_credit_date_is_not_eligible(self):
        """A credit date absent from the calendar must not be treated as open."""
        write_inputs(
            ["BILL9651,CUST9651,500,SAILED,SUNSET,2026-04-30"],
            ["BILL9651,CUST9651,500,SUN,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["tour_type"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_credit_date_is_not_eligible(self):
        """A credit with an empty credit_date must not match any booking."""
        write_inputs(
            ["BILL9701,CUST9701,900,SAILED,HARBOR,2026-04-05"],
            ["BILL9701,CUST9701,900,HARBOR,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["tour_type"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_record_without_tour_date_is_not_eligible(self):
        """A booking with an empty tour_date cannot be consumed."""
        write_inputs(
            ["BILL9801,CUST9801,700,SAILED,WHALE,"],
            ["BILL9801,CUST9801,700,WHL,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["tour_type"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_whl_alias_matches_whale_record_and_emits_canonical_tour_type(self):
        """A WHL credit should match a WHALE booking and report the canonical tour_type."""
        write_inputs(
            ["BILL9901,CUST9901,600,SAILED,WHALE,2026-04-10"],
            ["BILL9901,CUST9901,600,WHL,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["tour_type"] == "WHALE"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }


    def test_mismatched_tour_type_does_not_match_even_with_valid_dates(self):
        """Date logic must not bypass the original tour_type equality requirement."""
        write_inputs(
            ["BILL9851,CUST9851,775,SAILED,HARBOR,2026-04-10"],
            ["BILL9851,CUST9851,775,SUNSET,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["tour_type"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 775

    def test_hbr_alias_matches_harbor_record_with_dated_matching(self):
        """The HBR alias should still normalize to HARBOR when date gates are present."""
        write_inputs(
            ["BILL9951,CUST9951,650,SAILED,HARBOR,2026-04-10"],
            ["BILL9951,CUST9951,650,HBR,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["tour_type"] == "HARBOR"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 650,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
