"""Tests for milestone 3 laundromat load credit calendar and latest-date selection."""

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
    """Compile the COBOL program once for milestone 3 tests."""
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
            src("LDCAL0000001", "ACCT3001", "SML", 1111, "20260520", branch="BC01"),
            src("LDCAL0000002", "ACCT3002", "MDL", 2222, "20260521", branch="BC02"),
            src("LDCAL0000003", "ACCT3003", "LGE", 3333, "20260522", branch="BC03"),
            src("LDCAL0000004", "ACCT3004", "SML", 4444, "BAD-DATE", branch="BC04"),
        ],
        [
            action("LDCAL0000001", "ACCT3001", "SML", 1111, "20260523", "W02", branch="BC01"),
            action("LDCAL0000002", "ACCT3002", "MDL", 2222, "20260523", "W05", branch="BC02"),
            action("LDCAL0000003", "ACCT3003", "LGE", 3333, "20260523", "W09", branch="BC03"),
            action("LDCAL0000004", "ACCT3004", "SML", 4444, "20260523", "W02", branch="BC04"),
        ],
        ["20260520=OPEN", "20260521=CLOS", "BAD-DATE=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert [row["machine_size"] for row in rows[1:]] == ["", "", ""]
    assert [row["source_date"] for row in rows[1:]] == ["", "", ""]
    assert summary["matched_amount_cents"] == 1111
    assert summary["unmatched_amount_cents"] == 9999


def test_latest_source_date_wins_with_distinct_amounts():
    """Latest open source date must win even when an earlier row appears first in the file."""
    compile_program()
    write_inputs(
        [
            src("LDTB00000001", "ACCT0001", "SML", 500, "20260801", branch="BG01"),
            src("LDTB00000001", "ACCT0001", "SML", 800, "20260805", branch="BG01"),
        ],
        [
            action("LDTB00000001", "ACCT0001", "SM", 800, "20260810", "W02", branch="BG01"),
            action("LDTB00000001", "ACCT0001", "SM", 500, "20260810", "W02", branch="BG01"),
        ],
        ["20260801=OPEN", "20260805=OPEN", "20260810=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["amount_cents"] for row in rows] == ["0000000800", "0000000500"]
    assert [row["source_date"] for row in rows] == ["20260805", "20260801"]
    assert summary == {
        "matched_count": 2,
        "matched_amount_cents": 1300,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_latest_source_date_wins_when_amounts_match():
    """When multiple qualified source rows share the same amount, the latest open source date must be selected."""
    compile_program()
    write_inputs(
        [
            src("LDSAM0000001", "ACCT0002", "SML", 800, "20260801", branch="BG01"),
            src("LDSAM0000001", "ACCT0002", "SML", 800, "20260805", branch="BG01"),
        ],
        [action("LDSAM0000001", "ACCT0002", "SM", 800, "20260810", "W02", branch="BG01")],
        ["20260801=OPEN", "20260805=OPEN", "20260810=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["amount_cents"] == "0000000800"
    assert rows[0]["source_date"] == "20260805"
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 800,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_latest_date_selection_is_observable_through_consumption():
    """A single action must bind to the latest-dated source row, leaving the earlier row unused."""
    compile_program()
    write_inputs(
        [
            src("LDLAT0000003", "ACCT7003", "SML", 800, "20260801", branch="BG01"),
            src("LDLAT0000003", "ACCT7003", "SML", 800, "20260805", branch="BG01"),
        ],
        [action("LDLAT0000003", "ACCT7003", "SM", 800, "20260810", "W02", branch="BG01")],
        ["20260801=OPEN", "20260805=OPEN", "20260810=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["amount_cents"] == "0000000800"
    assert rows[0]["source_date"] == "20260805"
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 800,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_same_source_date_tie_prefers_earliest_input_row():
    """When source dates tie, the earliest source input row must be consumed first."""
    compile_program()
    write_inputs(
        [
            src("LDTIE0000001", "ACCT7101", "SML", 500, "20260805", branch="BG01"),
            src("LDTIE0000001", "ACCT7101", "SML", 500, "20260805", branch="BG01"),
        ],
        [
            action("LDTIE0000001", "ACCT7101", "SM", 500, "20260810", "W02", branch="BG01"),
            action("LDTIE0000001", "ACCT7101", "SM", 500, "20260810", "W02", branch="BG01"),
        ],
        ["20260805=OPEN", "20260810=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["source_date"] for row in rows] == ["20260805", "20260805"]
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
            src("LDPOS000001", "ACCT9001", "SML", 500, "20260810", branch="BX01"),
            src("LDPOS000001", "ACCT9001", "SML", 700, "20260810", branch="BX01"),
        ],
        [
            action("LDPOS000001", "ACCT9001", "SML", 500, "20260811", "W02", branch="BX01"),
            action("LDPOS000001", "ACCT9001", "SML", 700, "20260811", "W02", branch="BX01"),
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
        [src("LDCASE000001", "ACCT9002", "SML", 500, "20260901", branch="BX02")],
        [action("LDCASE000001", "ACCT9002", "SM", 500, "20260902", "W02", branch="BX02")],
        ["20260901=Open", "20260902=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["machine_size"] == "SML"
    assert rows[0]["source_date"] == "20260901"
    assert summary["matched_count"] == 1


def test_calendar_parser_trims_whitespace_around_dates_and_states():
    """Calendar entries with surrounding spaces around date, equals, and state still mark dates open."""
    compile_program()
    write_inputs(
        [src("LDSPACE00001", "ACCT9101", "SML", 750, "20260903", branch="BX03")],
        [action("LDSPACE00001", "ACCT9101", "sm", 750, "20260904", "W02", branch="BX03")],
        ["  20260903 = Open  ", "20260904=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["machine_size"] == "SML"
    assert rows[0]["source_date"] == "20260903"
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 750,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }



def test_second_action_stays_unmatched_after_latest_source_row_is_consumed():
    """Once the only eligible source row is consumed, a second duplicate action must remain unmatched."""
    compile_program()
    write_inputs(
        [src("LDLAT0000002", "ACCT7002", "SML", 1000, "20260805", branch="BG01")],
        [
            action("LDLAT0000002", "ACCT7002", "SM", 1000, "20260810", "W02", branch="BG01"),
            action("LDLAT0000002", "ACCT7002", "SM", 1000, "20260811", "W02", branch="BG01"),
        ],
        ["20260805=OPEN", "20260810=OPEN", "20260811=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert rows[0]["source_date"] == "20260805"
    assert rows[1]["machine_size"] == ""
    assert rows[1]["source_date"] == ""
    assert summary["matched_count"] == 1
    assert summary["unmatched_amount_cents"] == 1000


def test_aliases_still_work_under_calendar_gates():
    """Alias normalization must still apply when calendar gates are enforced."""
    compile_program()
    write_inputs(
        [src("LDALM3000001", "ACCT8001", "LGE", 650, "20260901", branch="BH01")],
        [action("LDALM3000001", "ACCT8001", "LG", 650, "20260902", "W09", branch="BH01")],
        ["20260901=OPEN", "20260902=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["machine_size"] == "LGE"
    assert rows[0]["source_date"] == "20260901"
    assert summary["matched_amount_cents"] == 650
