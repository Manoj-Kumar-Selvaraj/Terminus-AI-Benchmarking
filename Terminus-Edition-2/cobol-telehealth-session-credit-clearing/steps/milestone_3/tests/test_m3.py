"""Verifier tests for the telehealth session credit COBOL reconciler."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
SRC = APP / "src" / "session_credit_reconcile.cbl"
BIN = APP / "build" / "session_credit_reconcile"
SOURCE = APP / "data" / "sessions.dat"
ACTION = APP / "data" / "credits.dat"
CALENDAR = APP / "config" / "provider_calendar.txt"
REPORT = APP / "out" / "session_credit_report.csv"
SUMMARY = APP / "out" / "session_credit_summary.txt"


def src(record_id, account, category, amount, date, status="T", branch="B001"):
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
            src("THCAL0000001", "ACCT3001", "GEN", 1111, "20260520", branch="BC01"),
            src("THCAL0000002", "ACCT3002", "SPC", 2222, "20260521", branch="BC02"),
            src("THCAL0000003", "ACCT3003", "URG", 3333, "20260522", branch="BC03"),
            src("THCAL0000004", "ACCT3004", "GEN", 4444, "BAD-DATE", branch="BC04"),
        ],
        [
            action("THCAL0000001", "ACCT3001", "GEN", 1111, "20260523", "V02", branch="BC01"),
            action("THCAL0000002", "ACCT3002", "SPC", 2222, "20260523", "V09", branch="BC02"),
            action("THCAL0000003", "ACCT3003", "URG", 3333, "20260523", "V16", branch="BC03"),
            action("THCAL0000004", "ACCT3004", "GEN", 4444, "20260523", "V02", branch="BC04"),
        ],
        ["20260520=OPEN", "20260521=CLOS", "BAD-DATE=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary["matched_amount_cents"] == 1111
    assert summary["unmatched_amount_cents"] == 9999


def test_latest_source_date_wins_with_distinct_amounts():
    """Latest open source date must win even when an earlier row appears first in the file."""
    compile_program()
    write_inputs(
        [
            src("THLAT0000001", "ACCT7001", "GEN", 1000, "20260801", branch="BG01"),
            src("THLAT0000001", "ACCT7001", "GEN", 1500, "20260805", branch="BG01"),
            src("THLAT0000001", "ACCT7001", "GEN", 1200, "20260803", branch="BG01"),
        ],
        [
            action("THLAT0000001", "ACCT7001", "GN", 1500, "20260810", "V02", branch="BG01"),
            action("THLAT0000001", "ACCT7001", "GN", 1000, "20260811", "V02", branch="BG01"),
        ],
        ["20260801=OPEN", "20260803=OPEN", "20260805=OPEN", "20260810=OPEN", "20260811=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["amount_cents"] for row in rows] == ["0000001500", "0000001000"]
    assert summary == {
        "matched_count": 2,
        "matched_amount_cents": 2500,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_latest_source_date_leaves_older_row_for_narrower_action_date():
    """The latest-dated source row must be consumed first so a later action with an earlier action date can still match."""
    compile_program()
    write_inputs(
        [
            src("THLAT0000002", "ACCT7002", "GEN", 1000, "20260801", branch="BG01"),
            src("THLAT0000002", "ACCT7002", "GEN", 1000, "20260805", branch="BG01"),
        ],
        [
            action("THLAT0000002", "ACCT7002", "GN", 1000, "20260810", "V02", branch="BG01"),
            action("THLAT0000002", "ACCT7002", "GN", 1000, "20260803", "V02", branch="BG01"),
        ],
        ["20260801=OPEN", "20260805=OPEN", "20260803=OPEN", "20260810=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["amount_cents"] for row in rows] == ["0000001000", "0000001000"]
    assert summary == {
        "matched_count": 2,
        "matched_amount_cents": 2000,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_same_source_date_tie_prefers_earliest_input_row():
    """When source dates tie, equal-amount rows must be consumed in source input order."""
    compile_program()
    write_inputs(
        [
            src("THTIE0000001", "ACCT7101", "GEN", 1500, "20260805", branch="BG01"),
            src("THTIE0000001", "ACCT7101", "GEN", 1600, "20260805", branch="BG01"),
            src("THTIE0000001", "ACCT7101", "GEN", 1700, "20260805", branch="BG01"),
        ],
        [
            action("THTIE0000001", "ACCT7101", "GN", 1500, "20260810", "V02", branch="BG01"),
            action("THTIE0000001", "ACCT7101", "GN", 1600, "20260811", "V02", branch="BG01"),
            action("THTIE0000001", "ACCT7101", "GN", 1700, "20260812", "V02", branch="BG01"),
        ],
        ["20260805=OPEN", "20260810=OPEN", "20260811=OPEN", "20260812=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["amount_cents"] for row in rows] == ["0000001500", "0000001600", "0000001700"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 4800,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_duplicate_record_id_rows_are_consumed_by_position():
    """Identical source rows must be consumed independently by input position, not by record id alone."""
    compile_program()
    write_inputs(
        [
            src("THPOS000001", "ACCT9001", "GEN", 500, "20260810", branch="BX01"),
            src("THPOS000001", "ACCT9001", "GEN", 500, "20260810", branch="BX01"),
        ],
        [
            action("THPOS000001", "ACCT9001", "GEN", 500, "20260811", "V02", branch="BX01"),
            action("THPOS000001", "ACCT9001", "GEN", 500, "20260811", "V02", branch="BX01"),
            action("THPOS000001", "ACCT9001", "GEN", 500, "20260812", "V02", branch="BX01"),
        ],
        ["20260810=OPEN", "20260811=OPEN", "20260812=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["amount_cents"] for row in rows] == ["0000000500", "0000000500", "0000000500"]
    assert summary == {
        "matched_count": 2,
        "matched_amount_cents": 1000,
        "unmatched_count": 1,
        "unmatched_amount_cents": 500,
    }


def test_calendar_open_state_is_case_insensitive():
    """Mixed-case OPEN calendar states must still allow eligible source dates."""
    compile_program()
    write_inputs(
        [src("THCASE000001", "ACCT9002", "GEN", 500, "20260901", branch="BX02")],
        [action("THCASE000001", "ACCT9002", "GN", 500, "20260902", "V02", branch="BX02")],
        ["20260901=Open", "20260902=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["visit_type"] == "GEN"
    assert summary["matched_count"] == 1


def test_second_action_stays_unmatched_after_latest_source_row_is_consumed():
    """Once the only eligible source row is consumed, a second duplicate action must remain unmatched."""
    compile_program()
    write_inputs(
        [src("THLAT0000002", "ACCT7002", "GEN", 1000, "20260805", branch="BG01")],
        [
            action("THLAT0000002", "ACCT7002", "GN", 1000, "20260810", "V02", branch="BG01"),
            action("THLAT0000002", "ACCT7002", "GN", 1000, "20260811", "V02", branch="BG01"),
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
        [src("THALM3000001", "ACCT8001", "URG", 650, "20260901", branch="BH01")],
        [action("THALM3000001", "ACCT8001", "UG", 650, "20260902", "V16", branch="BH01")],
        ["20260901=OPEN", "20260902=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["visit_type"] == "URG"
    assert summary["matched_amount_cents"] == 650
