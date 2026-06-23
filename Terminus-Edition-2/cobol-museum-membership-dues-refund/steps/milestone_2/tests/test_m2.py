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


def test_legacy_aliases_match_and_emit_canonical_categories():
    """Legacy aliases should normalize to canonical categories before matching and in the report."""
    compile_program()
    write_inputs(
        [
            src("MMAL00000001", "ACCT5001", "ANN", 1500, "20260701", branch="BE01"),
            src("MMAL00000002", "ACCT5002", "FAM", 2500, "20260701", branch="BE02"),
            src("MMAL00000003", "ACCT5003", "STU", 3500, "20260701", branch="BE03"),
        ],
        [
            action("MMAL00000001", "ACCT5001", "AN", 1500, "20260702", "U01", branch="BE01"),
            action("MMAL00000002", "ACCT5002", "FM", 2500, "20260702", "U07", branch="BE02"),
            action("MMAL00000003", "ACCT5003", "SU", 3500, "20260702", "U15", branch="BE03"),
        ],
        ["20260701=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["plan_code"] for row in rows] == ["ANN", "FAM", "STU"]
    assert summary["matched_count"] == 3


def test_duplicate_actions_do_not_reuse_the_same_source_row():
    """Only the first eligible action may consume a matching source row."""
    compile_program()
    write_inputs(
        [src("MMDUP0000001", "ACCT6001", "ANN", 900, "20260710", branch="BF01")],
        [
            action("MMDUP0000001", "ACCT6001", "ANN", 900, "20260711", "U01", branch="BF01"),
            action("MMDUP0000001", "ACCT6001", "ANN", 900, "20260712", "U01", branch="BF01"),
        ],
        ["20260710=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert rows[1]["plan_code"] == ""
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 900,
        "unmatched_count": 1,
        "unmatched_amount_cents": 900,
    }
