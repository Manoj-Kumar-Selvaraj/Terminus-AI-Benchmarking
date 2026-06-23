"""Verifier tests for the utility meter adjustment COBOL reconciler."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
SRC = APP / "src" / "meter_adjust_reconcile.cbl"
BIN = APP / "build" / "meter_adjust_reconcile"
SOURCE = APP / "data" / "readings.dat"
ACTION = APP / "data" / "meter_adjustments.dat"
CALENDAR = APP / "config" / "meter_calendar.txt"
REPORT = APP / "out" / "meter_adjustment_report.csv"
SUMMARY = APP / "out" / "meter_adjustment_summary.txt"


def src(record_id, account, category, amount, date, status="R", branch="B001"):
    """Create one fixed-width source record."""
    return f"S{record_id:<12}{account:<8}{category:<3}{amount:010d}{date}{status}{branch:<4}"


def action(record_id, account, category, amount, date, reason, branch="B001"):
    """Create one fixed-width action record."""
    return f"A{record_id:<12}{account:<8}{category:<3}{amount:010d}{date}{reason:<3}{branch:<4}"


def compile_program():
    """Compile the COBOL program for a test scenario."""
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
            src("UT0000000001", "ACCT1001", "RES", 1200, "20260501", branch="BR01"),
            src("UT0000000002", "ACCT1002", "COM", 3400, "20260502", branch="BR02"),
            src("UT0000000003", "ACCT1003", "IND", 5600, "20260503", branch="BR03"),
        ],
        [
            action("UT0000000001", "ACCT1001", "RES", 1200, "20260504", "M03", branch="BR01"),
            action("UT0000000002", "ACCT1002", "COM", 3400, "20260505", "M09", branch="BR02"),
            action("UT0000000003", "ACCT1003", "IND", 5600, "20260506", "M12", branch="BR03"),
        ],
        ["20260501=OPEN", "20260502=OPEN", "20260503=OPEN"],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "record_id,account,rate_code,amount_cents,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["rate_code"] for row in rows] == ["RES", "COM", "IND"]
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
            src("UTGATE000001", "ACCT2001", "RES", 1000, "20260510", branch="BA01"),
            src("UTGATE000002", "ACCT2002", "RES", 2000, "20260510", status="X", branch="BA02"),
            src("UTGATE000003", "ACCT2003", "COM", 3000, "20260511", branch="BA03"),
            src("UTGATE000004", "ACCT2004", "BAD", 4000, "20260512", branch="BA04"),
            src("UTGATE000005", "ACCT2005", "IND", 5000, "20260513", branch="BA05"),
        ],
        [
            action("UTGATE000001", "ACCT2001", "RES", 1000, "20260514", "M03", branch="BA01"),
            action("UTGATE000001", "ACCT2001", "RES", 1000, "20260514", "M03", branch="BA01"),
            action("UTGATE000002", "ACCT2002", "RES", 2000, "20260514", "M03", branch="BA02"),
            action("UTGATE000003", "ACCT2999", "COM", 3000, "20260514", "M09", branch="BA03"),
            action("UTGATE000003", "ACCT2003", "COM", 3999, "20260514", "M09", branch="BA03"),
            action("UTGATE000003", "ACCT2003", "COM", 3000, "20260509", "M09", branch="BA03"),
            action("UTGATE000003", "ACCT2003", "COM", 3000, "20260514", "M06", branch="BA03"),
            action("UTGATE000004", "ACCT2004", "BAD", 4000, "20260514", "M03", branch="BA04"),
            action("UTGATE000005", "ACCT2005", "IND", 5000, "20260514", "M12", branch="ZZ99"),
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
    assert rows[1]["rate_code"] == ""
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
            src("UTORDER0001", "ACCT4001", "RES", 101, "20260601", branch="BD01"),
            src("UTORDER0002", "ACCT4002", "COM", 202, "20260601", branch="BD02"),
            src("UTORDER0003", "ACCT4003", "IND", 303, "20260601", branch="BD03"),
        ],
        [
            action("UTORDER0003", "ACCT4003", "IND", 303, "20260602", "M12", branch="BD03"),
            action("UTORDER0002", "ACCT4002", "COM", 999, "20260602", "M09", branch="BD02"),
            action("UTORDER0001", "ACCT4001", "RES", 101, "20260602", "M03", branch="BD01"),
        ],
        ["20260601=OPEN"],
    )
    rows, summary = run_program()

    assert [row["record_id"] for row in rows] == ["UTORDER0003", "UTORDER0002", "UTORDER0001"]
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["rate_code"] == ""
    assert [row["amount_cents"] for row in rows] == ["0000000303", "0000000999", "0000000101"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 404
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 999


def test_trimmed_shorter_record_id_emits_unpadded_csv_value():
    """Shorter record_id values padded in fixed-width fields should match and trim in CSV output."""
    compile_program()
    write_inputs(
        [src("UTSHORT1", "ACCT9001", "RES", 500, "20260520", branch="BX01")],
        [action("UTSHORT1", "ACCT9001", "RES", 500, "20260521", "M03", branch="BX01")],
        ["20260520=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["record_id"] == "UTSHORT1"
    assert rows[0]["rate_code"] == "RES"
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 500,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_trimmed_shorter_account_matches_padded_fixed_width_field():
    """Shorter account values padded in fixed-width fields should match after trim."""
    compile_program()
    write_inputs(
        [src("UTTRIM000001", "ACCT1", "RES", 750, "20260515", branch="BT01")],
        [action("UTTRIM000001", "ACCT1", "RES", 750, "20260516", "M03", branch="BT01")],
        ["20260515=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["account"] == "ACCT1"
    assert rows[0]["rate_code"] == "RES"
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 750,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
