"""Verifier tests for the warehouse storage credit COBOL reconciler."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
SRC = APP / "src" / "storage_credit_reconcile.cbl"
BIN = APP / "build" / "storage_credit_reconcile"
SOURCE = APP / "data" / "charges.dat"
ACTION = APP / "data" / "credits.dat"
CALENDAR = APP / "config" / "billing_calendar.txt"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.txt"


def src(record_id, account, category, amount, date, status="B", branch="B001"):
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
            src("WH0000000001", "ACCT1001", "BIN", 1200, "20260501", branch="BR01"),
            src("WH0000000002", "ACCT1002", "FLT", 3400, "20260502", branch="BR02"),
            src("WH0000000003", "ACCT1003", "CLD", 5600, "20260503", branch="BR03"),
        ],
        [
            action("WH0000000001", "ACCT1001", "BIN", 1200, "20260504", "C04", branch="BR01"),
            action("WH0000000002", "ACCT1002", "FLT", 3400, "20260505", "C08", branch="BR02"),
            action("WH0000000003", "ACCT1003", "CLD", 5600, "20260506", "C19", branch="BR03"),
        ],
        ["20260501=OPEN", "20260502=OPEN", "20260503=OPEN"],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "record_id,account,charge_type,amount_cents,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["charge_type"] for row in rows] == ["BIN", "FLT", "CLD"]
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
            src("WHGATE000001", "ACCT2001", "BIN", 1000, "20260510", branch="BA01"),
            src("WHGATE000002", "ACCT2002", "BIN", 2000, "20260510", status="X", branch="BA02"),
            src("WHGATE000003", "ACCT2003", "FLT", 3000, "20260511", branch="BA03"),
            src("WHGATE000004", "ACCT2004", "BAD", 4000, "20260512", branch="BA04"),
            src("WHGATE000005", "ACCT2005", "CLD", 5000, "20260513", branch="BA05"),
        ],
        [
            action("WHGATE000001", "ACCT2001", "BIN", 1000, "20260514", "C04", branch="BA01"),
            action("WHGATE000001", "ACCT2001", "BIN", 1000, "20260514", "C04", branch="BA01"),
            action("WHGATE000002", "ACCT2002", "BIN", 2000, "20260514", "C04", branch="BA02"),
            action("WHGATE000003", "ACCT2999", "FLT", 3000, "20260514", "C08", branch="BA03"),
            action("WHGATE000003", "ACCT2003", "FLT", 3999, "20260514", "C08", branch="BA03"),
            action("WHGATE000003", "ACCT2003", "FLT", 3000, "20260509", "C08", branch="BA03"),
            action("WHGATE000003", "ACCT2003", "FLT", 3000, "20260514", "BAD", branch="BA03"),
            action("WHGATE000004", "ACCT2004", "BAD", 4000, "20260514", "C04", branch="BA04"),
            action("WHGATE000005", "ACCT2005", "CLD", 5000, "20260514", "C19", branch="ZZ99"),
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
    assert rows[1]["charge_type"] == ""
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
            src("WHORDER0001", "ACCT4001", "BIN", 101, "20260601", branch="BD01"),
            src("WHORDER0002", "ACCT4002", "FLT", 202, "20260601", branch="BD02"),
            src("WHORDER0003", "ACCT4003", "CLD", 303, "20260601", branch="BD03"),
        ],
        [
            action("WHORDER0003", "ACCT4003", "CLD", 303, "20260602", "C19", branch="BD03"),
            action("WHORDER0002", "ACCT4002", "FLT", 999, "20260602", "C08", branch="BD02"),
            action("WHORDER0001", "ACCT4001", "BIN", 101, "20260602", "C04", branch="BD01"),
        ],
        ["20260601=OPEN"],
    )
    rows, summary = run_program()

    assert [row["record_id"] for row in rows] == ["WHORDER0003", "WHORDER0002", "WHORDER0001"]
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["charge_type"] == ""
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
            src("WHAL00000001", "ACCT5001", "BIN", 1500, "20260701", branch="BE01"),
            src("WHAL00000002", "ACCT5002", "FLT", 2500, "20260701", branch="BE02"),
            src("WHAL00000003", "ACCT5003", "CLD", 3500, "20260701", branch="BE03"),
        ],
        [
            action("WHAL00000001", "ACCT5001", "BN", 1500, "20260702", "C04", branch="BE01"),
            action("WHAL00000002", "ACCT5002", "FT", 2500, "20260702", "C08", branch="BE02"),
            action("WHAL00000003", "ACCT5003", "CD", 3500, "20260702", "C19", branch="BE03"),
        ],
        ["20260701=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["charge_type"] for row in rows] == ["BIN", "FLT", "CLD"]
    assert summary["matched_count"] == 3
def test_duplicate_actions_do_not_reuse_the_same_source_row():
    """Only the first eligible action may consume a matching source row."""
    compile_program()
    write_inputs(
        [src("WHDUP0000001", "ACCT6001", "BIN", 900, "20260710", branch="BF01")],
        [
            action("WHDUP0000001", "ACCT6001", "BIN", 900, "20260711", "C04", branch="BF01"),
            action("WHDUP0000001", "ACCT6001", "BIN", 900, "20260712", "C04", branch="BF01"),
        ],
        ["20260710=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert rows[1]["charge_type"] == ""
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 900,
        "unmatched_count": 1,
        "unmatched_amount_cents": 900,
    }
def test_closed_missing_and_malformed_calendar_dates_stay_unmatched():
    """Closed, missing, malformed, or unlisted source dates should never be treated as open."""
    compile_program()
    write_inputs(
        [
            src("WHCAL0000001", "ACCT3001", "BIN", 1111, "20260520", branch="BC01"),
            src("WHCAL0000002", "ACCT3002", "FLT", 2222, "20260521", branch="BC02"),
            src("WHCAL0000003", "ACCT3003", "CLD", 3333, "20260522", branch="BC03"),
            src("WHCAL0000004", "ACCT3004", "BIN", 4444, "BAD-DATE", branch="BC04"),
        ],
        [
            action("WHCAL0000001", "ACCT3001", "BIN", 1111, "20260523", "C04", branch="BC01"),
            action("WHCAL0000002", "ACCT3002", "FLT", 2222, "20260523", "C08", branch="BC02"),
            action("WHCAL0000003", "ACCT3003", "CLD", 3333, "20260523", "C19", branch="BC03"),
            action("WHCAL0000004", "ACCT3004", "BIN", 4444, "20260523", "C04", branch="BC04"),
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
            src("WHLAT0000001", "ACCT7001", "BIN", 1000, "20260801", branch="BG01"),
            src("WHLAT0000001", "ACCT7001", "BIN", 1000, "20260805", branch="BG01"),
            src("WHLAT0000001", "ACCT7001", "BIN", 1000, "20260803", branch="BG01"),
        ],
        [action("WHLAT0000001", "ACCT7001", "BN", 1000, "20260810", "C04", branch="BG01")],
        ["20260801=OPEN", "20260803=OPEN", "20260805=OPEN", "20260810=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["charge_type"] == "BIN"
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
        [src("WHLAT0000002", "ACCT7002", "BIN", 1000, "20260805", branch="BG01")],
        [
            action("WHLAT0000002", "ACCT7002", "BN", 1000, "20260810", "C04", branch="BG01"),
            action("WHLAT0000002", "ACCT7002", "BN", 1000, "20260811", "C04", branch="BG01"),
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
        [src("WHALM3000001", "ACCT8001", "CLD", 650, "20260901", branch="BH01")],
        [action("WHALM3000001", "ACCT8001", "CD", 650, "20260902", "C19", branch="BH01")],
        ["20260901=OPEN", "20260902=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["charge_type"] == "CLD"
    assert summary["matched_amount_cents"] == 650
