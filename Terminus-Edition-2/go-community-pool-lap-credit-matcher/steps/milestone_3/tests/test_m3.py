"""Milestone 3 verifier tests for dated credit reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
SOURCE_FILE = APP / "data" / "laps.csv"
ACTION_FILE = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "lap_credit_report.csv"
SUMMARY = APP / "out" / "lap_credit_summary.json"
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
    SOURCE_FILE.write_text("lap_id,swimmer_id,amount_cents,status,lane_tier,lap_date\n" + "\n".join(bill_rows) + "\n")
    ACTION_FILE.write_text("lap_id,swimmer_id,amount_cents,lane_tier,credit_date\n" + "\n".join(credit_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_legacy_inputs(source_rows, action_rows):
    """Pre-date schema: milestone 3 must keep milestone 2 behavior without calendar gates."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_FILE.write_text(
        "lap_id,swimmer_id,amount_cents,status,lane_tier\n" + "\n".join(source_rows) + "\n"
    )
    ACTION_FILE.write_text(
        "lap_id,swimmer_id,amount_cents,lane_tier\n" + "\n".join(action_rows) + "\n"
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
            ["POL0001,CUST0001,100,COMPLETED,SLOW"],
            ["POL0001,CUST0001,100,SL"],
        )
        rows, _ = run_program()
        with REPORT.open(newline="") as handle:
            assert handle.readline().strip() == "lap_id,swimmer_id,lane_tier,amount_cents,status"
        assert {row["status"] for row in rows} <= {"MATCHED", "UNMATCHED"}


    def test_legacy_schema_without_dates_keeps_prior_alias_and_consumption(self):
        """Pre-date inputs should keep milestone 2 matching without requiring calendar dates."""
        write_legacy_inputs(
            [
                "POL9001,CUST9001,1200,COMPLETED,FAST",
                "POL9001,CUST9001,1200,COMPLETED,FAST",
                "POL9002,CUST9002,700,COMPLETED,SLOW",
            ],
            [
                "POL9001,CUST9001,1200,FS",
                "POL9001,CUST9001,1200,FS",
                "POL9002,CUST9002,700,SL",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["lane_tier"] for row in rows] == ["FAST", "FAST", "SLOW"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 3100,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }


    def test_open_credit_date_and_latest_lap_date_win(self):
        """Open credit_date gates matching; matched row uses canonical lane_tier from latest lap_date."""
        write_inputs(
            [
                "POL9301,CUST9301,1000,COMPLETED,SLOW,2026-04-03",
                "POL9301,CUST9301,1000,COMPLETED,MED,2026-04-04",
                "POL9302,CUST9302,2000,COMPLETED,MED,2026-04-02",
                "POL9303,CUST9303,3000,COMPLETED,FAST,2026-04-05",
                "POL9304,CUST9304,4000,COMPLETED,FAST,2026-04-05",
            ],
            [
                "POL9301,CUST9301,1000,MD,2026-04-02",
                "POL9302,CUST9302,2000,MD,2026-04-04",
                "POL9303,CUST9303,3000,FS,2026-04-06",
                "POL9304,CUST9304,4000,FAST,2026-04-07",
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
        assert rows[0]["lane_tier"] == "MED"
        assert [row["lane_tier"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_lap_date_tie_uses_record_order_and_consumption(self):
        """Same-date candidates should use source row order and still enforce consumption."""
        write_inputs(
            [
                "POL9401,CUST9401,500,COMPLETED,MED,2026-04-05",
                "POL9401,CUST9401,500,COMPLETED,MED,2026-04-05",
                "POL9402,CUST9402,700,COMPLETED,SLOW,2026-04-05",
            ],
            [
                "POL9401,CUST9401,500,MD,2026-04-04",
                "POL9401,CUST9401,500,MD,2026-04-04",
                "POL9401,CUST9401,500,MD,2026-04-04",
                "POL9402,CUST9402,700,SLOW,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["lane_tier"] for row in rows] == ["MED", "MED", "", "SLOW"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_lap_date_wins_before_older_record_is_used(self):
        """Latest lap_date must win when the later input row carries the later date."""
        write_inputs(
            [
                "POL9501,CUST9501,500,COMPLETED,SLOW,2026-04-03",
                "POL9501,CUST9501,800,COMPLETED,MED,2026-04-06",
                "POL9501,CUST9501,700,COMPLETED,MED,2026-04-05",
            ],
            [
                "POL9501,CUST9501,800,MD,2026-04-02",
                "POL9501,CUST9501,700,MD,2026-04-04",
                "POL9501,CUST9501,500,SL,2026-04-03",
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
            ["POL9601,CUST9601,1000,COMPLETED,MED,2026-04-10"],
            ["POL9601,CUST9601,1000,MD,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["lane_tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_credit_date_is_not_eligible(self):
        """A credit date absent from the calendar must not be treated as open."""
        write_inputs(
            ["POL9651,CUST9651,500,COMPLETED,MED,2026-04-30"],
            ["POL9651,CUST9651,500,MD,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["lane_tier"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_credit_date_is_not_eligible(self):
        """A credit with an empty credit_date must not match any source row."""
        write_inputs(
            ["POL9701,CUST9701,900,COMPLETED,SLOW,2026-04-05"],
            ["POL9701,CUST9701,900,SLOW,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["lane_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_record_without_lap_date_is_not_eligible(self):
        """A source row with an empty lap_date cannot be consumed."""
        write_inputs(
            ["POL9801,CUST9801,700,COMPLETED,FAST,"],
            ["POL9801,CUST9801,700,FS,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["lane_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_fs_alias_matches_canonical_record_and_emits_canonical_lane_tier(self):
        """A FS lap credit should match a FAST source row and report the canonical lane_tier."""
        write_inputs(
            ["POL9901,CUST9901,600,COMPLETED,FAST,2026-04-10"],
            ["POL9901,CUST9901,600,FS,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["lane_tier"] == "FAST"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }


    def test_mismatched_lane_tier_does_not_match_even_with_valid_dates(self):
        """Date logic must not bypass the original lane_tier equality requirement."""
        write_inputs(
            ["POL9851,CUST9851,775,COMPLETED,SLOW,2026-04-10"],
            ["POL9851,CUST9851,775,MED,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["lane_tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 775

    def test_alias_matches_canonical_record_with_dated_matching(self):
        """The SL alias should still normalize to SLOW when date gates are present."""
        write_inputs(
            ["POL9951,CUST9951,650,COMPLETED,SLOW,2026-04-10"],
            ["POL9951,CUST9951,650,SL,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["lane_tier"] == "SLOW"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 650,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
