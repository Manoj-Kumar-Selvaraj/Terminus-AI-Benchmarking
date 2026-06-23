"""Verifier tests for the aviation hangar rent adjustment COBOL reconciler."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
SRC = APP / "src" / "hangar_adjust_reconcile.cbl"
BIN = APP / "build" / "hangar_adjust_reconcile"
SOURCE = APP / "data" / "invoices.dat"
ACTION = APP / "data" / "adjustments.dat"
CALENDAR = APP / "config" / "hangar_calendar.txt"
REPORT = APP / "out" / "hangar_adjustment_report.csv"
SUMMARY = APP / "out" / "hangar_adjustment_summary.txt"


def src(record_id, account, category, amount, date, status="H", branch="B001"):
    """Create one fixed-width source record."""
    return f"S{record_id:<12}{account:<8}{category:<3}{amount:010d}{date}{status}{branch:<4}"


def action(record_id, account, category, amount, date, reason, branch="B001"):
    """Create one fixed-width action record."""
    return f"A{record_id:<12}{account:<8}{category:<3}{amount:010d}{date}{reason:<3}{branch:<4}"


def compile_program():
    """Compile the COBOL program for a verifier scenario."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cobc", "-x", "-free", "-O2", "-o", str(BIN), str(SRC)], check=True, cwd=APP)


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
    subprocess.run([str(BIN)], check=True, cwd=APP)
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
            src("AV0000000001", "ACCT1001", "PRM", 1200, "20260501", branch="BR01"),
            src("AV0000000002", "ACCT1002", "STD", 3400, "20260502", branch="BR02"),
            src("AV0000000003", "ACCT1003", "ECO", 5600, "20260503", branch="BR03"),
        ],
        [
            action("AV0000000001", "ACCT1001", "PRM", 1200, "20260504", "A04", branch="BR01"),
            action("AV0000000002", "ACCT1002", "STD", 3400, "20260505", "A10", branch="BR02"),
            action("AV0000000003", "ACCT1003", "ECO", 5600, "20260506", "A18", branch="BR03"),
        ],
        ["20260501=OPEN", "20260502=OPEN", "20260503=OPEN"],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "record_id,account,hangar_class,amount_cents,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["hangar_class"] for row in rows] == ["PRM", "STD", "ECO"]
    assert [row["reason"] for row in rows] == ["A04", "A10", "A18"]
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
            src("AVGATE000001", "ACCT2001", "PRM", 1000, "20260510", branch="BA01"),
            src("AVGATE000002", "ACCT2002", "PRM", 2000, "20260510", status="X", branch="BA02"),
            src("AVGATE000003", "ACCT2003", "STD", 3000, "20260511", branch="BA03"),
            src("AVGATE000004", "ACCT2004", "BAD", 4000, "20260512", branch="BA04"),
            src("AVGATE000005", "ACCT2005", "ECO", 5000, "20260513", branch="BA05"),
        ],
        [
            action("AVGATE000001", "ACCT2001", "PRM", 1000, "20260514", "A04", branch="BA01"),
            action("AVGATE000001", "ACCT2001", "PRM", 1000, "20260514", "A04", branch="BA01"),
            action("AVGATE000002", "ACCT2002", "PRM", 2000, "20260514", "A04", branch="BA02"),
            action("AVGATE000003", "ACCT2999", "STD", 3000, "20260514", "A10", branch="BA03"),
            action("AVGATE000003", "ACCT2003", "STD", 3999, "20260514", "A10", branch="BA03"),
            action("AVGATE000003", "ACCT2003", "STD", 3000, "20260509", "A10", branch="BA03"),
            action("AVGATE000003", "ACCT2003", "STD", 3000, "20260514", "BAD", branch="BA03"),
            action("AVGATE000004", "ACCT2004", "BAD", 4000, "20260514", "A04", branch="BA04"),
            action("AVGATE000005", "ACCT2005", "ECO", 5000, "20260514", "A18", branch="ZZ99"),
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
    assert rows[1]["hangar_class"] == ""
    assert rows[8]["account"] == "ACCT2005"
    assert [row["reason"] for row in rows] == ["A04", "A04", "A04", "A10", "A10", "A10", "BAD", "A04", "A18"]
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 1000
    assert summary["unmatched_count"] == 8
    assert summary["unmatched_amount_cents"] == 24999


def test_report_keeps_action_order_blank_unmatched_category_and_positive_totals():
    """Output should keep action order, blank unmatched categories, exact statuses, and positive cent totals."""
    compile_program()
    write_inputs(
        [
            src("AVORDER0001", "ACCT4001", "PRM", 101, "20260601", branch="BD01"),
            src("AVORDER0002", "ACCT4002", "STD", 202, "20260601", branch="BD02"),
            src("AVORDER0003", "ACCT4003", "ECO", 303, "20260601", branch="BD03"),
        ],
        [
            action("AVORDER0003", "ACCT4003", "ECO", 303, "20260602", "A18", branch="BD03"),
            action("AVORDER0002", "ACCT4002", "STD", 999, "20260602", "A10", branch="BD02"),
            action("AVORDER0001", "ACCT4001", "PRM", 101, "20260602", "A04", branch="BD01"),
        ],
        ["20260601=OPEN"],
    )
    rows, summary = run_program()

    assert [row["record_id"] for row in rows] == ["AVORDER0003", "AVORDER0002", "AVORDER0001"]
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["hangar_class"] == ""
    assert [row["amount_cents"] for row in rows] == ["0000000303", "0000000999", "0000000101"]
    assert [row["reason"] for row in rows] == ["A18", "A10", "A04"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 404
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 999


def test_full_record_id_mismatch_is_the_only_rejection_gate():
    """A shared record-id prefix must not match when every other field is identical."""
    compile_program()
    write_inputs(
        [src("AVIDENT00001", "ACCT4101", "PRM", 707, "20260610", branch="BD11")],
        [action("AVIDENT00002", "ACCT4101", "PRM", 707, "20260611", "A04", branch="BD11")],
        ["20260610=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["hangar_class"] == ""
    assert summary == {
        "matched_count": 0,
        "matched_amount_cents": 0,
        "unmatched_count": 1,
        "unmatched_amount_cents": 707,
    }
