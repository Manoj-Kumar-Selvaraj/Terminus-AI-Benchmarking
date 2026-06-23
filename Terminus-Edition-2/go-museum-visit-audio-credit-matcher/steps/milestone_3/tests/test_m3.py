"""Milestone 3 verifier tests for dated credit reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
SOURCE_FILE = APP / "data" / "visits.csv"
ACTION_FILE = APP / "data" / "audio_credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "museum_credit_report.csv"
SUMMARY = APP / "out" / "museum_credit_summary.json"
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
    SOURCE_FILE.write_text("visit_id,patron_id,amount_cents,status,gallery_tier,visit_date\n" + "\n".join(bill_rows) + "\n")
    ACTION_FILE.write_text("visit_id,patron_id,amount_cents,gallery_tier,credit_date\n" + "\n".join(credit_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_legacy_inputs(source_rows, action_rows):
    """Pre-date schema: milestone 3 must keep milestone 2 behavior without calendar gates."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_FILE.write_text(
        "visit_id,patron_id,amount_cents,status,gallery_tier\n" + "\n".join(source_rows) + "\n"
    )
    ACTION_FILE.write_text(
        "visit_id,patron_id,amount_cents,gallery_tier\n" + "\n".join(action_rows) + "\n"
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
            ["MUS0001,CUST0001,100,COMPLETED,GENERAL"],
            ["MUS0001,CUST0001,100,GN"],
        )
        rows, _ = run_program()
        with REPORT.open(newline="") as handle:
            assert handle.readline().strip() == "visit_id,patron_id,gallery_tier,amount_cents,status"
        assert {row["status"] for row in rows} <= {"MATCHED", "UNMATCHED"}


    def test_legacy_schema_without_dates_keeps_prior_alias_and_consumption(self):
        """Pre-date inputs should keep milestone 2 matching without requiring calendar dates."""
        write_legacy_inputs(
            [
                "MUS9001,CUST9001,1200,COMPLETED,MEMBER",
                "MUS9001,CUST9001,1200,COMPLETED,MEMBER",
                "MUS9002,CUST9002,700,COMPLETED,GENERAL",
            ],
            [
                "MUS9001,CUST9001,1200,MB",
                "MUS9001,CUST9001,1200,MB",
                "MUS9002,CUST9002,700,GN",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["gallery_tier"] for row in rows] == ["MEMBER", "MEMBER", "GENERAL"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 3100,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }


    def test_open_credit_date_and_latest_visit_date_win(self):
        """Open credit_date gates matching; matched row uses canonical gallery_tier from latest visit_date."""
        write_inputs(
            [
                "MUS9301,CUST9301,1000,COMPLETED,GENERAL,2026-04-03",
                "MUS9301,CUST9301,1000,COMPLETED,SPECIAL,2026-04-04",
                "MUS9302,CUST9302,2000,COMPLETED,SPECIAL,2026-04-02",
                "MUS9303,CUST9303,3000,COMPLETED,MEMBER,2026-04-05",
                "MUS9304,CUST9304,4000,COMPLETED,MEMBER,2026-04-05",
            ],
            [
                "MUS9301,CUST9301,1000,SP,2026-04-02",
                "MUS9302,CUST9302,2000,SP,2026-04-04",
                "MUS9303,CUST9303,3000,MB,2026-04-06",
                "MUS9304,CUST9304,4000,MEMBER,2026-04-07",
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
        assert rows[0]["gallery_tier"] == "SPECIAL"
        assert [row["gallery_tier"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_visit_date_tie_uses_record_order_and_consumption(self):
        """Same-date candidates should use source row order and still enforce consumption."""
        write_inputs(
            [
                "MUS9401,CUST9401,500,COMPLETED,SPECIAL,2026-04-05",
                "MUS9401,CUST9401,500,COMPLETED,SPECIAL,2026-04-05",
                "MUS9402,CUST9402,700,COMPLETED,GENERAL,2026-04-05",
            ],
            [
                "MUS9401,CUST9401,500,SP,2026-04-04",
                "MUS9401,CUST9401,500,SP,2026-04-04",
                "MUS9401,CUST9401,500,SP,2026-04-04",
                "MUS9402,CUST9402,700,GENERAL,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["gallery_tier"] for row in rows] == ["SPECIAL", "SPECIAL", "", "GENERAL"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_visit_date_wins_before_older_record_is_used(self):
        """Latest visit_date must win when the later input row carries the later date."""
        write_inputs(
            [
                "MUS9501,CUST9501,500,COMPLETED,GENERAL,2026-04-03",
                "MUS9501,CUST9501,800,COMPLETED,SPECIAL,2026-04-06",
                "MUS9501,CUST9501,700,COMPLETED,SPECIAL,2026-04-05",
            ],
            [
                "MUS9501,CUST9501,800,SP,2026-04-02",
                "MUS9501,CUST9501,700,SP,2026-04-04",
                "MUS9501,CUST9501,500,GN,2026-04-03",
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
            ["MUS9601,CUST9601,1000,COMPLETED,SPECIAL,2026-04-10"],
            ["MUS9601,CUST9601,1000,SP,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["gallery_tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_credit_date_is_not_eligible(self):
        """A credit date absent from the calendar must not be treated as open."""
        write_inputs(
            ["MUS9651,CUST9651,500,COMPLETED,SPECIAL,2026-04-30"],
            ["MUS9651,CUST9651,500,SP,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["gallery_tier"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_credit_date_is_not_eligible(self):
        """A credit with an empty credit_date must not match any source row."""
        write_inputs(
            ["MUS9701,CUST9701,900,COMPLETED,GENERAL,2026-04-05"],
            ["MUS9701,CUST9701,900,GENERAL,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["gallery_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_record_without_visit_date_is_not_eligible(self):
        """A source row with an empty visit_date cannot be consumed."""
        write_inputs(
            ["MUS9801,CUST9801,700,COMPLETED,MEMBER,"],
            ["MUS9801,CUST9801,700,MB,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["gallery_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_mb_alias_matches_canonical_record_and_emits_canonical_gallery_tier(self):
        """A MB audio credit should match a MEMBER source row and report the canonical gallery_tier."""
        write_inputs(
            ["MUS9901,CUST9901,600,COMPLETED,MEMBER,2026-04-10"],
            ["MUS9901,CUST9901,600,MB,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["gallery_tier"] == "MEMBER"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }


    def test_mismatched_gallery_tier_does_not_match_even_with_valid_dates(self):
        """Date logic must not bypass the original gallery_tier equality requirement."""
        write_inputs(
            ["MUS9851,CUST9851,775,COMPLETED,GENERAL,2026-04-10"],
            ["MUS9851,CUST9851,775,SPECIAL,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["gallery_tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 775

    def test_alias_matches_canonical_record_with_dated_matching(self):
        """The GN alias should still normalize to GENERAL when date gates are present."""
        write_inputs(
            ["MUS9951,CUST9951,650,COMPLETED,GENERAL,2026-04-10"],
            ["MUS9951,CUST9951,650,GN,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["gallery_tier"] == "GENERAL"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 650,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
