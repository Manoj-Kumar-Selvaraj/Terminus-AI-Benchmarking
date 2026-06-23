"""Milestone 3 verifier tests for dated credit reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
SOURCE_FILE = APP / "data" / "prints.csv"
ACTION_FILE = APP / "data" / "print_credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "print_credit_report.csv"
SUMMARY = APP / "out" / "print_credit_summary.json"
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
    SOURCE_FILE.write_text("print_id,guest_id,amount_cents,status,pack_tier,print_date\n" + "\n".join(bill_rows) + "\n")
    ACTION_FILE.write_text("print_id,guest_id,amount_cents,pack_tier,credit_date\n" + "\n".join(credit_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_legacy_inputs(source_rows, action_rows):
    """Pre-date schema: milestone 3 must keep milestone 2 behavior without calendar gates."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_FILE.write_text(
        "print_id,guest_id,amount_cents,status,pack_tier\n" + "\n".join(source_rows) + "\n"
    )
    ACTION_FILE.write_text(
        "print_id,guest_id,amount_cents,pack_tier\n" + "\n".join(action_rows) + "\n"
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
            ["PHT0001,CUST0001,100,COMPLETED,MINI"],
            ["PHT0001,CUST0001,100,MI"],
        )
        rows, _ = run_program()
        with REPORT.open(newline="") as handle:
            assert handle.readline().strip() == "print_id,guest_id,pack_tier,amount_cents,status"
        assert {row["status"] for row in rows} <= {"MATCHED", "UNMATCHED"}


    def test_legacy_schema_without_dates_keeps_prior_alias_and_consumption(self):
        """Pre-date inputs should keep milestone 2 matching without requiring calendar dates."""
        write_legacy_inputs(
            [
                "PHT9001,CUST9001,1200,COMPLETED,MAX",
                "PHT9001,CUST9001,1200,COMPLETED,MAX",
                "PHT9002,CUST9002,700,COMPLETED,MINI",
            ],
            [
                "PHT9001,CUST9001,1200,MX",
                "PHT9001,CUST9001,1200,MX",
                "PHT9002,CUST9002,700,MI",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["pack_tier"] for row in rows] == ["MAX", "MAX", "MINI"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 3100,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }


    def test_open_credit_date_and_latest_print_date_win(self):
        """Open credit_date gates matching; matched row uses canonical pack_tier from latest print_date."""
        write_inputs(
            [
                "PHT9301,CUST9301,1000,COMPLETED,MINI,2026-04-03",
                "PHT9301,CUST9301,1000,COMPLETED,STANDARD,2026-04-04",
                "PHT9302,CUST9302,2000,COMPLETED,STANDARD,2026-04-02",
                "PHT9303,CUST9303,3000,COMPLETED,MAX,2026-04-05",
                "PHT9304,CUST9304,4000,COMPLETED,MAX,2026-04-05",
            ],
            [
                "PHT9301,CUST9301,1000,SD,2026-04-02",
                "PHT9302,CUST9302,2000,SD,2026-04-04",
                "PHT9303,CUST9303,3000,MX,2026-04-06",
                "PHT9304,CUST9304,4000,MAX,2026-04-07",
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
        assert rows[0]["pack_tier"] == "STANDARD"
        assert [row["pack_tier"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_print_date_tie_uses_record_order_and_consumption(self):
        """Same-date candidates should use source row order and still enforce consumption."""
        write_inputs(
            [
                "PHT9401,CUST9401,500,COMPLETED,STANDARD,2026-04-05",
                "PHT9401,CUST9401,500,COMPLETED,STANDARD,2026-04-05",
                "PHT9402,CUST9402,700,COMPLETED,MINI,2026-04-05",
            ],
            [
                "PHT9401,CUST9401,500,SD,2026-04-04",
                "PHT9401,CUST9401,500,SD,2026-04-04",
                "PHT9401,CUST9401,500,SD,2026-04-04",
                "PHT9402,CUST9402,700,MINI,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["pack_tier"] for row in rows] == ["STANDARD", "STANDARD", "", "MINI"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_print_date_wins_before_older_record_is_used(self):
        """Latest print_date must win when the later input row carries the later date."""
        write_inputs(
            [
                "PHT9501,CUST9501,500,COMPLETED,MINI,2026-04-03",
                "PHT9501,CUST9501,800,COMPLETED,STANDARD,2026-04-06",
                "PHT9501,CUST9501,700,COMPLETED,STANDARD,2026-04-05",
            ],
            [
                "PHT9501,CUST9501,800,SD,2026-04-02",
                "PHT9501,CUST9501,700,SD,2026-04-04",
                "PHT9501,CUST9501,500,MI,2026-04-03",
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
            ["PHT9601,CUST9601,1000,COMPLETED,STANDARD,2026-04-10"],
            ["PHT9601,CUST9601,1000,SD,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["pack_tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_credit_date_is_not_eligible(self):
        """A credit date absent from the calendar must not be treated as open."""
        write_inputs(
            ["PHT9651,CUST9651,500,COMPLETED,STANDARD,2026-04-30"],
            ["PHT9651,CUST9651,500,SD,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["pack_tier"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_credit_date_is_not_eligible(self):
        """A credit with an empty credit_date must not match any source row."""
        write_inputs(
            ["PHT9701,CUST9701,900,COMPLETED,MINI,2026-04-05"],
            ["PHT9701,CUST9701,900,MINI,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["pack_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_record_without_print_date_is_not_eligible(self):
        """A source row with an empty print_date cannot be consumed."""
        write_inputs(
            ["PHT9801,CUST9801,700,COMPLETED,MAX,"],
            ["PHT9801,CUST9801,700,MX,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["pack_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_mx_alias_matches_canonical_record_and_emits_canonical_pack_tier(self):
        """A MX action row should match a MAX source row and report the canonical pack_tier."""
        write_inputs(
            ["PHT9901,CUST9901,600,COMPLETED,MAX,2026-04-10"],
            ["PHT9901,CUST9901,600,MX,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["pack_tier"] == "MAX"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }


    def test_mismatched_pack_tier_does_not_match_even_with_valid_dates(self):
        """Date logic must not bypass the original pack_tier equality requirement."""
        write_inputs(
            ["PHT9851,CUST9851,775,COMPLETED,MINI,2026-04-10"],
            ["PHT9851,CUST9851,775,STANDARD,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["pack_tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 775

    def test_alias_matches_canonical_record_with_dated_matching(self):
        """The MI alias should still normalize to MINI when date gates are present."""
        write_inputs(
            ["PHT9951,CUST9951,650,COMPLETED,MINI,2026-04-10"],
            ["PHT9951,CUST9951,650,MI,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["pack_tier"] == "MINI"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 650,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
