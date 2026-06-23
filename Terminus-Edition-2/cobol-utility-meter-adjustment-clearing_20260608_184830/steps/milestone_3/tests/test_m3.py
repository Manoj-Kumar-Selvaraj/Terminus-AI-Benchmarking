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
def test_legacy_aliases_match_and_emit_canonical_categories():
    """Legacy aliases should normalize to canonical categories before matching and in the report."""
    compile_program()
    write_inputs(
        [
            src("UTAL00000001", "ACCT5001", "RES", 1500, "20260701", branch="BE01"),
            src("UTAL00000002", "ACCT5002", "COM", 2500, "20260701", branch="BE02"),
            src("UTAL00000003", "ACCT5003", "IND", 3500, "20260701", branch="BE03"),
        ],
        [
            action("UTAL00000001", "ACCT5001", "RS", 1500, "20260702", "M03", branch="BE01"),
            action("UTAL00000002", "ACCT5002", "CM", 2500, "20260702", "M09", branch="BE02"),
            action("UTAL00000003", "ACCT5003", "IN", 3500, "20260702", "M12", branch="BE03"),
        ],
        ["20260701=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["rate_code"] for row in rows] == ["RES", "COM", "IND"]
    assert summary["matched_count"] == 3
def test_duplicate_actions_do_not_reuse_the_same_source_row():
    """Only the first eligible action may consume a matching source row."""
    compile_program()
    write_inputs(
        [src("UTDUP0000001", "ACCT6001", "RES", 900, "20260710", branch="BF01")],
        [
            action("UTDUP0000001", "ACCT6001", "RES", 900, "20260711", "M03", branch="BF01"),
            action("UTDUP0000001", "ACCT6001", "RES", 900, "20260712", "M03", branch="BF01"),
        ],
        ["20260710=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert rows[1]["rate_code"] == ""
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
            src("UTCAL0000001", "ACCT3001", "RES", 1111, "20260520", branch="BC01"),
            src("UTCAL0000002", "ACCT3002", "COM", 2222, "20260521", branch="BC02"),
            src("UTCAL0000003", "ACCT3003", "IND", 3333, "20260522", branch="BC03"),
            src("UTCAL0000004", "ACCT3004", "RES", 4444, "BAD-DATE", branch="BC04"),
        ],
        [
            action("UTCAL0000001", "ACCT3001", "RES", 1111, "20260523", "M03", branch="BC01"),
            action("UTCAL0000002", "ACCT3002", "COM", 2222, "20260523", "M09", branch="BC02"),
            action("UTCAL0000003", "ACCT3003", "IND", 3333, "20260523", "M12", branch="BC03"),
            action("UTCAL0000004", "ACCT3004", "RES", 4444, "20260523", "M03", branch="BC04"),
        ],
        ["20260520=OPEN", "20260521=CLOS", "BAD-DATE=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary["matched_amount_cents"] == 1111
    assert summary["unmatched_amount_cents"] == 9999
def test_latest_source_date_wins_when_multiple_rows_qualify():
    """Among eligible source rows sharing amount, the latest open source date should be consumed first."""
    compile_program()
    write_inputs(
        [
            src("UTLAT0000001", "ACCT7001", "RES", 2500, "20260801", branch="BG01"),
            src("UTLAT0000001", "ACCT7001", "RES", 2500, "20260805", branch="BG01"),
            src("UTLAT0000001", "ACCT7001", "RES", 2500, "20260803", branch="BG01"),
        ],
        [
            action("UTLAT0000001", "ACCT7001", "RS", 2500, "20260810", "M03", branch="BG01"),
            action("UTLAT0000001", "ACCT7001", "RS", 2500, "20260811", "M03", branch="BG01"),
        ],
        ["20260801=OPEN", "20260803=OPEN", "20260805=OPEN", "20260810=OPEN", "20260811=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["amount_cents"] for row in rows] == ["0000002500", "0000002500"]
    assert summary == {
        "matched_count": 2,
        "matched_amount_cents": 5000,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_earliest_source_input_row_wins_on_date_tie():
    """When source dates tie, the earliest source input row should be consumed first."""
    compile_program()
    write_inputs(
        [
            src("UTTIE0000001", "ACCT7101", "RES", 1500, "20260820", branch="BH01"),
            src("UTTIE0000001", "ACCT7101", "RES", 1500, "20260820", branch="BH01"),
            src("UTTIE0000001", "ACCT7101", "RES", 1500, "20260820", branch="BH01"),
        ],
        [
            action("UTTIE0000001", "ACCT7101", "RS", 1500, "20260821", "M03", branch="BH01"),
            action("UTTIE0000001", "ACCT7101", "RS", 1500, "20260822", "M03", branch="BH01"),
        ],
        ["20260820=OPEN", "20260821=OPEN", "20260822=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["amount_cents"] for row in rows] == ["0000001500", "0000001500"]
    assert summary == {
        "matched_count": 2,
        "matched_amount_cents": 3000,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
def test_second_action_stays_unmatched_after_latest_source_row_is_consumed():
    """Once the only eligible source row is consumed, a second duplicate action must remain unmatched."""
    compile_program()
    write_inputs(
        [src("UTLAT0000002", "ACCT7002", "RES", 1000, "20260805", branch="BG01")],
        [
            action("UTLAT0000002", "ACCT7002", "RS", 1000, "20260810", "M03", branch="BG01"),
            action("UTLAT0000002", "ACCT7002", "RS", 1000, "20260811", "M03", branch="BG01"),
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
        [src("UTALM3000001", "ACCT8001", "IND", 650, "20260901", branch="BH01")],
        [action("UTALM3000001", "ACCT8001", "IN", 650, "20260902", "M12", branch="BH01")],
        ["20260901=OPEN", "20260902=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["rate_code"] == "IND"
    assert summary["matched_amount_cents"] == 650


def test_calendar_open_is_case_insensitive():
    """Calendar state 'open' (lowercase) should be treated as OPEN."""
    compile_program()
    write_inputs(
        [src("UTCASE000001", "ACCT9001", "RES", 500, "20260401", branch="BX01")],
        [action("UTCASE000001", "ACCT9001", "RES", 500, "20260402", "M03", branch="BX01")],
        ["20260401=open"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["rate_code"] == "RES"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 500


def test_calendar_open_mixed_case_is_treated_as_open():
    """Calendar state 'OpEn' must match through true case-insensitive OPEN comparison."""
    compile_program()
    write_inputs(
        [src("UTCASE000002", "ACCT9002", "RES", 600, "20260402", branch="BX02")],
        [action("UTCASE000002", "ACCT9002", "RES", 600, "20260403", "M03", branch="BX02")],
        ["20260402=OpEn"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["rate_code"] == "RES"
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
