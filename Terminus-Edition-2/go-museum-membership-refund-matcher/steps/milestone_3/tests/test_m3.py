"""Milestone 3 verifier tests for dated membership refund reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
BILLS = APP / "data" / "memberships.csv"
REFUNDS = APP / "data" / "refunds.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "refund_report.csv"
SUMMARY = APP / "out" / "refund_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go refund reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 3 tests."""
    build_program()


def write_inputs(bill_rows, refund_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated refund scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    BILLS.write_text("membership_id,patron_id,amount_cents,status,program,valid_through\n" + "\n".join(bill_rows) + "\n")
    REFUNDS.write_text("membership_id,patron_id,amount_cents,program,refund_date\n" + "\n".join(refund_rows) + "\n")
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
    """Date gates and latest eligible membership selection for refunds."""

    def test_open_refund_date_and_latest_valid_through_win(self):
        """Open refund dates should gate matching and latest eligible due date should win."""
        write_inputs(
            [
                "BILL9301,CUST9301,1000,ACTIVE,ADULT,2026-04-03",
                "BILL9301,CUST9301,1000,ACTIVE,FAMILY,2026-04-04",
                "BILL9302,CUST9302,2000,ACTIVE,FAMILY,2026-04-02",
                "BILL9303,CUST9303,3000,ACTIVE,PATRON,2026-04-05",
                "BILL9304,CUST9304,4000,ACTIVE,PATRON,2026-04-05",
            ],
            [
                "BILL9301,CUST9301,1000,FAM,2026-04-02",
                "BILL9302,CUST9302,2000,FAM,2026-04-04",
                "BILL9303,CUST9303,3000,PTR,2026-04-06",
                "BILL9304,CUST9304,4000,PATRON,2026-04-07",
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
        assert rows[0]["program"] == "FAMILY"
        assert [row["program"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_valid_through_tie_uses_bill_order_and_consumption(self):
        """Same-date candidates should use membership order and still enforce consumption."""
        write_inputs(
            [
                "BILL9401,CUST9401,500,ACTIVE,FAMILY,2026-04-05",
                "BILL9401,CUST9401,500,ACTIVE,FAMILY,2026-04-05",
                "BILL9402,CUST9402,700,ACTIVE,ADULT,2026-04-05",
            ],
            [
                "BILL9401,CUST9401,500,FAM,2026-04-04",
                "BILL9401,CUST9401,500,FAM,2026-04-04",
                "BILL9401,CUST9401,500,FAM,2026-04-04",
                "BILL9402,CUST9402,700,ADULT,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["program"] for row in rows] == ["FAMILY", "FAMILY", "", "ADULT"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_valid_through_wins_before_older_bill_is_used(self):
        """A later eligible due date should be consumed before an older eligible membership."""
        write_inputs(
            [
                "BILL9501,CUST9501,800,ACTIVE,FAMILY,2026-04-03",
                "BILL9501,CUST9501,800,ACTIVE,FAMILY,2026-04-06",
            ],
            [
                "BILL9501,CUST9501,800,FAM,2026-04-02",
                "BILL9501,CUST9501,800,FAM,2026-04-04",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["program"] for row in rows] == ["FAMILY", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_closed_refund_date_is_not_eligible(self):
        """A refund whose date is listed as closed must not match."""
        write_inputs(
            ["BILL9601,CUST9601,1000,ACTIVE,FAMILY,2026-04-10"],
            ["BILL9601,CUST9601,1000,FAM,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["program"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_refund_date_is_not_eligible(self):
        """A refund date absent from the calendar must not be treated as open."""
        write_inputs(
            ["BILL9651,CUST9651,500,ACTIVE,FAMILY,2026-04-30"],
            ["BILL9651,CUST9651,500,FAM,2026-04-15"],
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

    def test_missing_refund_date_is_not_eligible(self):
        """A refund with an empty refund_date must not match any membership."""
        write_inputs(
            ["BILL9701,CUST9701,900,ACTIVE,ADULT,2026-04-05"],
            ["BILL9701,CUST9701,900,ADULT,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["program"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_bill_without_valid_through_is_not_eligible(self):
        """A membership with an empty valid_through cannot be consumed."""
        write_inputs(
            ["BILL9801,CUST9801,700,ACTIVE,PATRON,"],
            ["BILL9801,CUST9801,700,PTR,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["program"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_ptr_alias_matches_patron_bill_and_emits_canonical_program(self):
        """A PTR refund should match a PATRON membership and report the canonical program."""
        write_inputs(
            ["BILL9901,CUST9901,600,ACTIVE,PATRON,2026-04-10"],
            ["BILL9901,CUST9901,600,PTR,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["program"] == "PATRON"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
