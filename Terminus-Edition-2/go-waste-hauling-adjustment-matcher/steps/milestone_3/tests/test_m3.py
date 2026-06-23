"""Milestone 3 tests for dated haul adjustment reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
BILLS = APP / "data" / "hauls.csv"
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
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 3 tests."""
    build_program()


def write_inputs(bill_rows, refund_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated adjustment scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    BILLS.write_text("haul_id,account_id,amount_cents,status,route,service_date\n" + "\n".join(bill_rows) + "\n")
    REFUNDS.write_text("haul_id,account_id,amount_cents,route,adjustment_date\n" + "\n".join(refund_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_undated_inputs(bill_rows, refund_rows, calendar_rows):
    """Replace undated CSV inputs; calendar content is ignored without date columns."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    BILLS.write_text("haul_id,account_id,amount_cents,status,route\n" + "\n".join(bill_rows) + "\n")
    REFUNDS.write_text("haul_id,account_id,amount_cents,route\n" + "\n".join(refund_rows) + "\n")
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
    """Date gates and latest eligible haul selection for refunds."""

    def test_undated_inputs_skip_calendar_and_use_alias_rules(self):
        """Without date columns, matching must follow alias-aware rules and ignore the calendar."""
        write_undated_inputs(
            ["ALIAS2001,CUSTALIAS2,2468,COMPLETED,COMM"],
            ["ALIAS2001,CUSTALIAS2,2468,COM"],
            ["2026-04-01 closed", "2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["route"] == "COMM"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 2468,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_open_adjustment_date_and_latest_service_date_win(self):
        """Open adjustment dates should gate matching and latest eligible due date should win."""
        write_inputs(
            [
                "BILL9301,CUST9301,1000,COMPLETED,RESI,2026-04-03",
                "BILL9301,CUST9301,1000,COMPLETED,COMM,2026-04-04",
                "BILL9302,CUST9302,2000,COMPLETED,COMM,2026-04-02",
                "BILL9303,CUST9303,3000,COMPLETED,IND,2026-04-05",
                "BILL9304,CUST9304,4000,COMPLETED,IND,2026-04-05",
            ],
            [
                "BILL9301,CUST9301,1000,COM,2026-04-02",
                "BILL9302,CUST9302,2000,COM,2026-04-04",
                "BILL9303,CUST9303,3000,INDL,2026-04-06",
                "BILL9304,CUST9304,4000,IND,2026-04-07",
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
        assert rows[0]["route"] == "COMM"
        assert [row["route"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_service_date_tie_uses_bill_order_and_consumption(self):
        """Same-date candidates should use haul order and still enforce consumption."""
        write_inputs(
            [
                "BILL9401,CUST9401,500,COMPLETED,COMM,2026-04-05",
                "BILL9401,CUST9401,500,COMPLETED,COMM,2026-04-05",
                "BILL9402,CUST9402,700,COMPLETED,RESI,2026-04-05",
            ],
            [
                "BILL9401,CUST9401,500,COM,2026-04-04",
                "BILL9401,CUST9401,500,COM,2026-04-04",
                "BILL9401,CUST9401,500,COM,2026-04-04",
                "BILL9402,CUST9402,700,RESI,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["route"] for row in rows] == ["COMM", "COMM", "", "RESI"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_service_date_wins_before_older_bill_is_used(self):
        """A later eligible due date should be consumed before an older eligible haul."""
        write_inputs(
            [
                "BILL9501,CUST9501,800,COMPLETED,COMM,2026-04-03",
                "BILL9501,CUST9501,800,COMPLETED,COMM,2026-04-06",
            ],
            [
                "BILL9501,CUST9501,800,COM,2026-04-02",
                "BILL9501,CUST9501,800,COM,2026-04-04",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["route"] for row in rows] == ["COMM", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_closed_adjustment_date_is_not_eligible(self):
        """A adjustment whose date is listed as closed must not match."""
        write_inputs(
            ["BILL9601,CUST9601,1000,COMPLETED,COMM,2026-04-10"],
            ["BILL9601,CUST9601,1000,COM,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["route"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_adjustment_date_is_not_eligible(self):
        """A adjustment date absent from the calendar must not be treated as open."""
        write_inputs(
            ["BILL9651,CUST9651,500,COMPLETED,COMM,2026-04-30"],
            ["BILL9651,CUST9651,500,COM,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["route"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_adjustment_date_is_not_eligible(self):
        """A adjustment with an empty adjustment_date must not match any haul."""
        write_inputs(
            ["BILL9701,CUST9701,900,COMPLETED,RESI,2026-04-05"],
            ["BILL9701,CUST9701,900,RESI,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["route"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_bill_without_service_date_is_not_eligible(self):
        """A haul with an empty service_date cannot be consumed."""
        write_inputs(
            ["BILL9801,CUST9801,700,COMPLETED,IND,"],
            ["BILL9801,CUST9801,700,INDL,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["route"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_indl_alias_matches_ind_bill_and_emits_canonical_route(self):
        """A INDL adjustment should match a IND haul and report the canonical route."""
        write_inputs(
            ["BILL9901,CUST9901,600,COMPLETED,IND,2026-04-10"],
            ["BILL9901,CUST9901,600,INDL,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["route"] == "IND"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_res_alias_matches_resi_with_dates_and_emits_canonical_route(self):
        """The RES alias should still normalize to RESI under dated matching."""
        write_inputs(
            ["ALIAS3001,CUSTALIAS3,4321,COMPLETED,RESI,2026-04-10"],
            ["ALIAS3001,CUSTALIAS3,4321,RES,2026-04-05"],
            ["2026-04-05 open", "2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["route"] == "RESI"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 4321,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_route_mismatch_rejects_even_when_dates_are_valid(self):
        """Route equality should still be required independently of date eligibility."""
        write_inputs(
            ["BILL9961,CUST9961,750,COMPLETED,IND,2026-04-10"],
            ["BILL9961,CUST9961,750,COMM,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["route"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 750,
        }

    def test_status_and_amount_gates_still_apply_under_dated_matching(self):
        """COMPLETED status and exact amount must still gate matches when dates are open."""
        write_inputs(
            [
                "STAT01,CUST01,1000,POSTED,COMM,2026-04-10",
                "AMNT01,CUST02,1000,COMPLETED,COMM,2026-04-10",
            ],
            [
                "STAT01,CUST01,1000,COM,2026-04-04",
                "AMNT01,CUST02,1500,COM,2026-04-04",
            ],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert [row["route"] for row in rows] == ["", ""]
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 2,
            "unmatched_amount_cents": 2500,
        }
