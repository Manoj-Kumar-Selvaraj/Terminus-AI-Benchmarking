"""Milestone 3 verifier tests for dated loyalty adjustment matching."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
FILLS = APP / "data" / "accruals.csv"
REVERSALS = APP / "data" / "adjustments.csv"
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


def write_inputs(accrual_rows, adjustment_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated adjustment scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    FILLS.write_text("accrual_id,member_id,amount_cents,status,reason,earn_date\n" + "\n".join(accrual_rows) + "\n")
    REVERSALS.write_text("accrual_id,member_id,amount_cents,reason,adjustment_date\n" + "\n".join(adjustment_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_raw_inputs(accrual_header, accrual_rows, adjustment_header, adjustment_rows, calendar_rows):
    """Replace inputs with explicit headers for missing-column compatibility scenarios."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    FILLS.write_text(accrual_header + "\n" + "\n".join(accrual_rows) + "\n")
    REVERSALS.write_text(adjustment_header + "\n" + "\n".join(adjustment_rows) + "\n")
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
    """Date gates and latest eligible accrual selection for adjustments."""

    def test_open_adjustment_date_and_latest_earn_date_win(self):
        """Open adjustment dates should gate matching and latest eligible earn date should win."""
        write_inputs(
            [
                "FILL9301,MEM9301,1000,POSTED,PURCHASE,2026-04-01",
                "FILL9301,MEM9301,1000,POSTED,BONUS,2026-04-03",
                "FILL9302,MEM9302,2000,POSTED,PROMO,2026-04-05",
                "FILL9303,MEM9303,3000,POSTED,PURCHASE,2026-04-04",
                "FILL9304,MEM9304,4000,POSTED,PROMO,2026-04-05",
            ],
            [
                "FILL9301,MEM9301,1000,BNS,2026-04-04",
                "FILL9302,MEM9302,2000,PRM,2026-04-04",
                "FILL9303,MEM9303,3000,PURCHASE,2026-04-05",
                "FILL9304,MEM9304,4000,PRM,2026-04-07",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 closed",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert rows[0]["reason"] == "BONUS"
        assert [row["reason"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_earn_date_tie_uses_accrual_order_and_consumption(self):
        """Same-date candidates should use accrual order and still enforce consumption."""
        write_inputs(
            [
                "FILL9401,MEM9401,500,POSTED,BONUS,2026-04-05",
                "FILL9401,MEM9401,500,POSTED,BONUS,2026-04-05",
                "FILL9402,MEM9402,700,POSTED,PURCHASE,2026-04-05",
            ],
            [
                "FILL9401,MEM9401,500,BNS,2026-04-06",
                "FILL9401,MEM9401,500,BNS,2026-04-06",
                "FILL9401,MEM9401,500,BNS,2026-04-06",
                "FILL9402,MEM9402,700,PURCHASE,2026-04-06",
            ],
            [
                "2026-04-06 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["reason"] for row in rows] == ["BONUS", "BONUS", "", "PURCHASE"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_earn_date_wins_before_older_accrual_is_used(self):
        """A later eligible earn date should be consumed before an older eligible accrual."""
        write_inputs(
            [
                "FILL9501,MEM9501,800,POSTED,PURCHASE,2026-04-01",
                "FILL9501,MEM9501,800,POSTED,PURCHASE,2026-04-03",
            ],
            [
                "FILL9501,MEM9501,800,PURCHASE,2026-04-04",
                "FILL9501,MEM9501,800,PURCHASE,2026-04-02",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["reason"] for row in rows] == ["PURCHASE", "PURCHASE"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_earn_date_equal_to_adjustment_date_is_eligible(self):
        """An accrual whose earn date equals the adjustment date should still match."""
        write_inputs(
            ["FILL9601,MEM9601,300,POSTED,PURCHASE,2026-04-06"],
            ["FILL9601,MEM9601,300,PURCHASE,2026-04-06"],
            ["2026-04-06 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["reason"] == "PURCHASE"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 300

    def test_missing_and_absent_adjustment_dates_are_unmatched_but_readable(self):
        """Missing date values or older no-date CSV shapes should not crash and should not match."""
        write_raw_inputs(
            "accrual_id,member_id,amount_cents,status,reason,earn_date",
            [
                "FILL9701,MEM9701,400,POSTED,PURCHASE,2026-04-06",
                "FILL9702,MEM9702,500,POSTED,BONUS,2026-04-06",
            ],
            "accrual_id,member_id,amount_cents,reason,adjustment_date",
            [
                "FILL9701,MEM9701,400,PURCHASE,",
                "FILL9702,MEM9702,500,BNS,2026-04-07",
            ],
            [
                "2026-04-06 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert [row["reason"] for row in rows] == ["", ""]
        assert summary["unmatched_count"] == 2
        assert summary["unmatched_amount_cents"] == 900

        write_raw_inputs(
            "accrual_id,member_id,amount_cents,status,reason",
            ["FILL9703,MEM9703,600,POSTED,PURCHASE"],
            "accrual_id,member_id,amount_cents,reason",
            ["FILL9703,MEM9703,600,PURCHASE"],
            ["2026-04-06 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["reason"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 600

    def test_missing_accrual_earn_date_is_unmatched_even_with_open_adjustment_date(self):
        """An accrual CSV without earn_date should not match even when adjustment_date is valid and open."""
        write_raw_inputs(
            "accrual_id,member_id,amount_cents,status,reason",
            ["FILL9704,MEM9704,700,POSTED,PURCHASE"],
            "accrual_id,member_id,amount_cents,reason,adjustment_date",
            ["FILL9704,MEM9704,700,PURCHASE,2026-04-06"],
            ["2026-04-06 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["reason"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_mismatched_reason_does_not_match_even_with_valid_dates(self):
        """Date logic must not bypass the original reason equality requirement."""
        write_inputs(
            ["FILL9851,MEM9851,775,POSTED,PURCHASE,2026-04-10"],
            ["FILL9851,MEM9851,775,BONUS,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["reason"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 775

    def test_prior_match_criteria_still_reject_latest_earn_date_decoy(self):
        """A later earn_date must not win unless accrual_id, member_id, amount, and reason all match."""
        write_inputs(
            [
                "FILL9961,MEM9961,700,POSTED,PURCHASE,2026-04-03",
                "FILL9961,MEM9961,700,POSTED,BONUS,2026-04-05",
                "FILL9961,MEM9999,700,POSTED,PURCHASE,2026-04-04",
            ],
            ["FILL9961,MEM9961,700,PURCHASE,2026-04-05"],
            [
                "2026-04-03 open",
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["reason"] == "PURCHASE"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 700,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_non_posted_accrual_does_not_match_despite_later_earn_date(self):
        """POSTED status must still gate matching when a later-dated non-POSTED decoy exists."""
        write_inputs(
            [
                "FILL8001,MEM8001,500,DRAFT,PURCHASE,2026-04-05",
                "FILL8001,MEM8001,500,POSTED,PURCHASE,2026-04-03",
            ],
            ["FILL8001,MEM8001,500,PURCHASE,2026-04-06"],
            ["2026-04-06 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["reason"] == "PURCHASE"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 500

    def test_wrong_accrual_id_does_not_match_despite_later_earn_date_decoy(self):
        """accrual_id equality must still gate matching when a later-dated decoy row exists."""
        write_inputs(
            [
                "FILL9971,MEM9971,600,POSTED,PURCHASE,2026-04-03",
                "FILL9972,MEM9971,600,POSTED,PURCHASE,2026-04-04",
            ],
            ["FILL9971,MEM9971,600,PURCHASE,2026-04-05"],
            [
                "2026-04-03 open",
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["reason"] == "PURCHASE"
        assert summary["matched_count"] == 1

    def test_wrong_member_id_does_not_match_despite_later_earn_date_decoy(self):
        """member_id equality must still gate matching when a later-dated decoy row exists."""
        write_inputs(
            [
                "FILL9981,MEM9981,650,POSTED,PURCHASE,2026-04-03",
                "FILL9981,MEM9982,650,POSTED,PURCHASE,2026-04-04",
            ],
            ["FILL9981,MEM9981,650,PURCHASE,2026-04-05"],
            [
                "2026-04-03 open",
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["reason"] == "PURCHASE"

    def test_wrong_amount_does_not_match_despite_later_earn_date_decoy(self):
        """amount_cents equality must still gate matching when a later-dated decoy row exists."""
        write_inputs(
            [
                "FILL9991,MEM9991,700,POSTED,PURCHASE,2026-04-03",
                "FILL9991,MEM9991,900,POSTED,PURCHASE,2026-04-04",
            ],
            ["FILL9991,MEM9991,700,PURCHASE,2026-04-05"],
            [
                "2026-04-03 open",
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["reason"] == "PURCHASE"
