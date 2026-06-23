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


def test_closed_missing_and_malformed_calendar_dates_stay_unmatched():
    """Closed, missing, malformed, or unlisted source dates should never be treated as open."""
    compile_program()
    write_inputs(
        [
            src("AVCAL0000001", "ACCT3001", "PRM", 1111, "20260520", branch="BC01"),
            src("AVCAL0000002", "ACCT3002", "STD", 2222, "20260521", branch="BC02"),
            src("AVCAL0000003", "ACCT3003", "ECO", 3333, "20260522", branch="BC03"),
            src("AVCAL0000004", "ACCT3004", "PRM", 4444, "BAD-DATE", branch="BC04"),
        ],
        [
            action("AVCAL0000001", "ACCT3001", "PRM", 1111, "20260523", "A04", branch="BC01"),
            action("AVCAL0000002", "ACCT3002", "STD", 2222, "20260523", "A10", branch="BC02"),
            action("AVCAL0000003", "ACCT3003", "ECO", 3333, "20260523", "A18", branch="BC03"),
            action("AVCAL0000004", "ACCT3004", "PRM", 4444, "20260523", "A04", branch="BC04"),
        ],
        ["20260520=OPEN", "20260521=CLOS", "BAD-DATE=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary["matched_amount_cents"] == 1111
    assert summary["unmatched_amount_cents"] == 9999


def test_latest_source_date_wins_when_multiple_rows_qualify():
    """Latest source-date selection should affect later action eligibility."""
    compile_program()
    write_inputs(
        [
            src("AVLAT0000001", "ACCT7001", "PRM", 1000, "20260801", branch="BG01"),
            src("AVLAT0000001", "ACCT7001", "PRM", 1000, "20260803", branch="BG01"),
            src("AVLAT0000001", "ACCT7001", "PRM", 1000, "20260805", branch="BG01"),
        ],
        [
            action("AVLAT0000001", "ACCT7001", "PM", 1000, "20260810", "A04", branch="BG01"),
            action("AVLAT0000001", "ACCT7001", "PM", 1000, "20260804", "A04", branch="BG01"),
            action("AVLAT0000001", "ACCT7001", "PM", 1000, "20260802", "A04", branch="BG01"),
        ],
        ["20260801=OPEN", "20260803=OPEN", "20260805=OPEN", "20260810=OPEN", "20260811=OPEN", "20260812=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["hangar_class"] for row in rows] == ["PRM", "PRM", "PRM"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 3000,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_same_id_rows_are_consumed_independently_by_source_position():
    """Duplicate source rows sharing an id remain independently consumable by row position."""
    compile_program()
    write_inputs(
        [
            src("AVTIE0000001", "ACCT9001", "PRM", 500, "20261005", branch="BI01"),
            src("AVTIE0000001", "ACCT9001", "PRM", 500, "20261005", branch="BI01"),
        ],
        [
            action("AVTIE0000001", "ACCT9001", "PM", 500, "20261010", "A04", branch="BI01"),
            action("AVTIE0000001", "ACCT9001", "PM", 500, "20261011", "A04", branch="BI01"),
            action("AVTIE0000001", "ACCT9001", "PM", 500, "20261012", "A04", branch="BI01"),
        ],
        ["20261005=OPEN", "20261010=OPEN", "20261011=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
    assert summary == {
        "matched_count": 2,
        "matched_amount_cents": 1000,
        "unmatched_count": 1,
        "unmatched_amount_cents": 500,
    }


def test_second_action_stays_unmatched_after_latest_source_row_is_consumed():
    """Once the only eligible source row is consumed, a second duplicate action must remain unmatched."""
    compile_program()
    write_inputs(
        [src("AVLAT0000002", "ACCT7002", "PRM", 1000, "20260805", branch="BG01")],
        [
            action("AVLAT0000002", "ACCT7002", "PM", 1000, "20260810", "A04", branch="BG01"),
            action("AVLAT0000002", "ACCT7002", "PM", 1000, "20260811", "A04", branch="BG01"),
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
        [src("AVALM3000001", "ACCT8001", "ECO", 650, "20260901", branch="BH01")],
        [action("AVALM3000001", "ACCT8001", "EC", 650, "20260902", "A18", branch="BH01")],
        ["20260901=Open", "20260902=oPeN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["hangar_class"] == "ECO"
    assert summary["matched_amount_cents"] == 650
