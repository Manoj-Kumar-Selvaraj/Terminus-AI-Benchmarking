"""Verifier tests for the bowling league fee reversal COBOL reconciler."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
SRC = APP / "src" / "league_fee_reversal_reconcile.cbl"
BIN = APP / "build" / "league_fee_reversal_reconcile"
SOURCE = APP / "data" / "lane_fees.dat"
ACTION = APP / "data" / "reversals.dat"
CALENDAR = APP / "config" / "league_calendar.txt"
REPORT = APP / "out" / "league_reversal_report.csv"
SUMMARY = APP / "out" / "league_reversal_summary.txt"


def src(record_id, account, category, amount, date, status="L", branch="B001"):
    """Create one fixed-width source record."""
    return f"S{record_id:<12}{account:<8}{category:<3}{amount:010d}{date}{status}{branch:<4}"


def action(record_id, account, category, amount, date, reason, branch="B001"):
    """Create one fixed-width action record."""
    return f"A{record_id:<12}{account:<8}{category:<3}{amount:010d}{date}{reason:<3}{branch:<4}"


def compile_program():
    """Compile the COBOL program for a verifier scenario."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cobc", "-x", "-free", "-O2", "-o", str(BIN), str(SRC)], check=True, cwd=APP, timeout=60)


def write_inputs(source_lines, action_lines, calendar_lines):
    """Replace input files so outputs cannot be precomputed from shipped fixtures."""
    SOURCE.write_text("\n".join(source_lines) + "\n")
    ACTION.write_text("\n".join(action_lines) + "\n")
    CALENDAR.write_text("\n".join(calendar_lines) + "\n")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the reconciler and return parsed report and summary data."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {}
    for raw in SUMMARY.read_text().splitlines():
        key, value = raw.split("=", 1)
        summary[key] = int(value)
    return rows, summary


def test_closed_missing_and_malformed_calendar_dates_stay_unmatched():
    """Closed, missing, malformed, or unlisted source dates should never be treated as open."""
    compile_program()
    write_inputs(
        [
            src("BLCAL0000001", "ACCT3001", "STR", 1111, "20260520", branch="BC01"),
            src("BLCAL0000002", "ACCT3002", "SCR", 2222, "20260521", branch="BC02"),
            src("BLCAL0000003", "ACCT3003", "COS", 3333, "20260522", branch="BC03"),
            src("BLCAL0000004", "ACCT3004", "STR", 4444, "BAD-DATE", branch="BC04"),
        ],
        [
            action("BLCAL0000001", "ACCT3001", "STR", 1111, "20260523", "B02", branch="BC01"),
            action("BLCAL0000002", "ACCT3002", "SCR", 2222, "20260523", "B05", branch="BC02"),
            action("BLCAL0000003", "ACCT3003", "COS", 3333, "20260523", "B11", branch="BC03"),
            action("BLCAL0000004", "ACCT3004", "STR", 4444, "20260523", "B02", branch="BC04"),
        ],
        ["20260520=OPEN", "20260521=CLOS", "BAD-DATE=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary["matched_amount_cents"] == 1111
    assert summary["unmatched_amount_cents"] == 9999


def test_latest_source_date_wins_when_multiple_rows_qualify():
    """Latest open source date must win even when an older row appears first in the file."""
    compile_program()
    write_inputs(
        [
            src("BLLAT0000001", "ACCT7001", "STR", 500, "20260801", branch="BG01"),
            src("BLLAT0000001", "ACCT7001", "SCR", 1000, "20260805", branch="BG01"),
            src("BLLAT0000001", "ACCT7001", "SCR", 700, "20260803", branch="BG01"),
        ],
        [
            action("BLLAT0000001", "ACCT7001", "SC", 1000, "20260810", "B02", branch="BG01"),
            action("BLLAT0000001", "ACCT7001", "SC", 700, "20260810", "B02", branch="BG01"),
            action("BLLAT0000001", "ACCT7001", "ST", 500, "20260810", "B02", branch="BG01"),
        ],
        ["20260801=OPEN", "20260803=OPEN", "20260805=OPEN", "20260810=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 2200,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_same_source_date_tie_prefers_earliest_input_row():
    """When source dates tie, the earliest source input row must be consumed first."""
    compile_program()
    write_inputs(
        [
            src("BLTIE0000001", "ACCT7101", "STR", 500, "20260805", branch="BG01"),
            src("BLTIE0000001", "ACCT7101", "STR", 700, "20260805", branch="BG01"),
            src("BLTIE0000001", "ACCT7101", "COS", 900, "20260808", branch="BG01"),
        ],
        [
            action("BLTIE0000001", "ACCT7101", "CO", 900, "20260810", "B02", branch="BG01"),
            action("BLTIE0000001", "ACCT7101", "ST", 500, "20260810", "B02", branch="BG01"),
            action("BLTIE0000001", "ACCT7101", "ST", 700, "20260810", "B02", branch="BG01"),
        ],
        ["20260805=OPEN", "20260808=OPEN", "20260810=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert summary["matched_count"] == 3
    assert summary["matched_amount_cents"] == 2100


def test_duplicate_record_id_rows_are_consumed_by_position():
    """Two source rows with the same record id must be independently consumable by amount."""
    compile_program()
    write_inputs(
        [
            src("BLPOS000001", "ACCT9001", "STR", 500, "20260810", branch="BX01"),
            src("BLPOS000001", "ACCT9001", "STR", 700, "20260810", branch="BX01"),
        ],
        [
            action("BLPOS000001", "ACCT9001", "STR", 500, "20260811", "B02", branch="BX01"),
            action("BLPOS000001", "ACCT9001", "STR", 700, "20260811", "B02", branch="BX01"),
        ],
        ["20260810=OPEN", "20260811=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert summary == {
        "matched_count": 2,
        "matched_amount_cents": 1200,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_calendar_open_state_is_case_insensitive():
    """Mixed-case OPEN calendar states must still allow eligible source dates."""
    compile_program()
    write_inputs(
        [src("BLCASE000001", "ACCT9002", "STR", 500, "20260901", branch="BX02")],
        [action("BLCASE000001", "ACCT9002", "ST", 500, "20260902", "B02", branch="BX02")],
        ["20260901=Open", "20260902=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["lane_type"] == "STR"
    assert summary["matched_count"] == 1



def test_second_action_stays_unmatched_after_latest_source_row_is_consumed():
    """Once the only eligible source row is consumed, a second duplicate action must remain unmatched."""
    compile_program()
    write_inputs(
        [src("BLLAT0000002", "ACCT7002", "STR", 1000, "20260805", branch="BG01")],
        [
            action("BLLAT0000002", "ACCT7002", "ST", 1000, "20260810", "B02", branch="BG01"),
            action("BLLAT0000002", "ACCT7002", "ST", 1000, "20260811", "B02", branch="BG01"),
        ],
        ["20260805=OPEN", "20260810=OPEN", "20260811=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert summary["matched_count"] == 1
    assert summary["unmatched_amount_cents"] == 1000


def test_aliases_still_work_under_calendar_gates():
    """Alias normalization must still apply when calendar gates are enforced."""
    compile_program()
    write_inputs(
        [src("BLALM3000001", "ACCT8001", "COS", 650, "20260901", branch="BH01")],
        [action("BLALM3000001", "ACCT8001", "CO", 650, "20260902", "B11", branch="BH01")],
        ["20260901=OPEN", "20260902=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["lane_type"] == "COS"
    assert summary["matched_amount_cents"] == 650
