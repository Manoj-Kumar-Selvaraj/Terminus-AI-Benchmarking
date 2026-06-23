"""Tests for milestone 1 laundromat load credit COBOL reconciliation."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
SRC = APP / "src" / "laundry_credit_reconcile.cbl"
BIN = APP / "build" / "laundry_credit_reconcile"
SOURCE = APP / "data" / "machine_loads.dat"
ACTION = APP / "data" / "credits.dat"
CALENDAR = APP / "config" / "service_calendar.txt"
REPORT = APP / "out" / "laundry_credit_report.csv"
SUMMARY = APP / "out" / "laundry_credit_summary.txt"


def src(record_id, account, category, amount, date, status="R", branch="B001"):
    """Create one fixed-width source record."""
    return f"S{record_id:<12}{account:<8}{category:<3}{amount:010d}{date}{status}{branch:<4}"


def action(record_id, account, category, amount, date, reason, branch="B001"):
    """Create one fixed-width action record."""
    return f"A{record_id:<12}{account:<8}{category:<3}{amount:010d}{date}{reason:<3}{branch:<4}"


def compile_program():
    """Compile the COBOL program once for milestone 1 tests."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cobc", "-x", "-free", "-O2", "-o", str(BIN), str(SRC)], check=True, cwd=APP, timeout=60)


def write_inputs(source_lines, action_lines, calendar_lines):
    """Replace input files so outputs cannot be precomputed from shipped fixtures.

    Calendar lines are written for shared helper reuse; milestone 1 ignores
    `/app/config/service_calendar.txt` because calendar gates start in milestone 3.
    """
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
            src("LD0000000001", "ACCT1001", "SML", 1200, "20260501", branch="BR01"),
            src("LD0000000002", "ACCT1002", "MDL", 3400, "20260502", branch="BR02"),
            src("LD0000000003", "ACCT1003", "LGE", 5600, "20260503", branch="BR03"),
        ],
        [
            action("LD0000000001", "ACCT1001", "SML", 1200, "20260504", "W02", branch="BR01"),
            action("LD0000000002", "ACCT1002", "MDL", 3400, "20260505", "W05", branch="BR02"),
            action("LD0000000003", "ACCT1003", "LGE", 5600, "20260506", "W09", branch="BR03"),
        ],
        ["20260501=OPEN", "20260502=OPEN", "20260503=OPEN"],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "record_id,account,machine_size,amount_cents,source_date,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["machine_size"] for row in rows] == ["SML", "MDL", "LGE"]
    assert [row["source_date"] for row in rows] == ["20260501", "20260502", "20260503"]
    assert [row["reason"] for row in rows] == ["W02", "W05", "W09"]
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
            src("LDGATE000001", "ACCT2001", "SML", 1000, "20260510", branch="BA01"),
            src("LDGATE000002", "ACCT2002", "SML", 2000, "20260510", status="X", branch="BA02"),
            src("LDGATE000003", "ACCT2003", "MDL", 3000, "20260511", branch="BA03"),
            src("LDGATE000004", "ACCT2004", "BAD", 4000, "20260512", branch="BA04"),
            src("LDGATE000005", "ACCT2005", "LGE", 5000, "20260513", branch="BA05"),
        ],
        [
            action("LDGATE000001", "ACCT2001", "SML", 1000, "20260514", "W02", branch="BA01"),
            action("LDGATE000001", "ACCT2001", "SML", 1000, "20260514", "W02", branch="BA01"),
            action("LDGATE000002", "ACCT2002", "SML", 2000, "20260514", "W02", branch="BA02"),
            action("LDGATE000003", "ACCT2999", "MDL", 3000, "20260514", "W05", branch="BA03"),
            action("LDGATE000003", "ACCT2003", "MDL", 3999, "20260514", "W05", branch="BA03"),
            action("LDGATE000003", "ACCT2003", "MDL", 3000, "20260509", "W05", branch="BA03"),
            action("LDGATE000003", "ACCT2003", "MDL", 3000, "20260514", "BAD", branch="BA03"),
            action("LDGATE000004", "ACCT2004", "BAD", 4000, "20260514", "W02", branch="BA04"),
            action("LDGATE000005", "ACCT2005", "LGE", 5000, "20260514", "W09", branch="ZZ99"),
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
    assert rows[1]["machine_size"] == ""
    assert rows[1]["source_date"] == ""
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
            src("LDORDER0001", "ACCT4001", "SML", 101, "20260601", branch="BD01"),
            src("LDORDER0002", "ACCT4002", "MDL", 202, "20260601", branch="BD02"),
            src("LDORDER0003", "ACCT4003", "LGE", 303, "20260601", branch="BD03"),
        ],
        [
            action("LDORDER0003", "ACCT4003", "LGE", 303, "20260602", "W09", branch="BD03"),
            action("LDORDER0002", "ACCT4002", "MDL", 999, "20260602", "W05", branch="BD02"),
            action("LDORDER0001", "ACCT4001", "SML", 101, "20260602", "W02", branch="BD01"),
        ],
        ["20260601=OPEN"],
    )
    rows, summary = run_program()

    assert [row["record_id"] for row in rows] == ["LDORDER0003", "LDORDER0002", "LDORDER0001"]
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["machine_size"] == ""
    assert rows[1]["source_date"] == ""
    assert [row["amount_cents"] for row in rows] == ["0000000303", "0000000999", "0000000101"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 404
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 999


def test_trims_padded_record_id_and_account_fields_in_report():
    """Short fixed-width ids and accounts should not leak trailing padding into CSV fields."""
    compile_program()
    write_inputs(
        [src("LDSHORT", "ACCT1", "SML", 707, "20260610", branch="BD10")],
        [action("LDSHORT", "ACCT1", "SML", 707, "20260611", "W02", branch="BD10")],
        ["20260610=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["record_id"] == "LDSHORT"
    assert rows[0]["account"] == "ACCT1"
    assert rows[0]["reason"] == "W02"
    assert rows[0]["status"] == "MATCHED"
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 707,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
