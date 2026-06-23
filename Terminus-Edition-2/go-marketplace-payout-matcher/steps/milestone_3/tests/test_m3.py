"""Milestone 3 tests for dated order payout reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
BILLS = APP / "data" / "orders.csv"
REFUNDS = APP / "data" / "payouts.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "payout_report.csv"
SUMMARY = APP / "out" / "payout_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go payout reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 3 tests."""
    build_program()


def write_inputs(bill_rows, refund_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated payout scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    BILLS.write_text("order_id,seller_id,amount_cents,status,lane,ship_date\n" + "\n".join(bill_rows) + "\n")
    REFUNDS.write_text("order_id,seller_id,amount_cents,lane,payout_date\n" + "\n".join(refund_rows) + "\n")
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
    """Date gates and latest eligible order selection for refunds."""

    def test_open_payout_date_and_latest_ship_date_win(self):
        """Open payout dates should gate matching and latest eligible due date should win."""
        write_inputs(
            [
                "BILL9301,CUST9301,1000,SHIPPED,D2D,2026-04-03",
                "BILL9301,CUST9301,1000,SHIPPED,LOCKER,2026-04-04",
                "BILL9302,CUST9302,2000,SHIPPED,LOCKER,2026-04-02",
                "BILL9303,CUST9303,3000,SHIPPED,STORE,2026-04-05",
                "BILL9304,CUST9304,4000,SHIPPED,STORE,2026-04-05",
            ],
            [
                "BILL9301,CUST9301,1000,PKU,2026-04-02",
                "BILL9302,CUST9302,2000,PKU,2026-04-04",
                "BILL9303,CUST9303,3000,RTL,2026-04-06",
                "BILL9304,CUST9304,4000,STORE,2026-04-07",
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
        assert rows[0]["lane"] == "LOCKER"
        assert [row["lane"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_ship_date_tie_uses_bill_order_and_consumption(self):
        """Same-date candidates should break ties by earliest order row and still enforce consumption."""
        write_inputs(
            [
                "BILL9401,CUST9401,500,SHIPPED,LOCKER,2026-04-05",
                "BILL9401,CUST9401,500,SHIPPED,LOCKER,2026-04-05",
                "BILL9402,CUST9402,700,SHIPPED,D2D,2026-04-05",
            ],
            [
                "BILL9401,CUST9401,500,PKU,2026-04-04",
                "BILL9401,CUST9401,500,PKU,2026-04-04",
                "BILL9401,CUST9401,500,PKU,2026-04-04",
                "BILL9402,CUST9402,700,D2D,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["lane"] for row in rows] == ["LOCKER", "LOCKER", "", "D2D"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_ship_date_wins_before_older_bill_is_used(self):
        """A later eligible due date should be consumed before an older eligible order."""
        write_inputs(
            [
                "BILL9501,CUST9501,800,SHIPPED,LOCKER,2026-04-03",
                "BILL9501,CUST9501,800,SHIPPED,LOCKER,2026-04-06",
            ],
            [
                "BILL9501,CUST9501,800,PKU,2026-04-02",
                "BILL9501,CUST9501,800,PKU,2026-04-04",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["lane"] for row in rows] == ["LOCKER", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_closed_payout_date_is_not_eligible(self):
        """A payout whose date is listed as closed must not match."""
        write_inputs(
            ["BILL9601,CUST9601,1000,SHIPPED,LOCKER,2026-04-10"],
            ["BILL9601,CUST9601,1000,PKU,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["lane"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_payout_date_is_not_eligible(self):
        """A payout date absent from the calendar must not be treated as open."""
        write_inputs(
            ["BILL9651,CUST9651,500,SHIPPED,LOCKER,2026-04-30"],
            ["BILL9651,CUST9651,500,PKU,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["lane"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_payout_date_is_not_eligible(self):
        """A payout with an empty payout_date must not match any order."""
        write_inputs(
            ["BILL9701,CUST9701,900,SHIPPED,D2D,2026-04-05"],
            ["BILL9701,CUST9701,900,D2D,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["lane"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_bill_without_ship_date_is_not_eligible(self):
        """An order with an empty ship_date cannot be consumed."""
        write_inputs(
            ["BILL9801,CUST9801,700,SHIPPED,STORE,"],
            ["BILL9801,CUST9801,700,RTL,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["lane"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_rtl_alias_matches_store_bill_and_emits_canonical_lane(self):
        """A RTL payout should match a STORE order and report the canonical lane."""
        write_inputs(
            ["BILL9901,CUST9901,600,SHIPPED,STORE,2026-04-10"],
            ["BILL9901,CUST9901,600,RTL,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["lane"] == "STORE"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_drp_alias_matches_d2d_order_with_dated_matching(self):
        """The DRP alias should still normalize to D2D when date gates are present."""
        write_inputs(
            ["BILL9951,CUST9951,650,SHIPPED,D2D,2026-04-10"],
            ["BILL9951,CUST9951,650,DRP,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["lane"] == "D2D"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 650,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_prior_match_criteria_still_reject_latest_ship_date_decoy(self):
        """A later ship_date must not win unless the identity and lane criteria also match."""
        write_inputs(
            [
                "BILL9961,CUST9961,700,SHIPPED,D2D,2026-04-08",
                "BILL9961,CUST9961,700,SHIPPED,STORE,2026-04-12",
                "BILL9961,CUST9999,700,SHIPPED,D2D,2026-04-15",
            ],
            ["BILL9961,CUST9961,700,DRP,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["lane"] == "D2D"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 700
