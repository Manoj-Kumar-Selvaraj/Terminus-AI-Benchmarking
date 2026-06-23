"""Milestone 3 verifier tests for dated tasting refund reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
WINS = APP / "data" / "tastings.csv"
ACTION_FILE = APP / "data" / "tasting_refunds.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "winery_refund_report.csv"
SUMMARY = APP / "out" / "winery_refund_summary.json"
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
    WINS.write_text("tasting_id,guest_id,amount_cents,status,flight_tier,tasting_date\n" + "\n".join(bill_rows) + "\n")
    ACTION_FILE.write_text("tasting_id,guest_id,amount_cents,flight_tier,refund_date\n" + "\n".join(credit_rows) + "\n")
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
    """Date gates and latest eligible source-row selection for action rows."""

    def test_open_refund_date_and_latest_tasting_date_win(self):
        """Open action dates should gate matching and the latest eligible source date should win."""
        write_inputs(
            [
                "WIN9301,CUST9301,1000,COMPLETED,RED,2026-04-03",
                "WIN9301,CUST9301,1000,COMPLETED,WHITE,2026-04-04",
                "WIN9302,CUST9302,2000,COMPLETED,WHITE,2026-04-02",
                "WIN9303,CUST9303,3000,COMPLETED,MIXED,2026-04-05",
                "WIN9304,CUST9304,4000,COMPLETED,MIXED,2026-04-05",
            ],
            [
                "WIN9301,CUST9301,1000,WH,2026-04-02",
                "WIN9302,CUST9302,2000,WH,2026-04-04",
                "WIN9303,CUST9303,3000,MX,2026-04-06",
                "WIN9304,CUST9304,4000,MIXED,2026-04-07",
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
        assert rows[0]["flight_tier"] == "WHITE"
        assert [row["flight_tier"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_tasting_date_tie_uses_record_order_and_consumption(self):
        """Same-date candidates should use source row order and still enforce consumption."""
        write_inputs(
            [
                "WIN9401,CUST9401,500,COMPLETED,WHITE,2026-04-05",
                "WIN9401,CUST9401,500,COMPLETED,WHITE,2026-04-05",
                "WIN9402,CUST9402,700,COMPLETED,RED,2026-04-05",
            ],
            [
                "WIN9401,CUST9401,500,WH,2026-04-04",
                "WIN9401,CUST9401,500,WH,2026-04-04",
                "WIN9401,CUST9401,500,WH,2026-04-04",
                "WIN9402,CUST9402,700,RED,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["flight_tier"] for row in rows] == ["WHITE", "WHITE", "", "RED"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_tasting_date_wins_before_older_record_is_used(self):
        """Latest tasting_date must win when the later input row carries the later date."""
        write_inputs(
            [
                "WIN9501,CUST9501,500,COMPLETED,RED,2026-04-03",
                "WIN9501,CUST9501,800,COMPLETED,WHITE,2026-04-06",
                "WIN9501,CUST9501,700,COMPLETED,WHITE,2026-04-05",
            ],
            [
                "WIN9501,CUST9501,800,WH,2026-04-02",
                "WIN9501,CUST9501,700,WH,2026-04-04",
                "WIN9501,CUST9501,500,RD,2026-04-03",
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

    def test_closed_refund_date_is_not_eligible(self):
        """A credit whose date is listed as closed must not match."""
        write_inputs(
            ["WIN9601,CUST9601,1000,COMPLETED,WHITE,2026-04-10"],
            ["WIN9601,CUST9601,1000,WH,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["flight_tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_refund_date_is_not_eligible(self):
        """A credit date absent from the calendar must not be treated as open."""
        write_inputs(
            ["WIN9651,CUST9651,500,COMPLETED,WHITE,2026-04-30"],
            ["WIN9651,CUST9651,500,WH,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["flight_tier"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_refund_date_is_not_eligible(self):
        """A credit with an empty refund_date must not match any source row."""
        write_inputs(
            ["WIN9701,CUST9701,900,COMPLETED,RED,2026-04-05"],
            ["WIN9701,CUST9701,900,RED,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["flight_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_record_without_tasting_date_is_not_eligible(self):
        """A source row with an empty tasting_date cannot be consumed."""
        write_inputs(
            ["WIN9801,CUST9801,700,COMPLETED,MIXED,"],
            ["WIN9801,CUST9801,700,MX,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["flight_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_alias_matches_canonical_record_and_emits_canonical_flight_tier(self):
        """A MX action row should match a MIXED source row and report the canonical flight_tier."""
        write_inputs(
            ["WIN9901,CUST9901,600,COMPLETED,MIXED,2026-04-10"],
            ["WIN9901,CUST9901,600,MX,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["flight_tier"] == "MIXED"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }


    def test_mismatched_flight_tier_does_not_match_even_with_valid_dates(self):
        """Date logic must not bypass the original flight_tier equality requirement."""
        write_inputs(
            ["WIN9851,CUST9851,775,COMPLETED,RED,2026-04-10"],
            ["WIN9851,CUST9851,775,WHITE,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["flight_tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 775

    def test_alias_matches_canonical_record_with_dated_matching(self):
        """The RD alias should still normalize to RED when date gates are present."""
        write_inputs(
            ["WIN9951,CUST9951,650,COMPLETED,RED,2026-04-10"],
            ["WIN9951,CUST9951,650,RD,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["flight_tier"] == "RED"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 650,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
