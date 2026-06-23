"""Tests for milestone 2 laundromat load credit alias normalization."""

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
    """Compile the COBOL program once for milestone 2 tests."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cobc", "-x", "-free", "-O2", "-o", str(BIN), str(SRC)], check=True, cwd=APP, timeout=60)


def write_inputs(source_lines, action_lines, calendar_lines):
    """Replace input files so outputs cannot be precomputed from shipped fixtures.

    Calendar lines are written for shared helper reuse; milestone 2 ignores
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


def test_legacy_aliases_match_and_emit_canonical_categories():
    """Legacy aliases should normalize to canonical categories before matching and in the report."""
    compile_program()
    write_inputs(
        [
            src("LDAL00000001", "ACCT5001", "SML", 1500, "20260701", branch="BE01"),
            src("LDAL00000002", "ACCT5002", "MDL", 2500, "20260701", branch="BE02"),
            src("LDAL00000003", "ACCT5003", "LGE", 3500, "20260701", branch="BE03"),
        ],
        [
            action("LDAL00000001", "ACCT5001", "SM", 1500, "20260702", "W02", branch="BE01"),
            action("LDAL00000002", "ACCT5002", "MD", 2500, "20260702", "W05", branch="BE02"),
            action("LDAL00000003", "ACCT5003", "LG", 3500, "20260702", "W09", branch="BE03"),
        ],
        ["20260701=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["machine_size"] for row in rows] == ["SML", "MDL", "LGE"]
    assert [row["source_date"] for row in rows] == ["20260701", "20260701", "20260701"]
    assert [row["reason"] for row in rows] == ["W02", "W05", "W09"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 7500,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_alias_normalization_trims_and_case_folds_before_matching():
    """Lowercase and mixed-case aliases in padded fixed-width fields should canonicalize before matching."""
    compile_program()
    write_inputs(
        [
            src("LDCASE000001", "ACCT7001", "SML", 1600, "20260703", branch="BG01"),
            src("LDCASE000002", "ACCT7002", "MDL", 2600, "20260703", branch="BG02"),
            src("LDCASE000003", "ACCT7003", "LGE", 3600, "20260703", branch="BG03"),
        ],
        [
            action("LDCASE000001", "ACCT7001", "sm", 1600, "20260704", "W02", branch="BG01"),
            action("LDCASE000002", "ACCT7002", "Md", 2600, "20260704", "W05", branch="BG02"),
            action("LDCASE000003", "ACCT7003", "lG", 3600, "20260704", "W09", branch="BG03"),
        ],
        ["20260703=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["machine_size"] for row in rows] == ["SML", "MDL", "LGE"]
    assert [row["source_date"] for row in rows] == ["20260703", "20260703", "20260703"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 7800,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_unknown_matching_alias_values_stay_unmatched_even_when_both_sides_agree():
    """A shared unknown machine_size code must not become eligible just because source and action match."""
    compile_program()
    write_inputs(
        [src("LDUNK0000001", "ACCT7101", "XL", 1700, "20260705", branch="BH01")],
        [action("LDUNK0000001", "ACCT7101", "XL", 1700, "20260706", "W02", branch="BH01")],
        ["20260705=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["machine_size"] == ""
    assert rows[0]["source_date"] == ""
    assert rows[0]["reason"] == "W02"
    assert summary == {
        "matched_count": 0,
        "matched_amount_cents": 0,
        "unmatched_count": 1,
        "unmatched_amount_cents": 1700,
    }


def test_duplicate_actions_do_not_reuse_the_same_source_row():
    """Only the first eligible action may consume a matching source row."""
    compile_program()
    write_inputs(
        [src("LDDUP0000001", "ACCT6001", "SML", 900, "20260710", branch="BF01")],
        [
            action("LDDUP0000001", "ACCT6001", "SML", 900, "20260711", "W02", branch="BF01"),
            action("LDDUP0000001", "ACCT6001", "SML", 900, "20260712", "W02", branch="BF01"),
        ],
        ["20260710=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert rows[1]["machine_size"] == ""
    assert rows[1]["source_date"] == ""
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 900,
        "unmatched_count": 1,
        "unmatched_amount_cents": 900,
    }


def test_earliest_action_wins_when_multiple_target_same_source():
    """First eligible action consumes the source; later ones stay unmatched even if they also qualify."""
    compile_program()
    write_inputs(
        [src("LDDUP0000002", "ACCT6002", "SML", 900, "20260710", branch="BF02")],
        [
            action("LDDUP0000002", "ACCT6002", "SM", 900, "20260711", "W02", branch="BF02"),
            action("LDDUP0000002", "ACCT6002", "SM", 900, "20260712", "W05", branch="BF02"),
        ],
        ["20260710=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["machine_size"] == "SML"
    assert rows[0]["source_date"] == "20260710"
    assert rows[0]["reason"] == "W02"
    assert rows[1]["status"] == "UNMATCHED"
    assert rows[1]["machine_size"] == ""
    assert rows[1]["source_date"] == ""
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 900,
        "unmatched_count": 1,
        "unmatched_amount_cents": 900,
    }
