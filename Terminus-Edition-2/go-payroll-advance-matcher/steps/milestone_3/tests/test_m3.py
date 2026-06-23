"""Milestone 3 verifier tests for dated advance repayment reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
BILLS = APP / "data" / "advances.csv"
REFUNDS = APP / "data" / "repayments.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "repayment_report.csv"
SUMMARY = APP / "out" / "repayment_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go repayment reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 3 tests."""
    build_program()


def write_inputs(bill_rows, refund_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated repayment scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    BILLS.write_text("advance_id,employee_id,amount_cents,status,method,advance_date\n" + "\n".join(bill_rows) + "\n")
    REFUNDS.write_text("advance_id,employee_id,amount_cents,method,repayment_date\n" + "\n".join(refund_rows) + "\n")
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
    """Date gates and latest eligible advance selection for refunds."""

    def test_open_repayment_date_and_latest_advance_date_win(self):
        """Open repayment dates should gate matching and latest eligible due date should win."""
        write_inputs(
            [
                "BILL9301,CUST9301,1000,ACTIVE,DIRECT,2026-04-03",
                "BILL9301,CUST9301,1000,ACTIVE,PAYROLL,2026-04-04",
                "BILL9302,CUST9302,2000,ACTIVE,PAYROLL,2026-04-02",
                "BILL9303,CUST9303,3000,ACTIVE,DEBIT,2026-04-05",
                "BILL9304,CUST9304,4000,ACTIVE,DEBIT,2026-04-05",
            ],
            [
                "BILL9301,CUST9301,1000,PR,2026-04-02",
                "BILL9302,CUST9302,2000,PR,2026-04-04",
                "BILL9303,CUST9303,3000,DBT,2026-04-06",
                "BILL9304,CUST9304,4000,DEBIT,2026-04-07",
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
        assert rows[0]["method"] == "PAYROLL"
        assert [row["method"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_advance_date_tie_uses_bill_order_and_consumption(self):
        """Same-date candidates should use advance order and still enforce consumption."""
        write_inputs(
            [
                "BILL9401,CUST9401,500,ACTIVE,PAYROLL,2026-04-05",
                "BILL9401,CUST9401,500,ACTIVE,PAYROLL,2026-04-05",
                "BILL9402,CUST9402,700,ACTIVE,DIRECT,2026-04-05",
            ],
            [
                "BILL9401,CUST9401,500,PR,2026-04-04",
                "BILL9401,CUST9401,500,PR,2026-04-04",
                "BILL9401,CUST9401,500,PR,2026-04-04",
                "BILL9402,CUST9402,700,DIRECT,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["method"] for row in rows] == ["PAYROLL", "PAYROLL", "", "DIRECT"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_advance_date_wins_before_older_bill_is_used(self):
        """A later eligible due date should be consumed before an older eligible advance."""
        write_inputs(
            [
                "BILL9501,CUST9501,800,ACTIVE,PAYROLL,2026-04-03",
                "BILL9501,CUST9501,800,ACTIVE,PAYROLL,2026-04-06",
            ],
            [
                "BILL9501,CUST9501,800,PR,2026-04-02",
                "BILL9501,CUST9501,800,PR,2026-04-04",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["method"] for row in rows] == ["PAYROLL", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_closed_repayment_date_is_not_eligible(self):
        """A repayment whose date is listed as closed must not match."""
        write_inputs(
            ["BILL9601,CUST9601,1000,ACTIVE,PAYROLL,2026-04-10"],
            ["BILL9601,CUST9601,1000,PR,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["method"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_repayment_date_is_not_eligible(self):
        """A repayment date absent from the calendar must not be treated as open."""
        write_inputs(
            ["BILL9651,CUST9651,500,ACTIVE,PAYROLL,2026-04-30"],
            ["BILL9651,CUST9651,500,PR,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["method"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_repayment_date_is_not_eligible(self):
        """A repayment with an empty repayment_date must not match any advance."""
        write_inputs(
            ["BILL9701,CUST9701,900,ACTIVE,DIRECT,2026-04-05"],
            ["BILL9701,CUST9701,900,DIRECT,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["method"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_bill_without_advance_date_is_not_eligible(self):
        """A advance with an empty advance_date cannot be consumed."""
        write_inputs(
            ["BILL9801,CUST9801,700,ACTIVE,DEBIT,"],
            ["BILL9801,CUST9801,700,DBT,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["method"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_dbt_alias_matches_debit_bill_and_emits_canonical_method(self):
        """A DBT repayment should match a DEBIT advance and report the canonical method."""
        write_inputs(
            ["BILL9901,CUST9901,600,ACTIVE,DEBIT,2026-04-10"],
            ["BILL9901,CUST9901,600,DBT,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["method"] == "DEBIT"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
