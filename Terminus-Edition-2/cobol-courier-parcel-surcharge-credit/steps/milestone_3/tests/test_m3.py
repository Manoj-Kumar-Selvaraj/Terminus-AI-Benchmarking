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


def test_closed_missing_and_malformed_calendar_dates_stay_unmatched():
    """Closed, missing, malformed, unlisted, and mixed-case calendar dates should be handled correctly."""
    compile_program()
    write_inputs(
        [
            src("CPCAL0000001", "ACCT3001", "STD", 1111, "20260520", branch="BC01"),
            src("CPCAL0000002", "ACCT3002", "NXT", 2222, "20260521", branch="BC02"),
            src("CPCAL0000003", "ACCT3003", "SAM", 3333, "20260522", branch="BC03"),
            src("CPCAL0000004", "ACCT3004", "STD", 4444, "BAD-DATE", branch="BC04"),
        ],
        [
            action("CPCAL0000001", "ACCT3001", "STD", 1111, "20260523", "P03", branch="BC01"),
            action("CPCAL0000002", "ACCT3002", "NXT", 2222, "20260523", "P08", branch="BC02"),
            action("CPCAL0000003", "ACCT3003", "SAM", 3333, "20260523", "P21", branch="BC03"),
            action("CPCAL0000004", "ACCT3004", "STD", 4444, "20260523", "P03", branch="BC04"),
        ],
        ["20260520=Open", "20260521=CLOS", "BAD-DATE=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert [row["service_tier"] for row in rows] == ["STD", "", "", ""]
    assert [row["reason"] for row in rows] == ["P03", "P08", "P21", "P03"]
    assert summary["matched_amount_cents"] == 1111
    assert summary["unmatched_amount_cents"] == 9999


def test_latest_source_date_wins_when_multiple_rows_qualify():
    """Selecting the latest row must preserve an older row for an earlier-dated action."""
    compile_program()
    write_inputs(
        [
            src("CPLAT0000001", "ACCT7001", "STD", 1000, "20260801", branch="BG01"),
            src("CPLAT0000001", "ACCT7001", "STD", 1000, "20260805", branch="BG01"),
        ],
        [
            action("CPLAT0000001", "ACCT7001", "ST", 1000, "20260810", "P03", branch="BG01"),
            action("CPLAT0000001", "ACCT7001", "ST", 1000, "20260802", "P08", branch="BG01"),
        ],
        ["20260801=OPEN", "20260805=oPeN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["reason"] for row in rows] == ["P03", "P08"]
    assert [row["service_tier"] for row in rows] == ["STD", "STD"]
    assert summary == {
        "matched_count": 2,
        "matched_amount_cents": 2000,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_second_action_stays_unmatched_after_latest_source_row_is_consumed():
    """Once the only eligible source row is consumed, a second duplicate action must remain unmatched."""
    compile_program()
    write_inputs(
        [src("CPLAT0000002", "ACCT7002", "STD", 1000, "20260805", branch="BG01")],
        [
            action("CPLAT0000002", "ACCT7002", "ST", 1000, "20260810", "P03", branch="BG01"),
            action("CPLAT0000002", "ACCT7002", "ST", 1000, "20260811", "P03", branch="BG01"),
        ],
        ["20260805=OPEN", "20260810=OPEN", "20260811=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert [row["service_tier"] for row in rows] == ["STD", ""]
    assert [row["reason"] for row in rows] == ["P03", "P03"]
    assert summary["matched_count"] == 1
    assert summary["unmatched_amount_cents"] == 1000


def test_aliases_still_work_under_calendar_gates():
    """Alias normalization must still apply when calendar gates are enforced."""
    compile_program()
    write_inputs(
        [src("CPALM3000001", "ACCT8001", "SAM", 650, "20260901", branch="BH01")],
        [action("CPALM3000001", "ACCT8001", "SM", 650, "20260902", "P21", branch="BH01")],
        ["20260901=OPEN", "20260902=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["service_tier"] == "SAM"
    assert rows[0]["reason"] == "P21"
    assert summary["matched_amount_cents"] == 650


def test_calendar_open_state_is_case_insensitive_across_multiple_variants():
    """Several mixed-case OPEN spellings must all make valid source dates eligible."""
    compile_program()
    write_inputs(
        [
            src("CPCAS0000001", "ACCT8101", "STD", 101, "20260910", branch="BI01"),
            src("CPCAS0000002", "ACCT8102", "NXT", 202, "20260911", branch="BI02"),
            src("CPCAS0000003", "ACCT8103", "SAM", 303, "20260912", branch="BI03"),
        ],
        [
            action("CPCAS0000001", "ACCT8101", "ST", 101, "20260913", "P03", branch="BI01"),
            action("CPCAS0000002", "ACCT8102", "NX", 202, "20260913", "P08", branch="BI02"),
            action("CPCAS0000003", "ACCT8103", "SM", 303, "20260913", "P21", branch="BI03"),
        ],
        ["20260910=OpEn", "20260911=opeN", "20260912=OPEn"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["service_tier"] for row in rows] == ["STD", "NXT", "SAM"]
    assert summary["matched_amount_cents"] == 606


def test_calendar_eligibility_does_not_bypass_source_status():
    """An OPEN source date must not make a non-S source row eligible."""
    compile_program()
    write_inputs(
        [src("CPSTS0000001", "ACCT8201", "STD", 700, "20260920", status="X", branch="BJ01")],
        [action("CPSTS0000001", "ACCT8201", "ST", 700, "20260921", "P03", branch="BJ01")],
        ["20260920=oPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["service_tier"] == ""
    assert summary["matched_count"] == 0
    assert summary["unmatched_amount_cents"] == 700
