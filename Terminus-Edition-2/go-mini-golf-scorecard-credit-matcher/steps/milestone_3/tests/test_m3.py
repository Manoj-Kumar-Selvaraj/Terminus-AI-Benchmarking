"""Milestone 3 verifier tests for dated credit reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
SOURCE_FILE = APP / "data" / "scorecards.csv"
ACTION_FILE = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "scorecard_credit_report.csv"
SUMMARY = APP / "out" / "scorecard_credit_summary.json"
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
    SOURCE_FILE.write_text("scorecard_id,player_id,amount_cents,status,course_tier,play_date\n" + "\n".join(bill_rows) + "\n")
    ACTION_FILE.write_text("scorecard_id,player_id,amount_cents,course_tier,credit_date\n" + "\n".join(credit_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_legacy_inputs(source_rows, action_rows):
    """Pre-date schema: milestone 3 must keep milestone 2 behavior without calendar gates."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_FILE.write_text(
        "scorecard_id,player_id,amount_cents,status,course_tier\n" + "\n".join(source_rows) + "\n"
    )
    ACTION_FILE.write_text(
        "scorecard_id,player_id,amount_cents,course_tier\n" + "\n".join(action_rows) + "\n"
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
    """Date gates and latest eligible source-row selection for credits."""

    def test_milestone3_report_header_and_status_vocabulary(self):
        """Milestone 3 keeps the same report schema and MATCHED/UNMATCHED status labels."""
        write_legacy_inputs(
            ["MGL0001,CUST0001,100,COMPLETED,FRONT"],
            ["MGL0001,CUST0001,100,FR"],
        )
        rows, _ = run_program()
        with REPORT.open(newline="") as handle:
            assert handle.readline().strip() == "scorecard_id,player_id,course_tier,amount_cents,status"
        assert {row["status"] for row in rows} <= {"MATCHED", "UNMATCHED"}


    def test_legacy_schema_without_dates_keeps_prior_alias_and_consumption(self):
        """Pre-date inputs should keep milestone 2 matching without requiring calendar dates."""
        write_legacy_inputs(
            [
                "MGL9001,CUST9001,1200,COMPLETED,FULL",
                "MGL9001,CUST9001,1200,COMPLETED,FULL",
                "MGL9002,CUST9002,700,COMPLETED,FRONT",
            ],
            [
                "MGL9001,CUST9001,1200,FL",
                "MGL9001,CUST9001,1200,FL",
                "MGL9002,CUST9002,700,FR",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["course_tier"] for row in rows] == ["FULL", "FULL", "FRONT"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 3100,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }


    def test_open_credit_date_and_latest_play_date_win(self):
        """Open credit_date gates matching; matched row uses canonical course_tier from latest play_date."""
        write_inputs(
            [
                "MGL9301,CUST9301,1000,COMPLETED,FRONT,2026-04-03",
                "MGL9301,CUST9301,1000,COMPLETED,BACK,2026-04-04",
                "MGL9302,CUST9302,2000,COMPLETED,BACK,2026-04-02",
                "MGL9303,CUST9303,3000,COMPLETED,FULL,2026-04-05",
                "MGL9304,CUST9304,4000,COMPLETED,FULL,2026-04-05",
            ],
            [
                "MGL9301,CUST9301,1000,BK,2026-04-02",
                "MGL9302,CUST9302,2000,BK,2026-04-04",
                "MGL9303,CUST9303,3000,FL,2026-04-06",
                "MGL9304,CUST9304,4000,FULL,2026-04-07",
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
        assert rows[0]["course_tier"] == "BACK"
        assert [row["course_tier"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_play_date_tie_uses_record_order_and_consumption(self):
        """Same-date candidates should use source row order and still enforce consumption."""
        write_inputs(
            [
                "MGL9401,CUST9401,500,COMPLETED,BACK,2026-04-05",
                "MGL9401,CUST9401,500,COMPLETED,BACK,2026-04-05",
                "MGL9402,CUST9402,700,COMPLETED,FRONT,2026-04-05",
            ],
            [
                "MGL9401,CUST9401,500,BK,2026-04-04",
                "MGL9401,CUST9401,500,BK,2026-04-04",
                "MGL9401,CUST9401,500,BK,2026-04-04",
                "MGL9402,CUST9402,700,FRONT,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["course_tier"] for row in rows] == ["BACK", "BACK", "", "FRONT"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_play_date_wins_before_older_record_is_used(self):
        """Latest play_date must win when the later input row carries the later date."""
        write_inputs(
            [
                "MGL9501,CUST9501,500,COMPLETED,FRONT,2026-04-03",
                "MGL9501,CUST9501,800,COMPLETED,BACK,2026-04-06",
                "MGL9501,CUST9501,700,COMPLETED,BACK,2026-04-05",
            ],
            [
                "MGL9501,CUST9501,800,BK,2026-04-02",
                "MGL9501,CUST9501,700,BK,2026-04-04",
                "MGL9501,CUST9501,500,FR,2026-04-03",
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
            ["MGL9601,CUST9601,1000,COMPLETED,BACK,2026-04-10"],
            ["MGL9601,CUST9601,1000,BK,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["course_tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_credit_date_is_not_eligible(self):
        """A credit date absent from the calendar must not be treated as open."""
        write_inputs(
            ["MGL9651,CUST9651,500,COMPLETED,BACK,2026-04-30"],
            ["MGL9651,CUST9651,500,BK,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["course_tier"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_credit_date_is_not_eligible(self):
        """A credit with an empty credit_date must not match any source row."""
        write_inputs(
            ["MGL9701,CUST9701,900,COMPLETED,FRONT,2026-04-05"],
            ["MGL9701,CUST9701,900,FRONT,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["course_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_record_without_play_date_is_not_eligible(self):
        """A source row with an empty play_date cannot be consumed."""
        write_inputs(
            ["MGL9801,CUST9801,700,COMPLETED,FULL,"],
            ["MGL9801,CUST9801,700,FL,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["course_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_fl_alias_matches_canonical_record_and_emits_canonical_course_tier(self):
        """A FL scorecard credit should match a FULL source row and report the canonical course_tier."""
        write_inputs(
            ["MGL9901,CUST9901,600,COMPLETED,FULL,2026-04-10"],
            ["MGL9901,CUST9901,600,FL,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["course_tier"] == "FULL"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }


    def test_mismatched_course_tier_does_not_match_even_with_valid_dates(self):
        """Date logic must not bypass the original course_tier equality requirement."""
        write_inputs(
            ["MGL9851,CUST9851,775,COMPLETED,FRONT,2026-04-10"],
            ["MGL9851,CUST9851,775,BACK,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["course_tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 775

    def test_alias_matches_canonical_record_with_dated_matching(self):
        """The FR alias should still normalize to FRONT when date gates are present."""
        write_inputs(
            ["MGL9951,CUST9951,650,COMPLETED,FRONT,2026-04-10"],
            ["MGL9951,CUST9951,650,FR,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["course_tier"] == "FRONT"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 650,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
