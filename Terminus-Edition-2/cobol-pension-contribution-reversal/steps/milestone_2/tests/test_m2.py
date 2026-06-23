"""Verifier tests for the pension contribution reversal COBOL reconciler."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
SRC = APP / "src" / "pension_reversal_reconcile.cbl"
BIN = APP / "build" / "pension_reversal_reconcile"
SOURCE = APP / "data" / "contributions.dat"
ACTION = APP / "data" / "reversals.dat"
CALENDAR = APP / "config" / "posting_calendar.txt"
REPORT = APP / "out" / "reversal_report.csv"
SUMMARY = APP / "out" / "reversal_summary.txt"


def src(record_id, account, category, amount, date, status="P", branch="B001"):
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
            src("PN0000000001", "ACCT1001", "EMP", 1200, "20260501", branch="BR01"),
            src("PN0000000002", "ACCT1002", "ERD", 3400, "20260502", branch="BR02"),
            src("PN0000000003", "ACCT1003", "VOL", 5600, "20260503", branch="BR03"),
        ],
        [
            action("PN0000000001", "ACCT1001", "EMP", 1200, "20260504", "R02", branch="BR01"),
            action("PN0000000002", "ACCT1002", "ERD", 3400, "20260505", "R05", branch="BR02"),
            action("PN0000000003", "ACCT1003", "VOL", 5600, "20260506", "R14", branch="BR03"),
        ],
        [],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "record_id,account,bucket,amount_cents,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["bucket"] for row in rows] == ["EMP", "ERD", "VOL"]
    assert [row["reason"] for row in rows] == ["R02", "R05", "R14"]
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
            src("PNGATE000001", "ACCT2001", "EMP", 1000, "20260510", branch="BA01"),
            src("PNGATE000002", "ACCT2002", "EMP", 2000, "20260510", status="X", branch="BA02"),
            src("PNGATE000003", "ACCT2003", "ERD", 3000, "20260511", branch="BA03"),
            src("PNGATE000004", "ACCT2004", "BAD", 4000, "20260512", branch="BA04"),
            src("PNGATE000005", "ACCT2005", "VOL", 5000, "20260513", branch="BA05"),
            src("PNCROSS00001", "ACCT9001", "EMP", 500, "20260514", branch="BX01"),
        ],
        [
            action("PNGATE000001", "ACCT2001", "EMP", 1000, "20260514", "R02", branch="BA01"),
            action("PNGATE000001", "ACCT2001", "EMP", 1000, "20260514", "R02", branch="BA01"),
            action("PNGATE000002", "ACCT2002", "EMP", 2000, "20260514", "R02", branch="BA02"),
            action("PNGATE000003", "ACCT2999", "ERD", 3000, "20260514", "R05", branch="BA03"),
            action("PNGATE000003", "ACCT2003", "ERD", 3999, "20260514", "R05", branch="BA03"),
            action("PNGATE000003", "ACCT2003", "ERD", 3000, "20260509", "R05", branch="BA03"),
            action("PNGATE000003", "ACCT2003", "ERD", 3000, "20260514", "BAD", branch="BA03"),
            action("PNGATE000004", "ACCT2004", "BAD", 4000, "20260514", "R02", branch="BA04"),
            action("PNGATE000005", "ACCT2005", "VOL", 5000, "20260514", "R14", branch="ZZ99"),
            action("PNCROSS00001", "ACCT9001", "ERD", 500, "20260514", "R02", branch="BX01"),
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
        "UNMATCHED",
    ]
    assert rows[1]["bucket"] == ""
    assert rows[9]["bucket"] == ""
    assert rows[8]["account"] == "ACCT2005"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 1000
    assert summary["unmatched_count"] == 9
    assert summary["unmatched_amount_cents"] == 25499
def test_report_keeps_action_order_blank_unmatched_category_and_positive_totals():
    """Output should keep action order, blank unmatched categories, exact statuses, and positive cent totals."""
    compile_program()
    write_inputs(
        [
            src("PNORDER0001", "ACCT4001", "EMP", 101, "20260601", branch="BD01"),
            src("PNORDER0002", "ACCT4002", "ERD", 202, "20260601", branch="BD02"),
            src("PNORDER0003", "ACCT4003", "VOL", 303, "20260601", branch="BD03"),
        ],
        [
            action("PNORDER0003", "ACCT4003", "VOL", 303, "20260602", "R14", branch="BD03"),
            action("PNORDER0002", "ACCT4002", "ERD", 999, "20260602", "R05", branch="BD02"),
            action("PNORDER0001", "ACCT4001", "EMP", 101, "20260602", "R02", branch="BD01"),
        ],
        [],
    )
    rows, summary = run_program()

    assert [row["record_id"] for row in rows] == ["PNORDER0003", "PNORDER0002", "PNORDER0001"]
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["bucket"] == ""
    assert [row["amount_cents"] for row in rows] == ["0000000303", "0000000999", "0000000101"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 404
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 999
def test_legacy_aliases_match_and_emit_canonical_categories():
    """Legacy aliases should normalize to canonical categories before matching and in the report."""
    compile_program()
    write_inputs(
        [
            src("PNAL00000001", "ACCT5001", "EMP", 1500, "20260701", branch="BE01"),
            src("PNAL00000002", "ACCT5002", "ERD", 2500, "20260701", branch="BE02"),
            src("PNAL00000003", "ACCT5003", "VOL", 3500, "20260701", branch="BE03"),
        ],
        [
            action("PNAL00000001", "ACCT5001", "EE", 1500, "20260702", "R02", branch="BE01"),
            action("PNAL00000002", "ACCT5002", "ER", 2500, "20260702", "R05", branch="BE02"),
            action("PNAL00000003", "ACCT5003", "VL", 3500, "20260702", "R14", branch="BE03"),
        ],
        [],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["bucket"] for row in rows] == ["EMP", "ERD", "VOL"]
    assert summary["matched_count"] == 3


def test_unknown_alias_does_not_match():
    """Unknown 2-char category codes must not be normalized into a valid bucket."""
    compile_program()
    write_inputs(
        [src("PNUNK0000001", "ACCT0001", "EMP", 100, "20260701", branch="B001")],
        [action("PNUNK0000001", "ACCT0001", "XX", 100, "20260702", "R02", branch="B001")],
        [],
    )
    rows, _ = run_program()
    assert rows[0]["status"] == "UNMATCHED"


def test_duplicate_actions_do_not_reuse_the_same_source_row():
    """Only the first eligible action may consume a matching source row."""
    compile_program()
    write_inputs(
        [src("PNDUP0000001", "ACCT6001", "EMP", 900, "20260710", branch="BF01")],
        [
            action("PNDUP0000001", "ACCT6001", "EMP", 900, "20260711", "R02", branch="BF01"),
            action("PNDUP0000001", "ACCT6001", "EMP", 900, "20260712", "R02", branch="BF01"),
        ],
        [],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert rows[1]["bucket"] == ""
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 900,
        "unmatched_count": 1,
        "unmatched_amount_cents": 900,
    }


def test_earliest_eligible_action_follows_input_order_not_action_date():
    """Duplicate actions must resolve by reversal input order, not by action date."""
    compile_program()
    write_inputs(
        [src("PNDUP0000002", "ACCT6002", "EMP", 900, "20260710", branch="BF02")],
        [
            action("PNDUP0000002", "ACCT6002", "EMP", 900, "20260715", "R02", branch="BF02"),
            action("PNDUP0000002", "ACCT6002", "EMP", 900, "20260711", "R02", branch="BF02"),
        ],
        [],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert rows[1]["bucket"] == ""
    assert summary["matched_count"] == 1
