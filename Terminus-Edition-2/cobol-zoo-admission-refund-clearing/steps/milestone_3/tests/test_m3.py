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


def test_closed_missing_and_malformed_calendar_dates_stay_unmatched():
    """Closed, missing, malformed, or unlisted source dates should never be treated as open."""
    compile_program()
    write_inputs(
        [
            src("ZOCAL0000001", "ACCT3001", "ADT", 1111, "20260520", branch="BC01"),
            src("ZOCAL0000002", "ACCT3002", "CHD", 2222, "20260521", branch="BC02"),
            src("ZOCAL0000003", "ACCT3003", "SEN", 3333, "20260522", branch="BC03"),
            src("ZOCAL0000004", "ACCT3004", "ADT", 4444, "BAD-DATE", branch="BC04"),
        ],
        [
            action("ZOCAL0000001", "ACCT3001", "ADT", 1111, "20260523", "Z02", branch="BC01"),
            action("ZOCAL0000002", "ACCT3002", "CHD", 2222, "20260523", "Z05", branch="BC02"),
            action("ZOCAL0000003", "ACCT3003", "SEN", 3333, "20260523", "Z14", branch="BC03"),
            action("ZOCAL0000004", "ACCT3004", "ADT", 4444, "20260523", "Z02", branch="BC04"),
        ],
        ["20260520=OPEN", "20260521=CLOS", "BAD-DATE=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary["matched_amount_cents"] == 1111
    assert summary["unmatched_amount_cents"] == 9999


def test_latest_date_wins_same_amount():
    """Latest open source date beats earlier when all other fields match."""
    compile_program()
    write_inputs(
        [
            src("ZOTB00000001", "ACCT0001", "ADT", 500, "20260801", branch="BG01"),
            src("ZOTB00000001", "ACCT0001", "ADT", 500, "20260805", branch="BG01"),
        ],
        [
            action("ZOTB00000001", "ACCT0001", "AD", 500, "20260810", "Z02", branch="BG01"),
            action("ZOTB00000001", "ACCT0001", "AD", 500, "20260810", "Z02", branch="BG01"),
        ],
        ["20260801=OPEN", "20260805=OPEN", "20260810=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert summary == {
        "matched_count": 2,
        "matched_amount_cents": 1000,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_same_source_date_tie_prefers_earliest_input_row():
    """When source dates tie, the earliest source input row must be consumed first."""
    compile_program()
    write_inputs(
        [
            src("ZOTIE0000001", "ACCT7101", "ADT", 500, "20260805", branch="BG01"),
            src("ZOTIE0000001", "ACCT7101", "ADT", 500, "20260805", branch="BG01"),
        ],
        [
            action("ZOTIE0000001", "ACCT7101", "AD", 500, "20260810", "Z02", branch="BG01"),
            action("ZOTIE0000001", "ACCT7101", "AD", 500, "20260810", "Z02", branch="BG01"),
        ],
        ["20260805=OPEN", "20260810=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert summary == {
        "matched_count": 2,
        "matched_amount_cents": 1000,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_duplicate_record_id_rows_are_consumed_by_position():
    """Two source rows with the same record id must be independently consumable by amount."""
    compile_program()
    write_inputs(
        [
            src("ZOPOS000001", "ACCT9001", "ADT", 500, "20260810", branch="BX01"),
            src("ZOPOS000001", "ACCT9001", "ADT", 700, "20260810", branch="BX01"),
        ],
        [
            action("ZOPOS000001", "ACCT9001", "ADT", 500, "20260811", "Z02", branch="BX01"),
            action("ZOPOS000001", "ACCT9001", "ADT", 700, "20260811", "Z02", branch="BX01"),
        ],
        ["20260810=OPEN", "20260811=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert summary == {
        "matched_count": 2,
        "matched_amount_cents": 1200,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_calendar_open_state_is_case_insensitive():
    """Mixed-case OPEN calendar states must still allow eligible source dates."""
    compile_program()
    write_inputs(
        [src("ZOCASE000001", "ACCT9002", "ADT", 500, "20260901", branch="BX02")],
        [action("ZOCASE000001", "ACCT9002", "AD", 500, "20260902", "Z02", branch="BX02")],
        ["20260901=Open", "20260902=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["ticket_tier"] == "ADT"
    assert summary["matched_count"] == 1



def test_second_action_stays_unmatched_after_latest_source_row_is_consumed():
    """Once the only eligible source row is consumed, a second duplicate action must remain unmatched."""
    compile_program()
    write_inputs(
        [src("ZOLAT0000002", "ACCT7002", "ADT", 1000, "20260805", branch="BG01")],
        [
            action("ZOLAT0000002", "ACCT7002", "AD", 1000, "20260810", "Z02", branch="BG01"),
            action("ZOLAT0000002", "ACCT7002", "AD", 1000, "20260811", "Z02", branch="BG01"),
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
        [src("ZOALM3000001", "ACCT8001", "SEN", 650, "20260901", branch="BH01")],
        [action("ZOALM3000001", "ACCT8001", "SE", 650, "20260902", "Z14", branch="BH01")],
        ["20260901=OPEN", "20260902=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["ticket_tier"] == "SEN"
    assert summary["matched_amount_cents"] == 650
