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


class TestMilestone4:
    """Refund reasons, runtime room tier policy, and ANY ranking."""

    def test_runtime_reason_eligibility_and_last_duplicate_row(self):
        reasons = "reason,eligible\nWEATHER,N\nWEATHER,Y\nNO_SHOW,Y\nNO_SHOW,N\n"
        write_inputs(
            ["ESC4101,TEAM41,1000,COMPLETED,EASY,2026-06-03", "ESC4102,TEAM41,1000,COMPLETED,EASY,2026-06-03"],
            ["ESC4101,TEAM41,1000,EASY,2026-06-02, weather ", "ESC4102,TEAM41,1000,EASY,2026-06-02,NO_SHOW"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date,refund_reason",
            calendar="2026-06-02 open\n",
            reasons=reasons,
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 1

    def test_blank_or_missing_reason_is_ineligible_when_reason_column_exists(self):
        write_inputs(
            ["ESC4201,TEAM42,500,COMPLETED,HARD,2026-06-03"],
            ["ESC4201,TEAM42,500,DIFF,2026-06-02,"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date,refund_reason",
            calendar="2026-06-02 open\n",
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["unmatched_count"] == 1

    def test_reason_gate_is_inactive_when_refund_reason_header_is_absent(self):
        write_inputs(
            ["ESC4251,TEAM42,500,COMPLETED,HARD,2026-06-03"],
            ["ESC4251,TEAM42,500,DIFF,2026-06-02"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date",
            calendar="2026-06-02 open\n",
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["room_tier"] == "HARD"
        assert summary["matched_count"] == 1

    def test_disabled_room_tier_policy_rejects_otherwise_valid_refund(self):
        tiers = "tier,enabled,priority\nEASY,true,1\nHARD,false,2\nVIP,true,3\n"
        write_inputs(
            ["ESC4301,TEAM43,700,COMPLETED,HARD,2026-06-03"],
            ["ESC4301,TEAM43,700,DIFF,2026-06-02,WEATHER"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date,refund_reason",
            calendar="2026-06-02 open\n",
            tiers=tiers,
        )
        rows, _ = run_program()
        assert rows[0]["status"] == "UNMATCHED"

    def test_any_picks_latest_slot_date_before_priority(self):
        tiers = "tier,enabled,priority\nEASY,true,1\nHARD,true,2\nVIP,true,3\n"
        write_inputs(
            ["ESC4401,TEAM44,800,COMPLETED,EASY,2026-06-04", "ESC4401,TEAM44,800,COMPLETED,HARD,2026-06-06"],
            ["ESC4401,TEAM44,800,ANY,2026-06-02,MAINT"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date,refund_reason",
            calendar="2026-06-02 open\n",
            tiers=tiers,
        )
        rows, _ = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["room_tier"] == "HARD"

    def test_any_same_date_uses_config_priority(self):
        tiers = "tier,enabled,priority\nEASY,true,5\nHARD,true,1\nVIP,true,9\n"
        write_inputs(
            ["ESC4501,TEAM45,800,COMPLETED,EASY,2026-06-04", "ESC4501,TEAM45,800,COMPLETED,HARD,2026-06-04"],
            ["ESC4501,TEAM45,800,ANY,2026-06-02,MAINT"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date,refund_reason",
            calendar="2026-06-02 open\n",
            tiers=tiers,
        )
        rows, _ = run_program()
        assert rows[0]["room_tier"] == "HARD"

    def test_any_same_date_same_priority_uses_earliest_booking_row(self):
        tiers = "tier,enabled,priority\nEASY,true,1\nHARD,true,1\nVIP,true,1\n"
        write_inputs(
            ["ESC4601,TEAM46,900,COMPLETED,VIP,2026-06-04", "ESC4601,TEAM46,900,COMPLETED,HARD,2026-06-04"],
            ["ESC4601,TEAM46,900,ANY,2026-06-02,WEATHER"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date,refund_reason",
            calendar="2026-06-02 open\n",
            tiers=tiers,
        )
        rows, _ = run_program()
        assert rows[0]["room_tier"] == "VIP"

    def test_malformed_priority_ranks_after_numeric_priority(self):
        tiers = "tier,enabled,priority\nEASY,true,bad\nHARD,true,2\nVIP,true,3\n"
        write_inputs(
            ["ESC4701,TEAM47,1000,COMPLETED,EASY,2026-06-04", "ESC4701,TEAM47,1000,COMPLETED,HARD,2026-06-04"],
            ["ESC4701,TEAM47,1000,ANY,2026-06-02,WEATHER"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date,refund_reason",
            calendar="2026-06-02 open\n",
            tiers=tiers,
        )
        rows, _ = run_program()
        assert rows[0]["room_tier"] == "HARD"

    def test_missing_priority_ranks_after_numeric_and_enabled_is_case_insensitive(self):
        tiers = "note,priority,enabled,tier\nmissing,,TrUe,EASY\nnumeric,4,tRuE,HARD\n"
        write_inputs(
            ["ESC4751,TEAM47,1000,COMPLETED,EASY,2026-06-04", "ESC4751,TEAM47,1000,COMPLETED,HARD,2026-06-04"],
            ["ESC4751,TEAM47,1000,ANY,2026-06-02,WEATHER"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date,refund_reason",
            calendar="2026-06-02 open\n",
            tiers=tiers,
        )
        rows, _ = run_program()
        assert rows[0]["room_tier"] == "HARD"

    def test_any_respects_amount_status_reason_and_calendar_gates(self):
        write_inputs(
            ["ESC4801,TEAM48,1000,DRAFT,HARD,2026-06-04", "ESC4802,TEAM48,2000,COMPLETED,HARD,2026-06-04", "ESC4803,TEAM48,3000,COMPLETED,HARD,2026-06-04"],
            ["ESC4801,TEAM48,1000,ANY,2026-06-02,WEATHER", "ESC4802,TEAM48,2001,ANY,2026-06-02,WEATHER", "ESC4803,TEAM48,3000,ANY,2026-06-05,NO_SHOW"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date,refund_reason",
            calendar="2026-06-02 open\n2026-06-05 closed\n",
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary["unmatched_count"] == 3

    def test_any_consumes_selected_row_then_next_best_candidate(self):
        tiers = "tier,enabled,priority\nEASY,true,1\nHARD,true,2\nVIP,true,3\n"
        write_inputs(
            ["ESC4901,TEAM49,1100,COMPLETED,EASY,2026-06-04", "ESC4901,TEAM49,1100,COMPLETED,HARD,2026-06-04"],
            ["ESC4901,TEAM49,1100,ANY,2026-06-02,WEATHER", "ESC4901,TEAM49,1100,ANY,2026-06-02,WEATHER"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date,refund_reason",
            calendar="2026-06-02 open\n",
            tiers=tiers,
        )
        rows, summary = run_program()
        assert [r["room_tier"] for r in rows] == ["EASY", "HARD"]
        assert summary["matched_count"] == 2
