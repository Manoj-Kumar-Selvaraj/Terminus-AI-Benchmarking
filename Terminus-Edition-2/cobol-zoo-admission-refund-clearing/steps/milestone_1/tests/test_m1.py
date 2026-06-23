"""Verifier tests for the zoo admission refund COBOL reconciler."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
SRC = APP / "src" / "zoo_refund_reconcile.cbl"
BIN = APP / "build" / "zoo_refund_reconcile"
SOURCE = APP / "data" / "admissions.dat"
ACTION = APP / "data" / "refunds.dat"
CALENDAR = APP / "config" / "gate_calendar.txt"
REPORT = APP / "out" / "zoo_refund_report.csv"
SUMMARY = APP / "out" / "zoo_refund_summary.txt"


def src(record_id, account, category, amount, date, status="A", branch="B001"):
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
            src("ZO0000000001", "ACCT1001", "ADT", 1200, "20260501", branch="BR01"),
            src("ZO0000000002", "ACCT1002", "CHD", 3400, "20260502", branch="BR02"),
            src("ZO0000000003", "ACCT1003", "SEN", 5600, "20260503", branch="BR03"),
        ],
        [
            action("ZO0000000001", "ACCT1001", "ADT", 1200, "20260504", "Z02", branch="BR01"),
            action("ZO0000000002", "ACCT1002", "CHD", 3400, "20260505", "Z05", branch="BR02"),
            action("ZO0000000003", "ACCT1003", "SEN", 5600, "20260506", "Z14", branch="BR03"),
        ],
        ["20260501=OPEN", "20260502=OPEN", "20260503=OPEN"],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "record_id,account,ticket_tier,amount_cents,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["ticket_tier"] for row in rows] == ["ADT", "CHD", "SEN"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 10200,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_every_matching_gate_can_reject_a_candidate_without_reusing_rows():
    """Status, amount, account, branch, reason, date, category, and row consumption all gate matching.

    Expected: 1 matched (first action), 8 unmatched (reuse, status X, wrong account,
    wrong amount, early date, bad reason, bad category, wrong branch).
    """
    compile_program()
    write_inputs(
        [
            src("ZOGATE000001", "ACCT2001", "ADT", 1000, "20260510", branch="BA01"),
            src("ZOGATE000002", "ACCT2002", "ADT", 2000, "20260510", status="X", branch="BA02"),
            src("ZOGATE000003", "ACCT2003", "CHD", 3000, "20260511", branch="BA03"),
            src("ZOGATE000004", "ACCT2004", "BAD", 4000, "20260512", branch="BA04"),
            src("ZOGATE000005", "ACCT2005", "SEN", 5000, "20260513", branch="BA05"),
        ],
        [
            action("ZOGATE000001", "ACCT2001", "ADT", 1000, "20260514", "Z02", branch="BA01"),
            action("ZOGATE000001", "ACCT2001", "ADT", 1000, "20260514", "Z02", branch="BA01"),
            action("ZOGATE000002", "ACCT2002", "ADT", 2000, "20260514", "Z02", branch="BA02"),
            action("ZOGATE000003", "ACCT2999", "CHD", 3000, "20260514", "Z05", branch="BA03"),
            action("ZOGATE000003", "ACCT2003", "CHD", 3999, "20260514", "Z05", branch="BA03"),
            action("ZOGATE000003", "ACCT2003", "CHD", 3000, "20260509", "Z05", branch="BA03"),
            action("ZOGATE000003", "ACCT2003", "CHD", 3000, "20260514", "BAD", branch="BA03"),
            action("ZOGATE000004", "ACCT2004", "BAD", 4000, "20260514", "Z02", branch="BA04"),
            action("ZOGATE000005", "ACCT2005", "SEN", 5000, "20260514", "Z14", branch="ZZ99"),
        ],
        ["20260510=OPEN", "20260511=OPEN", "20260512=OPEN", "20260513=OPEN"],
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
    assert rows[1]["ticket_tier"] == ""
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
            src("ZOORDER0001", "ACCT4001", "ADT", 101, "20260601", branch="BD01"),
            src("ZOORDER0002", "ACCT4002", "CHD", 202, "20260601", branch="BD02"),
            src("ZOORDER0003", "ACCT4003", "SEN", 303, "20260601", branch="BD03"),
        ],
        [
            action("ZOORDER0003", "ACCT4003", "SEN", 303, "20260602", "Z14", branch="BD03"),
            action("ZOORDER0002", "ACCT4002", "CHD", 999, "20260602", "Z05", branch="BD02"),
            action("ZOORDER0001", "ACCT4001", "ADT", 101, "20260602", "Z02", branch="BD01"),
        ],
        ["20260601=OPEN"],
    )
    rows, summary = run_program()

    assert [row["record_id"] for row in rows] == ["ZOORDER0003", "ZOORDER0002", "ZOORDER0001"]
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["ticket_tier"] == ""
    assert [row["amount_cents"] for row in rows] == ["0000000303", "0000000999", "0000000101"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 404
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 999
