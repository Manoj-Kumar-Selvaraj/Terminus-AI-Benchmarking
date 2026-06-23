"""Milestone 5 verifier tests for earn-date lookback windows."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
ACCRUALS = APP / "data" / "accruals.csv"
ADJUSTMENTS = APP / "data" / "adjustments.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
JOB = APP / "config" / "job.properties"
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
    """Compile the Go reconciliation CLI once for all milestone 5 tests."""
    build_program()


def write_inputs(accrual_rows, adjustment_rows, calendar_rows, lookback_days=2):
    """Replace dated CSV inputs, calendar, and lookback setting."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    ACCRUALS.write_text("accrual_id,member_id,amount_cents,status,reason,earn_date\n" + "\n".join(accrual_rows) + "\n")
    ADJUSTMENTS.write_text(
        "accrual_id,member_id,amount_cents,reason,adjustment_date\n" + "\n".join(adjustment_rows) + "\n"
    )
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    base = JOB.read_text(encoding="utf-8")
    lines = [line for line in base.splitlines() if not line.startswith("earn_lookback_open_days=")]
    lines.append(f"earn_lookback_open_days={lookback_days}")
    JOB.write_text("\n".join(lines) + "\n", encoding="utf-8")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_raw_inputs(accrual_header, accrual_rows, adjustment_header, adjustment_rows, calendar_rows, lookback_days=2):
    """Replace inputs with explicit headers for missing-column compatibility scenarios."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    ACCRUALS.write_text(accrual_header + "\n" + "\n".join(accrual_rows) + "\n")
    ADJUSTMENTS.write_text(adjustment_header + "\n" + "\n".join(adjustment_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    base = JOB.read_text(encoding="utf-8")
    lines = [line for line in base.splitlines() if not line.startswith("earn_lookback_open_days=")]
    lines.append(f"earn_lookback_open_days={lookback_days}")
    JOB.write_text("\n".join(lines) + "\n", encoding="utf-8")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse its CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone5:
    """Earn lookback open-day window on top of dated matching."""

    def test_two_open_days_after_earn_is_eligible_with_default_lookback(self):
        """Exactly two open days after earn_date through adjustment_date should match when lookback is 2."""
        write_inputs(
            ["FILL9101,MEM9101,800,POSTED,PURCHASE,2026-04-01"],
            ["FILL9101,MEM9101,800,PURCHASE,2026-04-03"],
            [
                "2026-04-01 open",
                "2026-04-02 open",
                "2026-04-03 open",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["reason"] == "PURCHASE"
        assert summary["matched_count"] == 1

    def test_three_open_days_after_earn_exceeds_default_lookback(self):
        """Three strictly-after open days should fail the default earn_lookback_open_days=2 rule."""
        write_inputs(
            ["FILL9201,MEM9201,900,POSTED,BONUS,2026-04-01"],
            ["FILL9201,MEM9201,900,BNS,2026-04-04"],
            [
                "2026-04-01 open",
                "2026-04-02 open",
                "2026-04-03 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["reason"] == ""
        assert summary["unmatched_amount_cents"] == 900

    def test_equal_earn_and_adjustment_dates_count_zero_open_days_after(self):
        """earn_date equal to adjustment_date should count zero lookback days and still match."""
        write_inputs(
            ["FILL9301,MEM9301,650,POSTED,PROMO,2026-04-05"],
            ["FILL9301,MEM9301,650,PRM,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["reason"] == "PROMO"

    def test_closed_calendar_day_does_not_count_toward_lookback(self):
        """Only dates explicitly marked open count toward the lookback window."""
        write_inputs(
            ["FILL9401,MEM9401,700,POSTED,PURCHASE,2026-04-01"],
            ["FILL9401,MEM9401,700,PUR,2026-04-04"],
            [
                "2026-04-01 open",
                "2026-04-02 closed",
                "2026-04-03 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["reason"] == "PURCHASE"

    def test_tighter_lookback_from_job_properties_blocks_wider_window(self):
        """earn_lookback_open_days=1 should reject two open days after earn_date."""
        write_inputs(
            ["FILL9501,MEM9501,500,POSTED,PURCHASE,2026-04-01"],
            ["FILL9501,MEM9501,500,PURCHASE,2026-04-03"],
            [
                "2026-04-01 open",
                "2026-04-02 open",
                "2026-04-03 open",
            ],
            lookback_days=1,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_lookback_does_not_bypass_reason_equality(self):
        """A valid lookback window must not match when reasons differ after canonicalization."""
        write_inputs(
            ["FILL9601,MEM9601,775,POSTED,PURCHASE,2026-04-01"],
            ["FILL9601,MEM9601,775,BONUS,2026-04-02"],
            [
                "2026-04-01 open",
                "2026-04-02 open",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["reason"] == ""

    def test_latest_earn_date_still_wins_within_lookback_window(self):
        """Latest earn_date selection from milestone 3 must still apply under lookback rules."""
        write_inputs(
            [
                "FILL9701,MEM9701,600,POSTED,PURCHASE,2026-04-02",
                "FILL9701,MEM9701,600,POSTED,PURCHASE,2026-04-03",
            ],
            ["FILL9701,MEM9701,600,PUR,2026-04-03"],
            [
                "2026-04-02 open",
                "2026-04-03 open",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["reason"] == "PURCHASE"
        assert summary["matched_amount_cents"] == 600

    def test_missing_earn_date_column_makes_rows_ineligible(self):
        """Rows missing either date column remain ineligible exactly as in milestone 3."""
        write_raw_inputs(
            "accrual_id,member_id,amount_cents,status,reason",
            ["FILL001,MEM001,500,POSTED,PURCHASE"],
            "accrual_id,member_id,amount_cents,reason,adjustment_date",
            ["FILL001,MEM001,500,PURCHASE,2026-04-02"],
            ["2026-04-02 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["reason"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_absent_calendar_day_does_not_count_toward_lookback(self):
        """Calendar dates absent from the file must not count toward the lookback window."""
        write_inputs(
            ["FILL9801,MEM9801,700,POSTED,PURCHASE,2026-04-01"],
            ["FILL9801,MEM9801,700,PUR,2026-04-04"],
            [
                "2026-04-01 open",
                "2026-04-03 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["reason"] == "PURCHASE"
        assert summary["matched_count"] == 1

    def test_closed_adjustment_date_rejects_despite_valid_lookback(self):
        """A closed adjustment date must fail even when the lookback window is otherwise satisfied."""
        write_inputs(
            ["FILL9901,MEM9901,500,POSTED,PURCHASE,2026-04-01"],
            ["FILL9901,MEM9901,500,PUR,2026-04-02"],
            [
                "2026-04-01 open",
                "2026-04-02 closed",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["reason"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }
