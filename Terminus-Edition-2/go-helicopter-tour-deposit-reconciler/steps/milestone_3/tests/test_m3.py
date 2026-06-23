"""Milestone 3 tests for dated deposit reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
SOURCE_FILE = APP / "data" / "tours.csv"
ACTION_FILE = APP / "data" / "deposits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "tour_deposit_report.csv"
SUMMARY = APP / "out" / "tour_deposit_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go deposit reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 3 tests."""
    build_program()


def write_inputs(bill_rows, credit_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated deposit scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_FILE.write_text("tour_id,passenger_id,amount_cents,status,cabin_tier,tour_date\n" + "\n".join(bill_rows) + "\n")
    ACTION_FILE.write_text("tour_id,passenger_id,amount_cents,cabin_tier,deposit_date\n" + "\n".join(credit_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_legacy_inputs(source_rows, action_rows):
    """Pre-date schema: milestone 3 must keep milestone 2 behavior without calendar gates."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_FILE.write_text(
        "tour_id,passenger_id,amount_cents,status,cabin_tier\n" + "\n".join(source_rows) + "\n"
    )
    ACTION_FILE.write_text(
        "tour_id,passenger_id,amount_cents,cabin_tier\n" + "\n".join(action_rows) + "\n"
    )
    CALENDAR.write_text("")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)




def run_program():
    """Run the compiled program and parse its CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone3:
    """Date gates and latest eligible source-row selection for deposits."""

    def test_milestone3_report_header_and_status_vocabulary(self):
        """Milestone 3 keeps the same report schema and MATCHED/UNMATCHED status labels."""
        write_legacy_inputs(
            ["HEL0001,CUST0001,100,COMPLETED,STD"],
            ["HEL0001,CUST0001,100,ST"],
        )
        rows, _ = run_program()
        with REPORT.open(newline="") as handle:
            assert handle.readline().strip() == "tour_id,passenger_id,cabin_tier,amount_cents,status"
        assert {row["status"] for row in rows} <= {"MATCHED", "UNMATCHED"}


    def test_legacy_schema_without_dates_keeps_prior_alias_and_consumption(self):
        """Pre-date inputs should keep milestone 2 matching without requiring calendar dates."""
        write_legacy_inputs(
            [
                "HEL9001,CUST9001,1200,COMPLETED,LUX",
                "HEL9001,CUST9001,1200,COMPLETED,LUX",
                "HEL9002,CUST9002,700,COMPLETED,STD",
            ],
            [
                "HEL9001,CUST9001,1200,LX",
                "HEL9001,CUST9001,1200,LX",
                "HEL9002,CUST9002,700,ST",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["cabin_tier"] for row in rows] == ["LUX", "LUX", "STD"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 3100,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }


    def test_open_deposit_date_and_latest_tour_date_win(self):
        """Open deposit_date gates matching; matched row uses canonical cabin_tier from latest tour_date."""
        write_inputs(
            [
                "HEL9301,CUST9301,1000,COMPLETED,STD,2026-04-03",
                "HEL9301,CUST9301,1000,COMPLETED,PREM,2026-04-04",
                "HEL9302,CUST9302,2000,COMPLETED,PREM,2026-04-02",
                "HEL9303,CUST9303,3000,COMPLETED,LUX,2026-04-05",
                "HEL9304,CUST9304,4000,COMPLETED,LUX,2026-04-05",
            ],
            [
                "HEL9301,CUST9301,1000,PM,2026-04-02",
                "HEL9302,CUST9302,2000,PM,2026-04-04",
                "HEL9303,CUST9303,3000,LX,2026-04-06",
                "HEL9304,CUST9304,4000,LUX,2026-04-07",
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
        assert rows[0]["cabin_tier"] == "PREM"
        assert [row["cabin_tier"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_tour_date_tie_uses_record_order_and_consumption(self):
        """Same-date candidates should use source row order and still enforce consumption."""
        write_inputs(
            [
                "HEL9401,CUST9401,500,COMPLETED,PREM,2026-04-05",
                "HEL9401,CUST9401,500,COMPLETED,PREM,2026-04-05",
                "HEL9402,CUST9402,700,COMPLETED,STD,2026-04-05",
            ],
            [
                "HEL9401,CUST9401,500,PM,2026-04-04",
                "HEL9401,CUST9401,500,PM,2026-04-04",
                "HEL9401,CUST9401,500,PM,2026-04-04",
                "HEL9402,CUST9402,700,STD,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["cabin_tier"] for row in rows] == ["PREM", "PREM", "", "STD"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_tour_date_wins_before_older_record_is_used(self):
        """Latest tour_date must win when the later input row carries the later date."""
        write_inputs(
            [
                "HEL9501,CUST9501,500,COMPLETED,STD,2026-04-03",
                "HEL9501,CUST9501,800,COMPLETED,PREM,2026-04-06",
                "HEL9501,CUST9501,700,COMPLETED,PREM,2026-04-05",
            ],
            [
                "HEL9501,CUST9501,800,PM,2026-04-02",
                "HEL9501,CUST9501,700,PM,2026-04-04",
                "HEL9501,CUST9501,500,ST,2026-04-03",
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

    def test_latest_tour_date_wins_with_same_cabin_tier_candidates(self):
        """When cabin_tier ties, the source row with later tour_date must be selected."""
        write_inputs(
            [
                "HEL9511,CUST9511,500,COMPLETED,PREM,2026-04-03",
                "HEL9511,CUST9511,500,COMPLETED,PREM,2026-04-06",
            ],
            [
                "HEL9511,CUST9511,500,PM,2026-04-02",
            ],
            [
                "2026-04-02 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED"]
        assert [row["cabin_tier"] for row in rows] == ["PREM"]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 500,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_closed_deposit_date_is_not_eligible(self):
        """A deposit whose date is listed as closed must not match."""
        write_inputs(
            ["HEL9601,CUST9601,1000,COMPLETED,PREM,2026-04-10"],
            ["HEL9601,CUST9601,1000,PM,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["cabin_tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_deposit_date_is_not_eligible(self):
        """A deposit date absent from the calendar must not be treated as open."""
        write_inputs(
            ["HEL9651,CUST9651,500,COMPLETED,PREM,2026-04-30"],
            ["HEL9651,CUST9651,500,PM,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["cabin_tier"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_deposit_date_is_not_eligible(self):
        """A deposit with an empty deposit_date must not match any source row."""
        write_inputs(
            ["HEL9701,CUST9701,900,COMPLETED,STD,2026-04-05"],
            ["HEL9701,CUST9701,900,STD,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["cabin_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_record_without_tour_date_is_not_eligible(self):
        """A source row with an empty tour_date cannot be consumed."""
        write_inputs(
            ["HEL9801,CUST9801,700,COMPLETED,LUX,"],
            ["HEL9801,CUST9801,700,LX,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["cabin_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_lx_alias_matches_canonical_record_and_emits_canonical_cabin_tier(self):
        """A LX action row should match a LUX source row and report the canonical cabin_tier."""
        write_inputs(
            ["HEL9901,CUST9901,600,COMPLETED,LUX,2026-04-10"],
            ["HEL9901,CUST9901,600,LX,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["cabin_tier"] == "LUX"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }


    def test_mismatched_cabin_tier_does_not_match_even_with_valid_dates(self):
        """Date logic must not bypass the original cabin_tier equality requirement."""
        write_inputs(
            ["HEL9851,CUST9851,775,COMPLETED,STD,2026-04-10"],
            ["HEL9851,CUST9851,775,PREM,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["cabin_tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 775

    def test_alias_matches_canonical_record_with_dated_matching(self):
        """The ST alias should still normalize to STD when date gates are present."""
        write_inputs(
            ["HEL9951,CUST9951,650,COMPLETED,STD,2026-04-10"],
            ["HEL9951,CUST9951,650,ST,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["cabin_tier"] == "STD"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 650,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_deposit_date_after_tour_date_stays_unmatched(self):
        """A deposit_date later than the source tour_date must stay unmatched."""
        write_inputs(
            ["HEL9751,CUST9751,600,COMPLETED,PREM,2026-04-05"],
            ["HEL9751,CUST9751,600,PM,2026-04-06"],
            ["2026-04-06 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["cabin_tier"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 600,
        }
