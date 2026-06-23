"""Verifier tests for the courier parcel surcharge credit COBOL reconciler."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
SRC = APP / "src" / "parcel_credit_reconcile.cbl"
BIN = APP / "build" / "parcel_credit_reconcile"
SOURCE = APP / "data" / "shipments.dat"
ACTION = APP / "data" / "credits.dat"
CALENDAR = APP / "config" / "dispatch_calendar.txt"
REPORT = APP / "out" / "surcharge_credit_report.csv"
SUMMARY = APP / "out" / "surcharge_credit_summary.txt"


def src(record_id, account, category, amount, date, status="S", branch="B001"):
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
            src("CPAL00000001", "ACCT5001", "STD", 1500, "20260701", branch="BE01"),
            src("CPAL00000002", "ACCT5002", "NXT", 2500, "20260701", branch="BE02"),
            src("CPAL00000003", "ACCT5003", "SAM", 3500, "20260701", branch="BE03"),
        ],
        [
            action("CPAL00000001", "ACCT5001", "ST", 1500, "20260702", "P03", branch="BE01"),
            action("CPAL00000002", "ACCT5002", "NX", 2500, "20260702", "P08", branch="BE02"),
            action("CPAL00000003", "ACCT5003", "SM", 3500, "20260702", "P21", branch="BE03"),
        ],
        [],
    )
    rows, summary = run_program()

    assert [row["record_id"] for row in rows] == ["CPAL00000001", "CPAL00000002", "CPAL00000003"]
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["service_tier"] for row in rows] == ["STD", "NXT", "SAM"]
    assert summary["matched_count"] == 3


def test_duplicate_actions_do_not_reuse_the_same_source_row():
    """Only the first eligible action may consume a matching source row."""
    compile_program()
    write_inputs(
        [src("CPDUP0000001", "ACCT6001", "STD", 900, "20260710", branch="BF01")],
        [
            action("CPDUP0000001", "ACCT6001", "ST", 900, "20260711", "P03", branch="BF01"),
            action("CPDUP0000001", "ACCT6001", "ST", 900, "20260712", "P03", branch="BF01"),
        ],
        [],
    )
    rows, summary = run_program()

    assert [row["record_id"] for row in rows] == ["CPDUP0000001", "CPDUP0000001"]
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert rows[0]["service_tier"] == "STD"
    assert rows[1]["service_tier"] == ""
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 900,
        "unmatched_count": 1,
        "unmatched_amount_cents": 900,
    }
