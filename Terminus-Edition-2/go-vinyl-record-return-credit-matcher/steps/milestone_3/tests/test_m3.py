"""Milestone 3 verifier tests for dated sale credit reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
BILLS = APP / "data" / "sales.csv"
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
    BILLS.write_text("sale_id,buyer_id,amount_cents,status,format,ship_date\n" + "\n".join(bill_rows) + "\n")
    REFUNDS.write_text("sale_id,buyer_id,amount_cents,format,credit_date\n" + "\n".join(refund_rows) + "\n")
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
    """Date gates and latest eligible sale selection for refunds."""

    def test_open_credit_date_allows_matching_with_latest_ship_date(self):
        """An open credit date should match the sale with the latest eligible ship_date."""
        write_inputs(
            [
                "BILL9301,CUST9301,1000,SHIPPED,LP,2026-04-03",
                "BILL9301,CUST9301,1000,SHIPPED,EP,2026-04-04",
            ],
            ["BILL9301,CUST9301,1000,SING,2026-04-02"],
            ["2026-04-02 open", "2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["format"] == "EP"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_credit_date_after_ship_date_stays_unmatched(self):
        """Credits dated after the sale ship_date must stay unmatched even when the calendar is open."""
        write_inputs(
            [
                "BILL9302,CUST9302,2000,SHIPPED,EP,2026-04-02",
                "BILL9303,CUST9303,3000,SHIPPED,BOX,2026-04-05",
            ],
            [
                "BILL9302,CUST9302,2000,SING,2026-04-04",
                "BILL9303,CUST9303,3000,SET,2026-04-06",
            ],
            ["2026-04-04 open", "2026-04-05 open", "2026-04-06 open"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert [row["format"] for row in rows] == ["", ""]
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 2
        assert summary["unmatched_amount_cents"] == 5000

    def test_unlisted_calendar_credit_date_stays_unmatched(self):
        """A credit date absent from the cutoff calendar must not match even with a valid ship_date."""
        write_inputs(
            ["BILL9304,CUST9304,4000,SHIPPED,BOX,2026-04-05"],
            ["BILL9304,CUST9304,4000,BOX,2026-04-07"],
            ["2026-04-05 open", "2026-04-06 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["format"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 4000,
        }

    def test_same_ship_date_tie_uses_bill_order_and_consumption(self):
        """Same-date candidates should use sale order and still enforce consumption."""
        write_inputs(
            [
                "BILL9401,CUST9401,500,SHIPPED,EP,2026-04-05",
                "BILL9401,CUST9401,500,SHIPPED,EP,2026-04-05",
                "BILL9402,CUST9402,700,SHIPPED,LP,2026-04-05",
            ],
            [
                "BILL9401,CUST9401,500,SING,2026-04-04",
                "BILL9401,CUST9401,500,SING,2026-04-04",
                "BILL9401,CUST9401,500,SING,2026-04-04",
                "BILL9402,CUST9402,700,LP,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["format"] for row in rows] == ["EP", "EP", "", "LP"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_ship_date_wins_before_older_bill_is_used(self):
        """A later eligible due date should be consumed before an older eligible sale."""
        write_inputs(
            [
                "BILL9501,CUST9501,800,SHIPPED,EP,2026-04-03",
                "BILL9501,CUST9501,800,SHIPPED,EP,2026-04-06",
            ],
            [
                "BILL9501,CUST9501,800,SING,2026-04-02",
                "BILL9501,CUST9501,800,SING,2026-04-04",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["format"] for row in rows] == ["EP", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_closed_credit_date_is_not_eligible(self):
        """A credit whose date is listed as closed must not match."""
        write_inputs(
            ["BILL9601,CUST9601,1000,SHIPPED,EP,2026-04-10"],
            ["BILL9601,CUST9601,1000,SING,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["format"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_credit_date_is_not_eligible(self):
        """A credit date absent from the calendar must not be treated as open."""
        write_inputs(
            ["BILL9651,CUST9651,500,SHIPPED,EP,2026-04-30"],
            ["BILL9651,CUST9651,500,SING,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["format"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_credit_date_is_not_eligible(self):
        """A credit with an empty credit_date must not match any sale."""
        write_inputs(
            ["BILL9701,CUST9701,900,SHIPPED,LP,2026-04-05"],
            ["BILL9701,CUST9701,900,LP,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["format"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_bill_without_ship_date_is_not_eligible(self):
        """A sale with an empty ship_date cannot be consumed."""
        write_inputs(
            ["BILL9801,CUST9801,700,SHIPPED,BOX,"],
            ["BILL9801,CUST9801,700,SET,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["format"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_set_alias_matches_box_bill_and_emits_canonical_format(self):
        """A SET credit should match a BOX sale and report the canonical format."""
        write_inputs(
            ["BILL9901,CUST9901,600,SHIPPED,BOX,2026-04-10"],
            ["BILL9901,CUST9901,600,SET,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["format"] == "BOX"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_long_alias_matches_lp_sale_with_dated_matching(self):
        """The LONG alias should still normalize to LP when date gates are present."""
        write_inputs(
            ["BILL9951,CUST9951,650,SHIPPED,LP,2026-04-10"],
            ["BILL9951,CUST9951,650,LONG,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["format"] == "LP"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 650,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
