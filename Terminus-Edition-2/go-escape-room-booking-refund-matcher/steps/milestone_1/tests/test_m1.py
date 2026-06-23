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


class TestMilestone1:
    """Base exact matching, parsing, consumption, and output contract tests."""

    def test_full_identifier_and_positive_amount_matching(self):
        write_inputs(
            ["ESC100000001,TEAM1,12500,COMPLETED,EASY", "ESC100000002,TEAM2,9900,completed,hard"],
            ["ESC100000001,TEAM1,12500,EASY", "ESC100000002,TEAM2,9900,HARD"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["MATCHED", "MATCHED"]
        assert [r["room_tier"] for r in rows] == ["EASY", "HARD"]
        assert summary == {"matched_count": 2, "matched_amount_cents": 22400, "unmatched_count": 0, "unmatched_amount_cents": 0}

    def test_booking_id_prefix_collision_does_not_match(self):
        write_inputs(
            ["ESC777770001,TEAM7,3300,COMPLETED,EASY", "ESC777770002,TEAM7,3300,COMPLETED,EASY"],
            ["ESC777770003,TEAM7,3300,EASY", "ESC777770002,TEAM7,3300,EASY"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["room_tier"] == ""
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300

    def test_header_addressed_csv_with_reordered_extra_columns(self):
        write_inputs(
            ["noise-a,HARD,COMPLETED,5200,TEAM52,ESC5200"],
            ["ESC5200,unused,TEAM52,HARD,5200"],
            booking_header="ignored,room_tier,status,amount_cents,team_id,booking_id",
            refund_header="booking_id,unused,team_id,room_tier,amount_cents",
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["room_tier"] == "HARD"
        assert summary["matched_count"] == 1

    def test_trimming_and_case_normalization(self):
        write_inputs(
            [" ESC6601 , TEAM66 , 06100 , cOmPlEtEd , vIp "],
            [" ESC6601 , TEAM66 , 06100 , ViP "],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["booking_id"] == "ESC6601"
        assert rows[0]["team_id"] == "TEAM66"
        assert rows[0]["room_tier"] == "VIP"
        assert rows[0]["amount_cents"] == "06100"
        assert summary["matched_amount_cents"] == 6100

    def test_duplicate_refunds_consume_booking_once(self):
        write_inputs(
            ["ESC5551,TEAM55,7500,COMPLETED,HARD", "ESC5552,TEAM55,7500,COMPLETED,HARD"],
            ["ESC5551,TEAM55,7500,HARD", "ESC5551,TEAM55,7500,HARD", "ESC5552,TEAM55,7500,HARD"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert summary["matched_count"] == 2
        assert summary["unmatched_count"] == 1

    def test_invalid_amounts_are_unmatched_counted_but_not_totaled(self):
        write_inputs(
            ["ESC8001,TEAM80,500,COMPLETED,EASY", "ESC8002,TEAM80,abc,COMPLETED,EASY"],
            ["ESC8001,TEAM80,000500,EASY", "ESC8002,TEAM80,abc,EASY", "ESC8003,TEAM80,-5,EASY", "ESC8004,TEAM80,0,EASY"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert [r["amount_cents"] for r in rows] == ["000500", "abc", "-5", "0"]
        assert summary == {"matched_count": 1, "matched_amount_cents": 500, "unmatched_count": 3, "unmatched_amount_cents": 0}

    def test_blank_and_decimal_amounts_stay_unmatched_without_totaling(self):
        write_inputs(
            [
                "ESC8101,TEAM81,500,COMPLETED,EASY",
                "ESC8102,TEAM81,,COMPLETED,EASY",
                "ESC8103,TEAM81,12.50,COMPLETED,EASY",
            ],
            [
                "ESC8101,TEAM81,,EASY",
                "ESC8101,TEAM81,12.50,EASY",
                "ESC8102,TEAM81,500,EASY",
                "ESC8103,TEAM81,1250,EASY",
            ],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert [r["amount_cents"] for r in rows] == ["", "12.50", "500", "1250"]
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 4,
            "unmatched_amount_cents": 1750,
        }

    def test_all_match_gates_are_required(self):
        write_inputs(
            [
                "ESC3001,TEAMX,1000,COMPLETED,EASY",
                "ESC3002,TEAM2,2000,DRAFT,HARD",
                "ESC3003,TEAM3,3000,COMPLETED,CHECK",
                "ESC3004,TEAM4,4000,COMPLETED,VIP",
            ],
            ["ESC3001,TEAM1,1000,EASY", "ESC3002,TEAM2,2000,HARD", "ESC3003,TEAM3,3000,CHECK", "ESC3004,TEAM4,4100,VIP"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary["unmatched_amount_cents"] == 10100

    def test_calendar_closed_date_does_not_block_milestone1_without_dates(self):
        write_inputs(
            ["ESC9101,TEAM91,600,COMPLETED,HARD"],
            ["ESC9101,TEAM91,600,HARD"],
            calendar="2026-06-01 closed\n",
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert summary["matched_count"] == 1

    def test_stale_outputs_are_replaced_not_appended(self):
        write_inputs(["ESC9201,TEAM92,700,COMPLETED,EASY"], ["ESC9201,TEAM92,700,EASY"])
        rows, _ = run_program()
        assert len(rows) == 1
        assert "stale" not in REPORT.read_text()
        assert '"stale"' not in SUMMARY.read_text()

    def test_report_schema_order_and_blank_unmatched_tier(self):
        write_inputs(["ESC9301,TEAM93,800,COMPLETED,EASY"], ["ESC9301,TEAM93,900,EASY"])
        rows, summary = run_program()
        assert REPORT.read_text().splitlines()[0] == "booking_id,team_id,room_tier,amount_cents,status"
        assert rows[0] == {"booking_id": "ESC9301", "team_id": "TEAM93", "room_tier": "", "amount_cents": "900", "status": "UNMATCHED"}
        assert summary["unmatched_amount_cents"] == 900
