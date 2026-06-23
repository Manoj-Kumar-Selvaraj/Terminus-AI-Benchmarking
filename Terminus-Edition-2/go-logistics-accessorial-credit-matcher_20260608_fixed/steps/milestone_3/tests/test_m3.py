"""Milestone 3 verifier tests for dated charge credit reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
BILLS = APP / "data" / "charges.csv"
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
    BILLS.write_text("charge_id,shipper_id,amount_cents,status,mode,invoice_date\n" + "\n".join(bill_rows) + "\n")
    REFUNDS.write_text("charge_id,shipper_id,amount_cents,mode,credit_date\n" + "\n".join(refund_rows) + "\n")
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
    """Date gates and latest eligible charge selection for refunds."""

    def test_open_credit_date_and_latest_invoice_date_win(self):
        """Open credit dates should gate matching and latest eligible due date should win."""
        write_inputs(
            [
                "BILL9301,CUST9301,1000,BILLED,LTL,2026-04-03",
                "BILL9301,CUST9301,1000,BILLED,FTL,2026-04-04",
                "BILL9302,CUST9302,2000,BILLED,FTL,2026-04-02",
                "BILL9303,CUST9303,3000,BILLED,RAIL,2026-04-05",
                "BILL9304,CUST9304,4000,BILLED,RAIL,2026-04-05",
            ],
            [
                "BILL9301,CUST9301,1000,FULL,2026-04-02",
                "BILL9302,CUST9302,2000,FULL,2026-04-04",
                "BILL9303,CUST9303,3000,RR,2026-04-06",
                "BILL9304,CUST9304,4000,RAIL,2026-04-07",
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
        assert rows[0]["mode"] == "FTL"
        assert [row["mode"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_invoice_date_tie_uses_bill_order_and_consumption(self):
        """Same-date candidates should use charge order and still enforce consumption."""
        write_inputs(
            [
                "BILL9401,CUST9401,500,BILLED,FTL,2026-04-05",
                "BILL9401,CUST9401,500,BILLED,FTL,2026-04-05",
                "BILL9402,CUST9402,700,BILLED,LTL,2026-04-05",
            ],
            [
                "BILL9401,CUST9401,500,FULL,2026-04-04",
                "BILL9401,CUST9401,500,FULL,2026-04-04",
                "BILL9401,CUST9401,500,FULL,2026-04-04",
                "BILL9402,CUST9402,700,LTL,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["mode"] for row in rows] == ["FTL", "FTL", "", "LTL"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_invoice_date_wins_before_older_bill_is_used(self):
        """A later eligible due date should be consumed before an older eligible charge."""
        write_inputs(
            [
                "BILL9501,CUST9501,800,BILLED,FTL,2026-04-03",
                "BILL9501,CUST9501,800,BILLED,FTL,2026-04-06",
            ],
            [
                "BILL9501,CUST9501,800,FULL,2026-04-02",
                "BILL9501,CUST9501,800,FULL,2026-04-04",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["mode"] for row in rows] == ["FTL", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_closed_credit_date_is_not_eligible(self):
        """A credit whose date is listed as closed must not match."""
        write_inputs(
            ["BILL9601,CUST9601,1000,BILLED,FTL,2026-04-10"],
            ["BILL9601,CUST9601,1000,FULL,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["mode"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_credit_date_is_not_eligible(self):
        """A credit date absent from the calendar must not be treated as open."""
        write_inputs(
            ["BILL9651,CUST9651,500,BILLED,FTL,2026-04-30"],
            ["BILL9651,CUST9651,500,FULL,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["mode"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_credit_date_is_not_eligible(self):
        """A credit with an empty credit_date must not match any charge."""
        write_inputs(
            ["BILL9701,CUST9701,900,BILLED,LTL,2026-04-05"],
            ["BILL9701,CUST9701,900,LTL,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["mode"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_bill_without_invoice_date_is_not_eligible(self):
        """A charge with an empty invoice_date cannot be consumed."""
        write_inputs(
            ["BILL9801,CUST9801,700,BILLED,RAIL,"],
            ["BILL9801,CUST9801,700,RR,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["mode"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_rr_alias_matches_rail_bill_and_emits_canonical_mode(self):
        """A RR credit should match a RAIL charge and report the canonical mode."""
        write_inputs(
            ["BILL9901,CUST9901,600,BILLED,RAIL,2026-04-10"],
            ["BILL9901,CUST9901,600,RR,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["mode"] == "RAIL"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_less_alias_matches_ltl_bill_and_emits_canonical_mode(self):
        """A LESS credit should match an LTL charge and report the canonical mode."""
        write_inputs(
            ["BILL9950,CUST9950,450,BILLED,LTL,2026-04-10"],
            ["BILL9950,CUST9950,450,LESS,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["mode"] == "LTL"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 450,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
