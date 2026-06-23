"""Milestone 3 tests for dated stall refund reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
BILLS = APP / "data" / "stalls.csv"
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
    BILLS.write_text("stall_id,vendor_id,amount_cents,status,stall_type,market_date\n" + "\n".join(bill_rows) + "\n")
    REFUNDS.write_text("stall_id,vendor_id,amount_cents,stall_type,refund_date\n" + "\n".join(refund_rows) + "\n")
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
    """Date gates and latest eligible stall selection for refunds."""

    def test_open_refund_date_and_latest_market_date_win(self):
        """Open refund dates should gate matching and the latest eligible market_date should win."""
        write_inputs(
            [
                "BILL9301,CUST9301,1000,RESERVED,PRODUCE,2026-04-03",
                "BILL9301,CUST9301,1000,RESERVED,CRAFT,2026-04-04",
                "BILL9302,CUST9302,2000,RESERVED,CRAFT,2026-04-02",
                "BILL9303,CUST9303,3000,RESERVED,FOOD,2026-04-05",
                "BILL9304,CUST9304,4000,RESERVED,FOOD,2026-04-05",
            ],
            [
                "BILL9301,CUST9301,1000,CRT,2026-04-02",
                "BILL9302,CUST9302,2000,CRT,2026-04-04",
                "BILL9303,CUST9303,3000,FOD,2026-04-06",
                "BILL9304,CUST9304,4000,FOOD,2026-04-07",
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
        assert rows[0]["stall_type"] == "CRAFT"
        assert [row["stall_type"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_market_date_tie_uses_record_order_and_consumption(self):
        """Same-date candidates should use stall order and still enforce consumption."""
        write_inputs(
            [
                "BILL9401,CUST9401,500,RESERVED,CRAFT,2026-04-05",
                "BILL9401,CUST9401,500,RESERVED,CRAFT,2026-04-05",
                "BILL9402,CUST9402,700,RESERVED,PRODUCE,2026-04-05",
            ],
            [
                "BILL9401,CUST9401,500,CRT,2026-04-04",
                "BILL9401,CUST9401,500,CRT,2026-04-04",
                "BILL9401,CUST9401,500,CRT,2026-04-04",
                "BILL9402,CUST9402,700,PRODUCE,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["stall_type"] for row in rows] == ["CRAFT", "CRAFT", "", "PRODUCE"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_market_date_wins_before_older_record_is_used(self):
        """A later eligible market_date should be consumed before an older eligible stall row."""
        write_inputs(
            [
                "BILL9501,CUST9501,800,RESERVED,CRAFT,2026-04-06",
                "BILL9501,CUST9501,800,RESERVED,CRAFT,2026-04-03",
            ],
            [
                "BILL9501,CUST9501,800,CRT,2026-04-02",
                "BILL9501,CUST9501,800,CRT,2026-04-04",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["stall_type"] for row in rows] == ["CRAFT", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_closed_refund_date_is_not_eligible(self):
        """A refund whose date is listed as closed must not match."""
        write_inputs(
            ["BILL9601,CUST9601,1000,RESERVED,CRAFT,2026-04-10"],
            ["BILL9601,CUST9601,1000,CRT,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["stall_type"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_refund_date_is_not_eligible(self):
        """A refund date absent from the calendar must not be treated as open."""
        write_inputs(
            ["BILL9651,CUST9651,500,RESERVED,CRAFT,2026-04-30"],
            ["BILL9651,CUST9651,500,CRT,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["stall_type"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_refund_date_is_not_eligible(self):
        """A refund with an empty refund_date must not match any stall."""
        write_inputs(
            ["BILL9701,CUST9701,900,RESERVED,PRODUCE,2026-04-05"],
            ["BILL9701,CUST9701,900,PRODUCE,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["stall_type"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_record_without_market_date_is_not_eligible(self):
        """A stall with an empty market_date cannot be consumed."""
        write_inputs(
            ["BILL9801,CUST9801,700,RESERVED,FOOD,"],
            ["BILL9801,CUST9801,700,FOD,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["stall_type"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_fod_alias_matches_food_record_and_emits_canonical_stall_type(self):
        """A FOD refund should match a FOOD stall and report the canonical stall_type."""
        write_inputs(
            ["BILL9901,CUST9901,600,RESERVED,FOOD,2026-04-10"],
            ["BILL9901,CUST9901,600,FOD,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["stall_type"] == "FOOD"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_both_blank_dates_still_clear_like_undated_records(self):
        """When date columns exist but both sides are blank, matching should follow the undated path."""
        write_inputs(
            [
                "BILLBB1,CUSTBB1,900,RESERVED,CRAFT,",
                "BILLBB1,CUSTBB1,900,RESERVED,FOOD,2026-04-10",
            ],
            [
                "BILLBB1,CUSTBB1,900,CRT,",
                "BILLBB1,CUSTBB1,900,FOD,2026-04-05",
            ],
            [
                "2026-04-05 open",
                "2026-04-10 open",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["stall_type"] == "CRAFT"
        assert rows[1]["status"] == "MATCHED"
        assert rows[1]["stall_type"] == "FOOD"
        assert summary["matched_count"] == 2

    def test_mismatched_stall_type_does_not_match_even_with_valid_dates(self):
        """Date logic must not bypass the original stall_type equality requirement."""
        write_inputs(
            ["BILL9851,CUST9851,775,RESERVED,PRODUCE,2026-04-10"],
            ["BILL9851,CUST9851,775,CRAFT,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["stall_type"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 775

    def test_prd_alias_matches_produce_record_with_dated_matching(self):
        """The PRD alias should still normalize to PRODUCE when date gates are present."""
        write_inputs(
            ["BILL9951,CUST9951,650,RESERVED,PRODUCE,2026-04-10"],
            ["BILL9951,CUST9951,650,PRD,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["stall_type"] == "PRODUCE"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 650,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
