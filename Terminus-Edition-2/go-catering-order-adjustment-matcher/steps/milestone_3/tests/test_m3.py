"""Milestone 3 verifier tests for dated order adjustment reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
BILLS = APP / "data" / "orders.csv"
REFUNDS = APP / "data" / "adjustments.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "adjustment_report.csv"
SUMMARY = APP / "out" / "adjustment_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go adjustment reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 3 tests."""
    build_program()


def write_inputs(bill_rows, refund_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated adjustment scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    BILLS.write_text("order_id,venue_id,amount_cents,status,service,fulfill_date\n" + "\n".join(bill_rows) + "\n")
    REFUNDS.write_text("order_id,venue_id,amount_cents,service,adjustment_date\n" + "\n".join(refund_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse its CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone3:
    """Date gates and latest eligible order selection for refunds."""

    def test_open_adjustment_date_gates_matching(self):
        """Closed or unlisted adjustment dates and adjustment_date after fulfill_date should not match."""
        write_inputs(
            [
                "BILL9302,CUST9302,2000,FULFILLED,DELIVERY,2026-04-02",
                "BILL9303,CUST9303,3000,FULFILLED,ONSITE,2026-04-05",
                "BILL9304,CUST9304,4000,FULFILLED,ONSITE,2026-04-05",
            ],
            [
                "BILL9302,CUST9302,2000,DEL,2026-04-04",
                "BILL9303,CUST9303,3000,OS,2026-04-06",
                "BILL9304,CUST9304,4000,ONSITE,2026-04-07",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
                "2026-04-06 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert [row["service"] for row in rows] == ["", "", ""]
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_latest_fulfill_date_wins_among_eligible_orders(self):
        """Among eligible orders, the row with the latest fulfill_date should win."""
        write_inputs(
            [
                "BILL9301,CUST9301,1000,FULFILLED,PICKUP,2026-04-03",
                "BILL9301,CUST9301,1000,FULFILLED,DELIVERY,2026-04-04",
            ],
            [
                "BILL9301,CUST9301,1000,DEL,2026-04-02",
            ],
            [
                "2026-04-02 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED"]
        assert rows[0]["service"] == "DELIVERY"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_same_fulfill_date_consumption_tracks_specific_order_rows(self):
        """Same-date orders should consume only their specific matching row."""
        write_inputs(
            [
                "BILL9401,CUST9401,500,FULFILLED,DELIVERY,2026-04-05",
                "BILL9401,CUST9401,500,FULFILLED,PICKUP,2026-04-05",
                "BILL9401,CUST9401,500,FULFILLED,ONSITE,2026-04-05",
            ],
            [
                "BILL9401,CUST9401,500,DEL,2026-04-04",
                "BILL9401,CUST9401,500,PU,2026-04-04",
                "BILL9401,CUST9401,500,OS,2026-04-04",
                "BILL9401,CUST9401,500,PU,2026-04-04",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["service"] for row in rows] == ["DELIVERY", "PICKUP", "ONSITE", ""]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1500
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_same_fulfill_date_same_key_tie_uses_earliest_order_row(self):
        """When equivalent orders tie on fulfill_date, the earliest input row should be consumed first."""
        write_inputs(
            [
                "BILL9451,CUST9451,500,FULFILLED,DELIVERY,2026-04-05",
                "BILL9451,CUST9451,500,FULFILLED,DELIVERY,2026-04-05",
            ],
            [
                "BILL9451,CUST9451,500,DEL,2026-04-04",
                "BILL9451,CUST9451,500,DEL,2026-04-04",
                "BILL9451,CUST9451,500,DEL,2026-04-04",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["service"] for row in rows] == ["DELIVERY", "DELIVERY", ""]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1000,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_latest_fulfill_date_wins_before_older_bill_is_used(self):
        """Latest fulfill_date must be consumed first so a later adjustment cannot reuse the older row."""
        write_inputs(
            [
                "BILL9501,CUST9501,800,FULFILLED,DELIVERY,2026-04-03",
                "BILL9501,CUST9501,800,FULFILLED,DELIVERY,2026-04-06",
            ],
            [
                "BILL9501,CUST9501,800,DEL,2026-04-02",
                "BILL9501,CUST9501,800,DEL,2026-04-04",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["service"] for row in rows] == ["DELIVERY", ""]
        assert [row["amount_cents"] for row in rows] == ["800", "800"]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_closed_adjustment_date_is_not_eligible(self):
        """An adjustment whose date is listed as closed must not match."""
        write_inputs(
            ["BILL9601,CUST9601,1000,FULFILLED,DELIVERY,2026-04-10"],
            ["BILL9601,CUST9601,1000,DEL,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["service"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_adjustment_date_is_not_eligible(self):
        """An adjustment date absent from the calendar must not be treated as open."""
        write_inputs(
            ["BILL9651,CUST9651,500,FULFILLED,DELIVERY,2026-04-30"],
            ["BILL9651,CUST9651,500,DEL,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["service"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_adjustment_date_is_not_eligible(self):
        """An adjustment with an empty adjustment_date must not match any order."""
        write_inputs(
            ["BILL9701,CUST9701,900,FULFILLED,PICKUP,2026-04-05"],
            ["BILL9701,CUST9701,900,PICKUP,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["service"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_bill_without_fulfill_date_is_not_eligible(self):
        """An order with an empty fulfill_date cannot be consumed."""
        write_inputs(
            ["BILL9801,CUST9801,700,FULFILLED,ONSITE,"],
            ["BILL9801,CUST9801,700,OS,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["service"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_os_alias_matches_onsite_bill_and_emits_canonical_service(self):
        """An OS adjustment should match an ONSITE order and report the canonical service."""
        write_inputs(
            ["BILL9901,CUST9901,600,FULFILLED,ONSITE,2026-04-10"],
            ["BILL9901,CUST9901,600,OS,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service"] == "ONSITE"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_pu_alias_matches_pickup_bill_with_dates_and_emits_canonical_service(self):
        """A PU adjustment should still normalize to PICKUP under dated matching."""
        write_inputs(
            ["BILL9951,CUST9951,650,FULFILLED,PICKUP,2026-04-10"],
            ["BILL9951,CUST9951,650,PU,2026-04-05"],
            ["2026-04-05 open", "2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service"] == "PICKUP"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 650,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_adjustment_date_equals_fulfill_date_is_eligible(self):
        """An adjustment date equal to fulfill_date must still be eligible when the calendar is open."""
        write_inputs(
            ["BILL001,VEN001,500,FULFILLED,DELIVERY,2026-04-05"],
            ["BILL001,VEN001,500,DEL,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service"] == "DELIVERY"
        assert summary["matched_count"] == 1

    def test_non_fulfilled_order_excluded_under_dates(self):
        """Non-FULFILLED orders must remain ineligible even when dates and services otherwise align."""
        write_inputs(
            ["BILL001,VEN001,500,DRAFT,DELIVERY,2026-04-10"],
            ["BILL001,VEN001,500,DEL,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["service"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
