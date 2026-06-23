"""Milestone 3 verifier tests for dated pass credit reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
BILLS = APP / "data" / "passes.csv"
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


def write_inputs(bill_rows, refund_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated credit scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    BILLS.write_text("pass_id,guest_id,amount_cents,status,program,valid_until\n" + "\n".join(bill_rows) + "\n")
    REFUNDS.write_text("pass_id,guest_id,amount_cents,program,credit_date\n" + "\n".join(refund_rows) + "\n")
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
    """Date gates and latest eligible pass selection for refunds."""

    def test_open_credit_date_and_latest_valid_until_win(self):
        """Open credit dates should gate matching and latest eligible due date should win."""
        write_inputs(
            [
                "BILL9301,CUST9301,1000,ACTIVE,GENERAL,2026-04-03",
                "BILL9301,CUST9301,1000,ACTIVE,TOUR,2026-04-04",
                "BILL9302,CUST9302,2000,ACTIVE,TOUR,2026-04-02",
                "BILL9303,CUST9303,3000,ACTIVE,MEMBER,2026-04-05",
                "BILL9304,CUST9304,4000,ACTIVE,MEMBER,2026-04-05",
            ],
            [
                "BILL9301,CUST9301,1000,TR,2026-04-02",
                "BILL9302,CUST9302,2000,TR,2026-04-04",
                "BILL9303,CUST9303,3000,MEM,2026-04-06",
                "BILL9304,CUST9304,4000,MEMBER,2026-04-07",
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
        assert rows[0]["program"] == "TOUR"
        assert [row["program"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_valid_until_tie_uses_bill_order_and_consumption(self):
        """Same-date candidates should use pass order and still enforce consumption."""
        write_inputs(
            [
                "BILL9401,CUST9401,500,ACTIVE,TOUR,2026-04-05",
                "BILL9401,CUST9401,500,ACTIVE,TOUR,2026-04-05",
                "BILL9402,CUST9402,700,ACTIVE,GENERAL,2026-04-05",
            ],
            [
                "BILL9401,CUST9401,500,TR,2026-04-04",
                "BILL9401,CUST9401,500,TR,2026-04-04",
                "BILL9401,CUST9401,500,TR,2026-04-04",
                "BILL9402,CUST9402,700,GENERAL,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["program"] for row in rows] == ["TOUR", "TOUR", "", "GENERAL"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_valid_until_wins_before_older_bill_is_used(self):
        """A later eligible due date should be consumed before an older eligible pass."""
        write_inputs(
            [
                "BILL9501,CUST9501,800,ACTIVE,TOUR,2026-04-03",
                "BILL9501,CUST9501,800,ACTIVE,TOUR,2026-04-06",
            ],
            [
                "BILL9501,CUST9501,800,TR,2026-04-02",
                "BILL9501,CUST9501,800,TR,2026-04-04",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["program"] for row in rows] == ["TOUR", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_closed_credit_date_is_not_eligible(self):
        """A credit whose date is listed as closed must not match."""
        write_inputs(
            ["BILL9601,CUST9601,1000,ACTIVE,TOUR,2026-04-10"],
            ["BILL9601,CUST9601,1000,TR,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["program"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_credit_date_is_not_eligible(self):
        """A credit date absent from the calendar must not be treated as open."""
        write_inputs(
            ["BILL9651,CUST9651,500,ACTIVE,TOUR,2026-04-30"],
            ["BILL9651,CUST9651,500,TR,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["program"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_credit_date_is_not_eligible(self):
        """A credit with an empty credit_date must not match any pass."""
        write_inputs(
            ["BILL9701,CUST9701,900,ACTIVE,GENERAL,2026-04-05"],
            ["BILL9701,CUST9701,900,GENERAL,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["program"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_bill_without_valid_until_is_not_eligible(self):
        """A pass with an empty valid_until cannot be consumed."""
        write_inputs(
            ["BILL9801,CUST9801,700,ACTIVE,MEMBER,"],
            ["BILL9801,CUST9801,700,MEM,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["program"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_credit_date_after_valid_until_stays_unmatched(self):
        """credit_date later than valid_until must stay unmatched even when the calendar is open."""
        write_inputs(
            ["BILL9711,CUST9711,600,ACTIVE,TOUR,2026-04-03"],
            ["BILL9711,CUST9711,600,TR,2026-04-05"],
            ["2026-04-03 open", "2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["program"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 600,
        }

    def test_mem_alias_matches_member_bill_and_emits_canonical_program(self):
        """A MEM credit should match a MEMBER pass and report the canonical program."""
        write_inputs(
            ["BILL9901,CUST9901,600,ACTIVE,MEMBER,2026-04-10"],
            ["BILL9901,CUST9901,600,MEM,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["program"] == "MEMBER"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_gen_alias_matches_general_with_dates_and_emits_canonical_program(self):
        """The GEN alias should still normalize to GENERAL under dated matching."""
        write_inputs(
            ["ALIAS3001,CUSTALIAS3,4321,ACTIVE,GENERAL,2026-04-10"],
            ["ALIAS3001,CUSTALIAS3,4321,GEN,2026-04-05"],
            ["2026-04-05 open", "2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["program"] == "GENERAL"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 4321,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_both_blank_dates_still_clear_like_undated_records(self):
        """When date columns exist but both sides are blank, matching should follow the undated path."""
        write_inputs(
            ["BILLBB1,CUSTBB1,900,ACTIVE,GENERAL,", "BILLBB1,CUSTBB1,900,ACTIVE,TOUR,2026-04-10"],
            ["BILLBB1,CUSTBB1,900,GENERAL,", "BILLBB1,CUSTBB1,900,TR,2026-04-05"],
            ["2026-04-05 open", "2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["program"] == "GENERAL"
        assert rows[1]["status"] == "MATCHED"
        assert rows[1]["program"] == "TOUR"
        assert summary["matched_count"] == 2

    def test_mismatched_program_does_not_match_even_with_valid_dates(self):
        """Date logic must not bypass the program equality requirement."""
        write_inputs(
            ["BILL9851,CUST9851,775,ACTIVE,GENERAL,2026-04-10"],
            ["BILL9851,CUST9851,775,TOUR,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["program"] == ""
        assert summary["unmatched_count"] == 1


class TestMilestone3Regression:
    """Key milestone 1-2 behaviours preserved under dated matching."""

    def test_full_pass_id_required(self):
        """Prefix-only pass ids must not match."""
        write_inputs(
            [
                "INV777770001,CUST2001,3300,ACTIVE,GENERAL,2026-04-05",
                "INV777770002,CUST2001,3300,ACTIVE,GENERAL,2026-04-05",
            ],
            [
                "INV777770003,CUST2001,3300,GENERAL,2026-04-04",
                "INV777770002,CUST2001,3300,GENERAL,2026-04-04",
            ],
            ["2026-04-04 open", "2026-04-05 open"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert summary["matched_count"] == 1

    def test_gen_alias_still_normalizes(self):
        """GEN alias should still map to GENERAL with dates present."""
        write_inputs(
            ["ALIAS-REG1,CUSTREG1,2100,ACTIVE,GENERAL,2026-04-10"],
            ["ALIAS-REG1,CUSTREG1,2100,GEN,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["program"] == "GENERAL"

