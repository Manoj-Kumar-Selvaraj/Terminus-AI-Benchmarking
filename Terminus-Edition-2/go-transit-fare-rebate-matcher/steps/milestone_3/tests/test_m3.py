"""Milestone 3 verifier tests for dated trip rebate reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
BILLS = APP / "data" / "trips.csv"
REFUNDS = APP / "data" / "rebates.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "rebate_report.csv"
SUMMARY = APP / "out" / "rebate_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go rebate reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 3 tests."""
    build_program()


def write_inputs(bill_rows, refund_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated rebate scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    BILLS.write_text("trip_id,rider_id,route_id,amount_cents,status,mode,trip_date\n" + "\n".join(bill_rows) + "\n")
    REFUNDS.write_text("trip_id,rider_id,route_id,amount_cents,mode,rebate_date\n" + "\n".join(refund_rows) + "\n")
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
    """Date gates and latest eligible trip selection for refunds."""

    def test_open_rebate_date_and_latest_trip_date_win(self):
        """Open rebate dates should gate matching and latest eligible due date should win."""
        write_inputs(
            [
                "BILL9301,CUST9301,RT-01,1000,TAPPED,BUS,2026-04-03",
                "BILL9301,CUST9301,RT-01,1000,TAPPED,RAIL,2026-04-04",
                "BILL9302,CUST9302,RT-01,2000,TAPPED,RAIL,2026-04-02",
                "BILL9303,CUST9303,RT-01,3000,TAPPED,FERRY,2026-04-05",
                "BILL9304,CUST9304,RT-01,4000,TAPPED,FERRY,2026-04-05",
            ],
            [
                "BILL9301,CUST9301,RT-01,1000,LRT,2026-04-02",
                "BILL9302,CUST9302,RT-01,2000,LRT,2026-04-04",
                "BILL9303,CUST9303,RT-01,3000,FRY,2026-04-06",
                "BILL9304,CUST9304,RT-01,4000,FERRY,2026-04-07",
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
        assert rows[0]["mode"] == "RAIL"
        assert [row["mode"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_trip_date_tie_uses_bill_order_and_consumption(self):
        """Same-date candidates should use trip order and still enforce consumption."""
        write_inputs(
            [
                "BILL9401,CUST9401,RT-01,500,TAPPED,RAIL,2026-04-05",
                "BILL9401,CUST9401,RT-01,500,TAPPED,RAIL,2026-04-05",
                "BILL9402,CUST9402,RT-01,700,TAPPED,BUS,2026-04-05",
            ],
            [
                "BILL9401,CUST9401,RT-01,500,LRT,2026-04-04",
                "BILL9401,CUST9401,RT-01,500,LRT,2026-04-04",
                "BILL9401,CUST9401,RT-01,500,LRT,2026-04-04",
                "BILL9402,CUST9402,RT-01,700,BUS,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["mode"] for row in rows] == ["RAIL", "RAIL", "", "BUS"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_trip_date_wins_before_older_bill_is_used(self):
        """A later eligible due date should be consumed before an older eligible trip."""
        write_inputs(
            [
                "BILL9501,CUST9501,RT-01,800,TAPPED,RAIL,2026-04-03",
                "BILL9501,CUST9501,RT-01,800,TAPPED,RAIL,2026-04-06",
            ],
            [
                "BILL9501,CUST9501,RT-01,800,LRT,2026-04-02",
                "BILL9501,CUST9501,RT-01,800,LRT,2026-04-04",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["mode"] for row in rows] == ["RAIL", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_closed_rebate_date_is_not_eligible(self):
        """A rebate whose date is listed as closed must not match."""
        write_inputs(
            ["BILL9601,CUST9601,RT-01,1000,TAPPED,RAIL,2026-04-10"],
            ["BILL9601,CUST9601,RT-01,1000,LRT,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["mode"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_rebate_date_is_not_eligible(self):
        """A rebate date absent from the calendar must not be treated as open."""
        write_inputs(
            ["BILL9651,CUST9651,RT-01,500,TAPPED,RAIL,2026-04-30"],
            ["BILL9651,CUST9651,RT-01,500,LRT,2026-04-15"],
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

    def test_missing_rebate_date_is_not_eligible(self):
        """A rebate with an empty rebate_date must not match any trip."""
        write_inputs(
            ["BILL9701,CUST9701,RT-01,900,TAPPED,BUS,2026-04-05"],
            ["BILL9701,CUST9701,RT-01,900,BUS,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["mode"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_bill_without_trip_date_is_not_eligible(self):
        """A trip with an empty trip_date cannot be consumed."""
        write_inputs(
            ["BILL9801,CUST9801,RT-01,700,TAPPED,FERRY,"],
            ["BILL9801,CUST9801,RT-01,700,FRY,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["mode"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_fry_alias_matches_ferry_bill_and_emits_canonical_mode(self):
        """A FRY rebate should match a FERRY trip and report the canonical mode."""
        write_inputs(
            ["BILL9901,CUST9901,RT-01,600,TAPPED,FERRY,2026-04-10"],
            ["BILL9901,CUST9901,RT-01,600,FRY,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["mode"] == "FERRY"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_bst_alias_matches_bus_trip(self):
        """A BST rebate should match a BUS trip under dated matching and emit canonical BUS."""
        write_inputs(
            ["BILL_X,CUST_X,RT-01,400,TAPPED,BUS,2026-04-05"],
            ["BILL_X,CUST_X,RT-01,400,BST,2026-04-03"],
            ["2026-04-03 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["mode"] == "BUS"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 400,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_mixed_case_tapped_status_is_eligible(self):
        """Trip status comparison should treat mixed-case TAPPED as eligible."""
        write_inputs(
            ["BILL_TAP,CUST_TAP,RT-01,900,TaPpEd,RAIL,2026-04-08"],
            ["BILL_TAP,CUST_TAP,RT-01,900,LRT,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["mode"] == "RAIL"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 900

    def test_posted_or_draft_trip_status_is_not_eligible(self):
        """POSTED and DRAFT trip rows must not match even when other fields align."""
        write_inputs(
            [
                "BILL_POST,CUST_POST,RT-01,1100,POSTED,BUS,2026-04-06",
                "BILL_DRAFT,CUST_DRAFT,RT-02,1200,DRAFT,FERRY,2026-04-06",
            ],
            [
                "BILL_POST,CUST_POST,RT-01,1100,BUS,2026-04-04",
                "BILL_DRAFT,CUST_DRAFT,RT-02,1200,FRY,2026-04-04",
            ],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert [row["mode"] for row in rows] == ["", ""]
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 2,
            "unmatched_amount_cents": 2300,
        }

