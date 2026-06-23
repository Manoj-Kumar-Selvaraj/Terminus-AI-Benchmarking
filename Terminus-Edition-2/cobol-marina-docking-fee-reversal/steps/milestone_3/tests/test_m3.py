"""Verifier tests for the marina docking fee reversal COBOL reconciler."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
SRC = APP / "src" / "docking_reversal_reconcile.cbl"
BIN = APP / "build" / "docking_reversal_reconcile"
SOURCE = APP / "data" / "dock_fees.dat"
ACTION = APP / "data" / "reversals.dat"
CALENDAR = APP / "config" / "harbor_calendar.txt"
REPORT = APP / "out" / "docking_reversal_report.csv"
SUMMARY = APP / "out" / "docking_reversal_summary.txt"


def src(record_id, account, category, amount, date, status="D", branch="B001"):
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
            src("MRCAL0000001", "ACCT3001", "SLP", 1111, "20260520", branch="BC01"),
            src("MRCAL0000002", "ACCT3002", "DRY", 2222, "20260521", branch="BC02"),
            src("MRCAL0000003", "ACCT3003", "TRN", 3333, "20260522", branch="BC03"),
            src("MRCAL0000004", "ACCT3004", "SLP", 4444, "BAD-DATE", branch="BC04"),
        ],
        [
            action("MRCAL0000001", "ACCT3001", "SLP", 1111, "20260523", "H02", branch="BC01"),
            action("MRCAL0000002", "ACCT3002", "DRY", 2222, "20260523", "H06", branch="BC02"),
            action("MRCAL0000003", "ACCT3003", "TRN", 3333, "20260523", "H13", branch="BC03"),
            action("MRCAL0000004", "ACCT3004", "SLP", 4444, "20260523", "H02", branch="BC04"),
        ],
        ["20260520=OPEN", "20260521=CLOS", "BAD-DATE=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary["matched_amount_cents"] == 1111
    assert summary["unmatched_amount_cents"] == 9999


def test_latest_source_date_wins_when_multiple_rows_qualify():
    """Among eligible source rows, the latest open source date should win for a single action."""
    compile_program()
    write_inputs(
        [
            src("MRLAT0000001", "ACCT7001", "SLP", 1000, "20260801", branch="BG01"),
            src("MRLAT0000001", "ACCT7001", "SLP", 1000, "20260805", branch="BG01"),
            src("MRLAT0000001", "ACCT7001", "SLP", 1000, "20260803", branch="BG01"),
        ],
        [action("MRLAT0000001", "ACCT7001", "SP", 1000, "20260810", "H02", branch="BG01")],
        ["20260801=OPEN", "20260803=OPEN", "20260805=OPEN", "20260810=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["berth_type"] == "SLP"
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 1000,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_second_action_stays_unmatched_after_latest_source_row_is_consumed():
    """Once the only eligible source row is consumed, a second duplicate action must remain unmatched."""
    compile_program()
    write_inputs(
        [src("MRLAT0000002", "ACCT7002", "SLP", 1000, "20260805", branch="BG01")],
        [
            action("MRLAT0000002", "ACCT7002", "SP", 1000, "20260810", "H02", branch="BG01"),
            action("MRLAT0000002", "ACCT7002", "SP", 1000, "20260811", "H02", branch="BG01"),
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
        [src("MRALM3000001", "ACCT8001", "TRN", 650, "20260901", branch="BH01")],
        [action("MRALM3000001", "ACCT8001", "TN", 650, "20260902", "H13", branch="BH01")],
        ["20260901=OPEN", "20260902=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["berth_type"] == "TRN"
    assert summary["matched_amount_cents"] == 650
