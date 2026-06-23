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


class TestMilestone5:
    """Team-level policies, amount caps, allow_any, and blocked-row consumption behavior."""

    def test_team_policy_allows_under_cap_exact_key(self):
        limits = "team_id,room_tier,max_refund_cents,enabled,allow_any\nTEAM51,HARD,1000,true,false\n"
        write_inputs(
            ["ESC5101,TEAM51,900,COMPLETED,HARD,2026-06-04"],
            ["ESC5101,TEAM51,900,DIFF,2026-06-02,WEATHER"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date,refund_reason",
            calendar="2026-06-02 open\n",
            limits=limits,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert summary["matched_amount_cents"] == 900

    def test_team_policy_csv_is_header_addressed_with_extra_columns(self):
        limits = "note,allow_any,max_refund_cents,room_tier,team_id,enabled\nkeep,false,1000,DIFF,TEAM515,TrUe\n"
        write_inputs(
            ["ESC5151,TEAM515,900,COMPLETED,HARD,2026-06-04"],
            ["ESC5151,TEAM515,900,DIFF,2026-06-02,WEATHER"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date,refund_reason",
            calendar="2026-06-02 open\n",
            limits=limits,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert summary["matched_count"] == 1

    def test_missing_disabled_wrong_tier_and_over_limit_policies_block(self):
        limits = "team_id,room_tier,max_refund_cents,enabled,allow_any\nTEAM52,EASY,1000,true,false\nTEAM53,HARD,1000,false,false\nTEAM54,HARD,500,true,false\n"
        write_inputs(
            ["ESC5201,TEAM52,900,COMPLETED,HARD,2026-06-04", "ESC5301,TEAM53,900,COMPLETED,HARD,2026-06-04", "ESC5401,TEAM54,900,COMPLETED,HARD,2026-06-04", "ESC5501,TEAM55,900,COMPLETED,HARD,2026-06-04"],
            ["ESC5201,TEAM52,900,DIFF,2026-06-02,WEATHER", "ESC5301,TEAM53,900,DIFF,2026-06-02,WEATHER", "ESC5401,TEAM54,900,DIFF,2026-06-02,WEATHER", "ESC5501,TEAM55,900,DIFF,2026-06-02,WEATHER"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date,refund_reason",
            calendar="2026-06-02 open\n",
            limits=limits,
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary["unmatched_count"] == 4

    def test_last_well_formed_duplicate_policy_row_is_authoritative(self):
        limits = "team_id,room_tier,max_refund_cents,enabled,allow_any\nTEAM56,HARD,2000,true,false\nTEAM56,HARD,2000,false,false\nTEAM57,HARD,500,true,false\nTEAM57,HARD,2000,true,false\n"
        write_inputs(
            ["ESC5601,TEAM56,900,COMPLETED,HARD,2026-06-04", "ESC5701,TEAM57,900,COMPLETED,HARD,2026-06-04"],
            ["ESC5601,TEAM56,900,DIFF,2026-06-02,WEATHER", "ESC5701,TEAM57,900,DIFF,2026-06-02,WEATHER"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date,refund_reason",
            calendar="2026-06-02 open\n",
            limits=limits,
        )
        rows, _ = run_program()
        assert [r["status"] for r in rows] == ["UNMATCHED", "MATCHED"]

    def test_malformed_later_policy_row_does_not_override_valid_policy(self):
        limits = "team_id,room_tier,max_refund_cents,enabled,allow_any\nTEAM58,HARD,1000,true,false\nTEAM58,HARD,bad,false,false\n"
        write_inputs(
            ["ESC5801,TEAM58,900,COMPLETED,HARD,2026-06-04"],
            ["ESC5801,TEAM58,900,DIFF,2026-06-02,WEATHER"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date,refund_reason",
            calendar="2026-06-02 open\n",
            limits=limits,
        )
        rows, _ = run_program()
        assert rows[0]["status"] == "MATCHED"

    def test_allow_any_false_blocks_any_but_exact_refund_can_match(self):
        limits = "team_id,room_tier,max_refund_cents,enabled,allow_any\nTEAM59,HARD,1000,true,false\n"
        write_inputs(
            ["ESC5901,TEAM59,900,COMPLETED,HARD,2026-06-04"],
            ["ESC5901,TEAM59,900,ANY,2026-06-02,WEATHER", "ESC5901,TEAM59,900,DIFF,2026-06-02,WEATHER"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date,refund_reason",
            calendar="2026-06-02 open\n",
            limits=limits,
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["UNMATCHED", "MATCHED"]
        assert summary["matched_count"] == 1

    def test_allow_any_true_with_alias_normalized_policy_tier(self):
        limits = "team_id,room_tier,max_refund_cents,enabled,allow_any\n TEAM60 , DIFF , 1500 , TRUE , TRUE \n"
        write_inputs(
            ["ESC6001,TEAM60,1200,COMPLETED,HARD,2026-06-04"],
            ["ESC6001,TEAM60,1200,ANY,2026-06-02,MAINT"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date,refund_reason",
            calendar="2026-06-02 open\n",
            limits=limits,
        )
        rows, _ = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["room_tier"] == "HARD"

    def test_policy_blocked_candidate_does_not_consume_source_row(self):
        limits = "team_id,room_tier,max_refund_cents,enabled,allow_any\nTEAM61,HARD,500,true,false\nTEAM61,EASY,2000,true,false\n"
        write_inputs(
            ["ESC6101,TEAM61,900,COMPLETED,HARD,2026-06-04", "ESC6102,TEAM61,900,COMPLETED,EASY,2026-06-04"],
            ["ESC6101,TEAM61,900,DIFF,2026-06-02,WEATHER", "ESC6102,TEAM61,900,EZ,2026-06-02,WEATHER"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date,refund_reason",
            calendar="2026-06-02 open\n",
            limits=limits,
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["UNMATCHED", "MATCHED"]
        assert summary["matched_count"] == 1

    def test_policy_does_not_bypass_reason_or_calendar_gates(self):
        limits = "team_id,room_tier,max_refund_cents,enabled,allow_any\nTEAM62,HARD,5000,true,true\nTEAM63,HARD,5000,true,true\n"
        write_inputs(
            ["ESC6201,TEAM62,1000,COMPLETED,HARD,2026-06-04", "ESC6301,TEAM63,1000,COMPLETED,HARD,2026-06-04"],
            ["ESC6201,TEAM62,1000,ANY,2026-06-02,NO_SHOW", "ESC6301,TEAM63,1000,ANY,2026-06-05,WEATHER"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date,refund_reason",
            calendar="2026-06-02 open\n2026-06-05 closed\n",
            limits=limits,
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["UNMATCHED", "UNMATCHED"]
        assert summary["unmatched_count"] == 2

    def test_no_well_formed_policies_means_policy_gate_is_inactive(self):
        limits = "team_id,room_tier,max_refund_cents,enabled,allow_any\n,DIFF,1000,true,true\nTEAM64,HARD,zero,true,true\nTEAM64,HARD,0,true,true\nTEAM64,HARD,-1,true,true\nTEAM64,ANY,1000,true,true\n"
        write_inputs(
            ["ESC6401,TEAM64,900,COMPLETED,HARD,2026-06-04"],
            ["ESC6401,TEAM64,900,DIFF,2026-06-02,WEATHER"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date,refund_reason",
            calendar="2026-06-02 open\n",
            limits=limits,
        )
        rows, _ = run_program()
        assert rows[0]["status"] == "MATCHED"

    def test_zero_and_negative_limits_are_ignored_when_other_valid_policies_activate_gate(self):
        limits = "team_id,room_tier,max_refund_cents,enabled,allow_any\nTEAM65,HARD,0,true,false\nTEAM65,HARD,-10,true,false\nTEAM66,HARD,1000,true,false\n"
        write_inputs(
            ["ESC6501,TEAM65,900,COMPLETED,HARD,2026-06-04", "ESC6601,TEAM66,900,COMPLETED,HARD,2026-06-04"],
            ["ESC6501,TEAM65,900,DIFF,2026-06-02,WEATHER", "ESC6601,TEAM66,900,DIFF,2026-06-02,WEATHER"],
            booking_header="booking_id,team_id,amount_cents,status,room_tier,slot_date",
            refund_header="booking_id,team_id,amount_cents,room_tier,refund_date,refund_reason",
            calendar="2026-06-02 open\n",
            limits=limits,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert summary["matched_count"] == 1
