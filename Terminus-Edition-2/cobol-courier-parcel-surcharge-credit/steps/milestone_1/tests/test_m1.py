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


def test_core_keys_status_reason_and_category_match_with_positive_totals():
    """Canonical categories should match through full keys, status, reason, and branch gates."""
    compile_program()
    write_inputs(
        [
            src("CP0000000001", "ACCT1001", "STD", 1200, "20260501", branch="BR01"),
            src("CP0000000002", "ACCT1002", "NXT", 3400, "20260502", branch="BR02"),
            src("CP0000000003", "ACCT1003", "SAM", 5600, "20260503", branch="BR03"),
        ],
        [
            action("CP0000000001", "ACCT1001", "STD", 1200, "20260504", "P03", branch="BR01"),
            action("CP0000000002", "ACCT1002", "NXT", 3400, "20260505", "P08", branch="BR02"),
            action("CP0000000003", "ACCT1003", "SAM", 5600, "20260506", "P21", branch="BR03"),
        ],
        [],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "record_id,account,service_tier,amount_cents,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["service_tier"] for row in rows] == ["STD", "NXT", "SAM"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 10200,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_every_matching_gate_can_reject_a_candidate_without_reusing_rows():
    """Status, amount, account, branch, reason, date, category, and row consumption all gate matching."""
    compile_program()
    write_inputs(
        [
            src("CPGATE000001", "ACCT2001", "STD", 1000, "20260510", branch="BA01"),
            src("CPGATE000002", "ACCT2002", "STD", 2000, "20260510", status="X", branch="BA02"),
            src("CPGATE000003", "ACCT2003", "NXT", 3000, "20260511", branch="BA03"),
            src("CPGATE000004", "ACCT2004", "BAD", 4000, "20260512", branch="BA04"),
            src("CPGATE000005", "ACCT2005", "SAM", 5000, "20260513", branch="BA05"),
        ],
        [
            action("CPGATE000001", "ACCT2001", "STD", 1000, "20260514", "P03", branch="BA01"),
            action("CPGATE000001", "ACCT2001", "STD", 1000, "20260514", "P03", branch="BA01"),
            action("CPGATE000002", "ACCT2002", "STD", 2000, "20260514", "P03", branch="BA02"),
            action("CPGATE000003", "ACCT2999", "NXT", 3000, "20260514", "P08", branch="BA03"),
            action("CPGATE000003", "ACCT2003", "NXT", 3999, "20260514", "P08", branch="BA03"),
            action("CPGATE000003", "ACCT2003", "NXT", 3000, "20260509", "P08", branch="BA03"),
            action("CPGATE000003", "ACCT2003", "NXT", 3000, "20260514", "BAD", branch="BA03"),
            action("CPGATE000004", "ACCT2004", "BAD", 4000, "20260514", "P03", branch="BA04"),
            action("CPGATE000005", "ACCT2005", "SAM", 5000, "20260514", "P21", branch="ZZ99"),
        ],
        [],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == [
        "MATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
    ]
    assert rows[1]["service_tier"] == ""
    assert rows[8]["account"] == "ACCT2005"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 1000
    assert summary["unmatched_count"] == 8
    assert summary["unmatched_amount_cents"] == 24999


def test_report_keeps_action_order_blank_unmatched_category_and_positive_totals():
    """Output should keep action order, blank unmatched categories, exact statuses, and positive cent totals."""
    compile_program()
    write_inputs(
        [
            src("CPORDER0001", "ACCT4001", "STD", 101, "20260601", branch="BD01"),
            src("CPORDER0002", "ACCT4002", "NXT", 202, "20260601", branch="BD02"),
            src("CPORDER0003", "ACCT4003", "SAM", 303, "20260601", branch="BD03"),
        ],
        [
            action("CPORDER0003", "ACCT4003", "SAM", 303, "20260602", "P21", branch="BD03"),
            action("CPORDER0002", "ACCT4002", "NXT", 999, "20260602", "P08", branch="BD02"),
            action("CPORDER0001", "ACCT4001", "STD", 101, "20260602", "P03", branch="BD01"),
        ],
        [],
    )
    rows, summary = run_program()

    assert [row["record_id"] for row in rows] == ["CPORDER0003", "CPORDER0002", "CPORDER0001"]
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["service_tier"] == ""
    assert [row["amount_cents"] for row in rows] == ["0000000303", "0000000999", "0000000101"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 404
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 999
