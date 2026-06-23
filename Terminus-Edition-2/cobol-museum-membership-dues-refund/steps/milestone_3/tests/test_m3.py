"""Verifier tests for the museum membership dues refund COBOL reconciler."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
SRC = APP / "src" / "membership_refund_reconcile.cbl"
BIN = APP / "build" / "membership_refund_reconcile"
SOURCE = APP / "data" / "dues.dat"
ACTION = APP / "data" / "refunds.dat"
CALENDAR = APP / "config" / "membership_calendar.txt"
REPORT = APP / "out" / "dues_refund_report.csv"
SUMMARY = APP / "out" / "dues_refund_summary.txt"


def src(record_id, account, category, amount, date, status="M", branch="B001"):
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
            src("MMCAL0000001", "ACCT3001", "ANN", 1111, "20260520", branch="BC01"),
            src("MMCAL0000002", "ACCT3002", "FAM", 2222, "20260521", branch="BC02"),
            src("MMCAL0000003", "ACCT3003", "STU", 3333, "20260522", branch="BC03"),
            src("MMCAL0000004", "ACCT3004", "ANN", 4444, "BAD-DATE", branch="BC04"),
        ],
        [
            action("MMCAL0000001", "ACCT3001", "ANN", 1111, "20260523", "U01", branch="BC01"),
            action("MMCAL0000002", "ACCT3002", "FAM", 2222, "20260523", "U07", branch="BC02"),
            action("MMCAL0000003", "ACCT3003", "STU", 3333, "20260523", "U15", branch="BC03"),
            action("MMCAL0000004", "ACCT3004", "ANN", 4444, "20260523", "U01", branch="BC04"),
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
            src("MMLAT0000001", "ACCT7001", "ANN", 1000, "20260801", branch="BG01"),
            src("MMLAT0000001", "ACCT7001", "ANN", 1000, "20260805", branch="BG01"),
            src("MMLAT0000001", "ACCT7001", "ANN", 1000, "20260803", branch="BG01"),
        ],
        [action("MMLAT0000001", "ACCT7001", "AN", 1000, "20260810", "U01", branch="BG01")],
        ["20260801=OPEN", "20260803=OPEN", "20260805=OPEN", "20260810=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["plan_code"] == "ANN"
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
        [src("MMLAT0000002", "ACCT7002", "ANN", 1000, "20260805", branch="BG01")],
        [
            action("MMLAT0000002", "ACCT7002", "AN", 1000, "20260810", "U01", branch="BG01"),
            action("MMLAT0000002", "ACCT7002", "AN", 1000, "20260811", "U01", branch="BG01"),
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
        [src("MMALM3000001", "ACCT8001", "STU", 650, "20260901", branch="BH01")],
        [action("MMALM3000001", "ACCT8001", "SU", 650, "20260902", "U15", branch="BH01")],
        ["20260901=OPEN", "20260902=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["plan_code"] == "STU"
    assert summary["matched_amount_cents"] == 650
