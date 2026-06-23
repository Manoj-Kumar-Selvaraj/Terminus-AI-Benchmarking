"""Verifier tests for the escape-room booking refund reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
BOOKINGS = APP / "data" / "bookings.csv"
REFUNDS = APP / "data" / "refunds.csv"
REPORT = APP / "out" / "booking_refund_report.csv"
SUMMARY = APP / "out" / "booking_refund_summary.json"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
ALIASES = APP / "config" / "room_aliases.csv"
TIERS = APP / "config" / "room_tiers.csv"
REASONS = APP / "config" / "refund_reasons.csv"
LIMITS = APP / "config" / "team_limits.csv"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def compile_program():
    """Compile the Go CLI from the mounted /app source tree."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go = str(GO) if GO.exists() else "go"
    subprocess.run([go, "build", "-o", str(BIN), "/app/cmd/reconcile"], cwd=APP, check=True, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Build once per verifier run; individual tests rewrite runtime data/config."""
    compile_program()


def reset_configs():
    """Write permissive baseline config files; tests override the file they exercise."""
    (APP / "config").mkdir(parents=True, exist_ok=True)
    ALIASES.write_text("alias,canonical,enabled\nEZ,EASY,true\nDIFF,HARD,true\nPREM,VIP,true\n")
    TIERS.write_text("tier,enabled,priority\nEASY,true,2\nHARD,true,1\nVIP,true,3\n")
    REASONS.write_text("reason,eligible\nWEATHER,Y\nMAINT,Y\nNO_SHOW,N\n")
    LIMITS.write_text("# team_id,room_tier,max_refund_cents,enabled,allow_any\n")
    CALENDAR.write_text("")


def clear_outputs():
    """Remove old outputs and plant stale files so regeneration is observable."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("stale,header\nold,row\n")
    SUMMARY.write_text('{"matched_count":"stale"}\n')


def write_inputs(bookings, refunds, *, booking_header=None, refund_header=None, calendar="", aliases=None, tiers=None, reasons=None, limits=None):
    """Replace app inputs/configs with a test scenario."""
    reset_configs()
    booking_header = booking_header or "booking_id,team_id,amount_cents,status,room_tier"
    refund_header = refund_header or "booking_id,team_id,amount_cents,room_tier"
    BOOKINGS.write_text(booking_header + "\n" + "\n".join(bookings) + ("\n" if bookings else ""))
    REFUNDS.write_text(refund_header + "\n" + "\n".join(refunds) + ("\n" if refunds else ""))
    CALENDAR.write_text(calendar)
    if aliases is not None:
        ALIASES.write_text(aliases)
    if tiers is not None:
        TIERS.write_text(tiers)
    if reasons is not None:
        REASONS.write_text(reasons)
    if limits is not None:
        LIMITS.write_text(limits)
    clear_outputs()


def run_program():
    """Run the compiled CLI and parse the required report and summary artifacts."""
    subprocess.run([str(BIN)], cwd=APP, check=True, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    raw_summary = SUMMARY.read_text()
    summary = json.loads(raw_summary)
    assert REPORT.read_text().splitlines()[0] == "booking_id,team_id,room_tier,amount_cents,status"
    assert set(summary) == {"matched_count", "matched_amount_cents", "unmatched_count", "unmatched_amount_cents"}
    assert all(isinstance(summary[k], int) for k in summary)
    assert {row["status"] for row in rows} <= {"MATCHED", "UNMATCHED"}
    return rows, summary


class TestMilestone3:
    """Dated refund eligibility, calendar behavior, latest-slot selection, and legacy fallback."""

    def test_legacy_no_date_schema_keeps_alias_and_consumption_without_calendar(self):
        write_inputs(
            ["ESC3101,TEAM31,100,COMPLETED,HARD", "ESC3101,TEAM31,100,COMPLETED,HARD"],
            ["ESC3101,TEAM31,100,DIFF", "ESC3101,TEAM31,100,DIFF"],
            calendar="2026-06-01 closed\n",
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["MATCHED", "MATCHED"]
        assert summary["matched_count"] == 2

    def test_booking_only_date_column_makes_refund_ineligible(self):
        write_inputs(
            ["ESC3201,TEAM32,200,COMPLETED,EASY,2026-06-03"],
            ["ESC3201,TEAM32,200,EZ"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            calendar="2026-06-02 open\n",
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["unmatched_amount_cents"] == 200

    def test_refund_only_date_column_makes_booking_ineligible(self):
        write_inputs(
            ["ESC3251,TEAM32,250,COMPLETED,EASY"],
            ["ESC3251,TEAM32,250,EZ,2026-06-02"],
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date",
            calendar="2026-06-02 open\n",
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["unmatched_amount_cents"] == 250

    def test_open_refund_date_and_latest_slot_date_win(self):
        write_inputs(
            ["ESC3301,TEAM33,500,COMPLETED,HARD,2026-06-02", "ESC3301,TEAM33,500,COMPLETED,HARD,2026-06-05"],
            ["ESC3301,TEAM33,500,DIFF,2026-06-01"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date",
            calendar="2026-06-01 open\n",
        )
        rows, _ = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["room_tier"] == "HARD"

    def test_latest_slot_selection_changes_second_refund_eligibility(self):
        write_inputs(
            ["ESC3401,TEAM34,700,COMPLETED,EASY,2026-06-04", "ESC3401,TEAM34,700,COMPLETED,EASY,2026-06-07"],
            ["ESC3401,TEAM34,700,EZ,2026-06-03", "ESC3401,TEAM34,700,EZ,2026-06-05"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date",
            calendar="2026-06-03 open\n2026-06-05 open\n",
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 1
        assert summary["unmatched_count"] == 1

    def test_same_slot_date_tie_uses_earliest_unused_row_and_consumption(self):
        write_inputs(
            ["ESC3501,TEAM35,300,COMPLETED,VIP,2026-06-05", "ESC3501,TEAM35,300,COMPLETED,VIP,2026-06-05"],
            ["ESC3501,TEAM35,300,PREM,2026-06-04", "ESC3501,TEAM35,300,PREM,2026-06-04", "ESC3501,TEAM35,300,PREM,2026-06-04"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date",
            calendar="2026-06-04 open\n",
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert summary["unmatched_count"] == 1

    def test_closed_unlisted_missing_and_malformed_refund_dates_are_ineligible(self):
        write_inputs(
            ["ESC3601,TEAM36,100,COMPLETED,EASY,2026-06-05"] * 4,
            ["ESC3601,TEAM36,100,EZ,2026-06-01", "ESC3601,TEAM36,100,EZ,2026-06-02", "ESC3601,TEAM36,100,EZ,2026-99-99", "ESC3601,TEAM36,100,EZ,"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date",
            calendar="2026-06-01 closed\n2026-06-03 open\n",
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary["unmatched_count"] == 4

    def test_calendar_open_state_is_case_insensitive_and_ignores_comments(self):
        write_inputs(
            ["ESC3701,TEAM37,1000,COMPLETED,HARD,2026-06-03", "ESC3702,TEAM37,1000,COMPLETED,HARD,2026-06-03"],
            ["ESC3701,TEAM37,1000,DIFF,2026-06-01", "ESC3702,TEAM37,1000,DIFF,2026-06-02"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date",
            calendar="# comment\n2026-06-01 oPeN\n2026-06-02 opEN\nmalformed row\n",
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["MATCHED", "MATCHED"]
        assert summary["matched_count"] == 2

    def test_refund_date_after_slot_date_is_unmatched(self):
        write_inputs(
            ["ESC3801,TEAM38,600,COMPLETED,EASY,2026-06-02"],
            ["ESC3801,TEAM38,600,EZ,2026-06-03"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date",
            calendar="2026-06-03 open\n",
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["unmatched_amount_cents"] == 600

    def test_dated_header_reordering_and_extra_columns(self):
        write_inputs(
            ["2026-06-04,HARD,COMPLETED,TEAM39,900,ESC3901,extra"],
            ["DIFF,2026-06-02,ESC3901,900,TEAM39,ignored"],
            booking_header="slot_date,room_tier,status,team_id,amount_cents,booking_id,extra",
            refund_header="room_tier,refund_date,booking_id,amount_cents,team_id,extra",
            calendar="2026-06-02 OPEN\n",
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert summary["matched_amount_cents"] == 900

    def test_invalid_slot_dates_are_never_candidates(self):
        write_inputs(
            ["ESC3911,TEAM39,100,COMPLETED,EASY,2026-13-01", "ESC3911,TEAM39,100,COMPLETED,EASY,2026-06-05"],
            ["ESC3911,TEAM39,100,EZ,2026-06-04"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date",
            calendar="2026-06-04 open\n",
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert summary["matched_count"] == 1
