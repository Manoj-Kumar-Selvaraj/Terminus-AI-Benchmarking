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


class TestMilestone2:
    """Runtime alias handling while preserving base reconciliation behavior."""

    def test_runtime_aliases_match_and_emit_canonical_tiers(self):
        write_inputs(
            ["ESC2101,TEAM21,1000,COMPLETED,EASY", "ESC2102,TEAM21,2000,COMPLETED,HARD", "ESC2103,TEAM21,3000,COMPLETED,VIP"],
            ["ESC2101,TEAM21,1000,EZ", "ESC2102,TEAM21,2000,DIFF", "ESC2103,TEAM21,3000,PREM"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [r["room_tier"] for r in rows] == ["EASY", "HARD", "VIP"]
        assert summary["matched_amount_cents"] == 6000

    def test_alias_file_is_runtime_authoritative_not_hardcoded(self):
        aliases = "alias,canonical,enabled\nSOFT,EASY,true\nROUGH,HARD,true\n"
        write_inputs(
            ["ESC2201,TEAM22,500,COMPLETED,EASY", "ESC2202,TEAM22,600,COMPLETED,HARD"],
            ["ESC2201,TEAM22,500,SOFT", "ESC2202,TEAM22,600,DIFF"],
            aliases=aliases,
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 1
        assert summary["unmatched_amount_cents"] == 600

    def test_alias_csv_is_header_addressed_with_extra_columns(self):
        aliases = "note,enabled,canonical,alias\nfirst,true,HARD,SCARY\nignored,false,EASY,SOFT\n"
        write_inputs(
            ["ESC2251,TEAM22,500,COMPLETED,HARD"],
            ["ESC2251,TEAM22,500,SCARY"],
            aliases=aliases,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["room_tier"] == "HARD"
        assert summary["matched_count"] == 1

    def test_blank_and_malformed_alias_rows_are_ignored(self):
        aliases = (
            "alias,canonical,enabled\n"
            ",EASY,true\n"
            "VOID,,true\n"
            "SHORT,HARD\n"
            "MAYBE,HARD,maybe\n"
            "GOOD,HARD,true\n"
        )
        write_inputs(
            [
                "ESC2261,TEAM22,500,COMPLETED,EASY",
                "ESC2262,TEAM22,600,COMPLETED,HARD",
                "ESC2263,TEAM22,700,COMPLETED,HARD",
                "ESC2264,TEAM22,800,COMPLETED,HARD",
                "ESC2265,TEAM22,900,COMPLETED,HARD",
            ],
            [
                "ESC2261,TEAM22,500,",
                "ESC2262,TEAM22,600,VOID",
                "ESC2263,TEAM22,700,SHORT",
                "ESC2264,TEAM22,800,MAYBE",
                "ESC2265,TEAM22,900,GOOD",
            ],
            aliases=aliases,
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[4]["room_tier"] == "HARD"
        assert summary["matched_amount_cents"] == 900

    def test_padded_lowercase_aliases_and_booking_side_aliases_normalize(self):
        aliases = "alias,canonical,enabled\n e ,EASY,true\n h ,HARD,true\n"
        write_inputs(
            ["ESC2301,TEAM23,700,COMPLETED, h "],
            ["ESC2301,TEAM23,700, H "],
            aliases=aliases,
        )
        rows, _ = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["room_tier"] == "HARD"

    def test_disabled_alias_and_invalid_target_are_rejected(self):
        aliases = "alias,canonical,enabled\nNOPE,EASY,false\nBAD,CHECK,true\nOK,VIP,true\n"
        write_inputs(
            ["ESC2401,TEAM24,100,COMPLETED,EASY", "ESC2402,TEAM24,200,COMPLETED,VIP", "ESC2403,TEAM24,300,COMPLETED,VIP"],
            ["ESC2401,TEAM24,100,NOPE", "ESC2402,TEAM24,200,BAD", "ESC2403,TEAM24,300,OK"],
            aliases=aliases,
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["UNMATCHED", "UNMATCHED", "MATCHED"]
        assert summary["matched_amount_cents"] == 300

    def test_first_valid_duplicate_alias_row_wins(self):
        aliases = "alias,canonical,enabled\nDUPE,EASY,true\nDUPE,HARD,true\n"
        write_inputs(
            ["ESC2501,TEAM25,400,COMPLETED,EASY", "ESC2502,TEAM25,400,COMPLETED,HARD"],
            ["ESC2501,TEAM25,400,DUPE", "ESC2502,TEAM25,400,DUPE"],
            aliases=aliases,
        )
        rows, _ = run_program()
        assert [r["status"] for r in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[0]["room_tier"] == "EASY"

    def test_any_is_not_a_wildcard_in_alias_step(self):
        write_inputs(["ESC2601,TEAM26,800,COMPLETED,HARD"], ["ESC2601,TEAM26,800,ANY"])
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["room_tier"] == ""
        assert summary["unmatched_count"] == 1

    def test_aliases_do_not_bypass_full_identity_or_consumption(self):
        write_inputs(
            ["ESC2701,TEAM27,900,COMPLETED,HARD"],
            ["ESC2701,OTHER,900,DIFF", "ESC2701,TEAM27,900,DIFF", "ESC2701,TEAM27,900,DIFF"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["UNMATCHED", "MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 1

    def test_header_reordering_and_amount_preservation_still_hold_with_aliases(self):
        write_inputs(
            ["VIP,COMPLETED,TEAM28,ESC2801,001200"],
            ["PREM,001200,TEAM28,ESC2801"],
            booking_header="room_tier,status,team_id,booking_id,amount_cents",
            refund_header="room_tier,amount_cents,team_id,booking_id",
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["room_tier"] == "VIP"
        assert rows[0]["amount_cents"] == "001200"
        assert summary["matched_amount_cents"] == 1200

    def test_unknown_alias_stays_unmatched_and_blank(self):
        write_inputs(["ESC2901,TEAM29,1300,COMPLETED,EASY"], ["ESC2901,TEAM29,1300,MYSTERY"])
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["room_tier"] == ""
        assert summary["unmatched_amount_cents"] == 1300
