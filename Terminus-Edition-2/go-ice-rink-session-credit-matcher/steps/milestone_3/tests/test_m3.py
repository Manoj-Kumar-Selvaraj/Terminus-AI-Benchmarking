"""Milestone 3 verifier tests for dated credit reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
SOURCE_FILE = APP / "data" / "sessions.csv"
ACTION_FILE = APP / "data" / "session_credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "rink_credit_report.csv"
SUMMARY = APP / "out" / "rink_credit_summary.json"
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
    SOURCE_FILE.write_text("session_id,skater_id,amount_cents,status,rink_pass,session_date\n" + "\n".join(bill_rows) + "\n")
    ACTION_FILE.write_text("session_id,skater_id,amount_cents,rink_pass,credit_date\n" + "\n".join(credit_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_legacy_inputs(source_rows, action_rows):
    """Pre-date schema: milestone 3 must keep milestone 2 behavior without calendar gates."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_FILE.write_text(
        "session_id,skater_id,amount_cents,status,rink_pass\n" + "\n".join(source_rows) + "\n"
    )
    ACTION_FILE.write_text(
        "session_id,skater_id,amount_cents,rink_pass\n" + "\n".join(action_rows) + "\n"
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
            ["ICE0001,CUST0001,100,COMPLETED,PRAC"],
            ["ICE0001,CUST0001,100,PR"],
        )
        rows, _ = run_program()
        with REPORT.open(newline="") as handle:
            assert handle.readline().strip() == "session_id,skater_id,rink_pass,amount_cents,status"
        assert {row["status"] for row in rows} <= {"MATCHED", "UNMATCHED"}


    def test_legacy_schema_without_dates_keeps_prior_alias_and_consumption(self):
        """Pre-date inputs should keep milestone 2 matching without requiring calendar dates."""
        write_legacy_inputs(
            [
                "ICE9001,CUST9001,1200,COMPLETED,LEAG",
                "ICE9001,CUST9001,1200,COMPLETED,LEAG",
                "ICE9002,CUST9002,700,COMPLETED,PRAC",
            ],
            [
                "ICE9001,CUST9001,1200,LG",
                "ICE9001,CUST9001,1200,LG",
                "ICE9002,CUST9002,700,PR",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["rink_pass"] for row in rows] == ["LEAG", "LEAG", "PRAC"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 3100,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }


    def test_open_credit_date_and_latest_session_date_win(self):
        """Open credit_date gates matching; matched row uses canonical rink_pass from latest session_date."""
        write_inputs(
            [
                "ICE9301,CUST9301,1000,COMPLETED,PRAC,2026-04-03",
                "ICE9301,CUST9301,1000,COMPLETED,GAME,2026-04-04",
                "ICE9302,CUST9302,2000,COMPLETED,GAME,2026-04-02",
                "ICE9303,CUST9303,3000,COMPLETED,LEAG,2026-04-05",
                "ICE9304,CUST9304,4000,COMPLETED,LEAG,2026-04-05",
            ],
            [
                "ICE9301,CUST9301,1000,GM,2026-04-02",
                "ICE9302,CUST9302,2000,GM,2026-04-04",
                "ICE9303,CUST9303,3000,LG,2026-04-06",
                "ICE9304,CUST9304,4000,LEAG,2026-04-07",
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
        assert rows[0]["rink_pass"] == "GAME"
        assert [row["rink_pass"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_session_date_tie_uses_record_order_and_consumption(self):
        """Same-date candidates should use source row order and still enforce consumption."""
        write_inputs(
            [
                "ICE9401,CUST9401,500,COMPLETED,GAME,2026-04-05",
                "ICE9401,CUST9401,500,COMPLETED,GAME,2026-04-05",
                "ICE9402,CUST9402,700,COMPLETED,PRAC,2026-04-05",
            ],
            [
                "ICE9401,CUST9401,500,GM,2026-04-04",
                "ICE9401,CUST9401,500,GM,2026-04-04",
                "ICE9401,CUST9401,500,GM,2026-04-04",
                "ICE9402,CUST9402,700,PRAC,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["rink_pass"] for row in rows] == ["GAME", "GAME", "", "PRAC"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_session_date_wins_before_older_record_is_used(self):
        """Latest session_date must win when the later input row carries the later date."""
        write_inputs(
            [
                "ICE9501,CUST9501,500,COMPLETED,PRAC,2026-04-03",
                "ICE9501,CUST9501,800,COMPLETED,GAME,2026-04-06",
                "ICE9501,CUST9501,700,COMPLETED,GAME,2026-04-05",
            ],
            [
                "ICE9501,CUST9501,800,GM,2026-04-02",
                "ICE9501,CUST9501,700,GM,2026-04-04",
                "ICE9501,CUST9501,500,PR,2026-04-03",
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
            ["ICE9601,CUST9601,1000,COMPLETED,GAME,2026-04-10"],
            ["ICE9601,CUST9601,1000,GM,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["rink_pass"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_credit_date_is_not_eligible(self):
        """A credit date absent from the calendar must not be treated as open."""
        write_inputs(
            ["ICE9651,CUST9651,500,COMPLETED,GAME,2026-04-30"],
            ["ICE9651,CUST9651,500,GM,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["rink_pass"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_credit_date_is_not_eligible(self):
        """A credit with an empty credit_date must not match any source row."""
        write_inputs(
            ["ICE9701,CUST9701,900,COMPLETED,PRAC,2026-04-05"],
            ["ICE9701,CUST9701,900,PRAC,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["rink_pass"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_record_without_session_date_is_not_eligible(self):
        """A source row with an empty session_date cannot be consumed."""
        write_inputs(
            ["ICE9801,CUST9801,700,COMPLETED,LEAG,"],
            ["ICE9801,CUST9801,700,LG,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["rink_pass"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_lg_alias_matches_canonical_record_and_emits_canonical_rink_pass(self):
        """A LG session credit should match a LEAG source row and report the canonical rink_pass."""
        write_inputs(
            ["ICE9901,CUST9901,600,COMPLETED,LEAG,2026-04-10"],
            ["ICE9901,CUST9901,600,LG,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["rink_pass"] == "LEAG"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }


    def test_mismatched_rink_pass_does_not_match_even_with_valid_dates(self):
        """Date logic must not bypass the original rink_pass equality requirement."""
        write_inputs(
            ["ICE9851,CUST9851,775,COMPLETED,PRAC,2026-04-10"],
            ["ICE9851,CUST9851,775,GAME,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["rink_pass"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 775

    def test_alias_matches_canonical_record_with_dated_matching(self):
        """The PR alias should still normalize to PRAC when date gates are present."""
        write_inputs(
            ["ICE9951,CUST9951,650,COMPLETED,PRAC,2026-04-10"],
            ["ICE9951,CUST9951,650,PR,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["rink_pass"] == "PRAC"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 650,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
