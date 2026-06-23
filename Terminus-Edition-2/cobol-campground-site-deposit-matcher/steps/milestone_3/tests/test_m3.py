"""Verifier tests for the campground site deposit reconciler."""
import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SRC = APP / "src" / "camp_deposit_reconcile.cbl"
BIN = APP / "build" / "camp_deposit_reconcile"
SOURCE = APP / "data" / "site_fees.dat"
ACTION = APP / "data" / "deposit_returns.dat"
CALENDAR = APP / "config" / "season_calendar.txt"
REASONS = APP / "config" / "reasons.csv"
CATEGORIES = APP / "config" / "categories.csv"
POLICIES = APP / "config" / "branch_policies.csv"
REPORT = APP / "out" / "camp_deposit_report.csv"
SUMMARY = APP / "out" / "camp_deposit_summary.txt"

def src(record_id, account, category, amount, date, status="G", branch="B001"):
    """Create one fixed-width source record from normalized field values."""
    amount_text = f"{amount:010d}" if isinstance(amount, int) else str(amount)[:10].ljust(10)
    return f"S{record_id:<12}{account:<8}{category:<3}{amount_text}{date:<8}{status:<1}{branch:<4}"

def action(record_id, account, category, amount, date, reason, branch="B001"):
    """Create one fixed-width action record from normalized field values."""
    amount_text = f"{amount:010d}" if isinstance(amount, int) else str(amount)[:10].ljust(10)
    return f"A{record_id:<12}{account:<8}{category:<3}{amount_text}{date:<8}{reason:<3}{branch:<4}"

def compile_program():
    """Compile the COBOL driver before each scenario so source patches are exercised."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cobc", "-x", "-free", "-O2", "-o", str(BIN), str(SRC)], check=True, cwd=APP, timeout=60)

def write_inputs(source_lines, action_lines, calendar_lines=None, reason_lines=None, category_lines=None, policy_lines=None):
    """Replace runtime data and config files with scenario-specific contents."""
    SOURCE.write_text("\n".join(source_lines) + "\n")
    ACTION.write_text("\n".join(action_lines) + "\n")
    CALENDAR.write_text("\n".join(calendar_lines if calendar_lines is not None else ["20260101=OPEN"]) + "\n")
    REASONS.write_text("\n".join(reason_lines if reason_lines is not None else ["code,eligible", "C02,Y", "C06,Y", "C10,Y"]) + "\n")
    CATEGORIES.write_text("\n".join(category_lines if category_lines is not None else ["code,enabled,priority", "TNT,true,2", "RV,true,3", "CBN,true,1"]) + "\n")
    POLICIES.write_text("\n".join(policy_lines if policy_lines is not None else ["branch,site_class,max_deposit_cents,enabled,allow_any", "B001,TNT,999999,true,true", "B001,RV,999999,true,true", "B001,CBN,999999,true,true"]) + "\n")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("stale report must be replaced\n")
    SUMMARY.write_text("stale summary must be replaced\n")

def run_program():
    """Run the compiled reconciler and parse report and summary outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {}
    for raw in SUMMARY.read_text().splitlines():
        key, value = raw.split("=", 1)
        summary[key] = int(value)
    return rows, summary

def test_calendar_closed_missing_unlisted_and_malformed_source_dates_reject():
    """Calendar validation rejects closed, missing, unlisted, nonnumeric, and malformed source dates."""
    compile_program()
    write_inputs(
        [src("CGCAL000001", "ACCT8001", "TNT", 1111, "20260801", branch="BM01"), src("CGCAL000002", "ACCT8002", "RV", 2222, "20260802", branch="BM02"), src("CGCAL000003", "ACCT8003", "CBN", 3333, "20260803", branch="BM03"), src("CGCAL000004", "ACCT8004", "TNT", 4444, "BAD-DATE", branch="BM04")],
        [action("CGCAL000001", "ACCT8001", "NT", 1111, "20260805", "C02", branch="BM01"), action("CGCAL000002", "ACCT8002", "R0", 2222, "20260805", "C06", branch="BM02"), action("CGCAL000003", "ACCT8003", "CB", 3333, "20260805", "C10", branch="BM03"), action("CGCAL000004", "ACCT8004", "NT", 4444, "20260805", "C02", branch="BM04")],
        ["20260801=OPEN", "20260802=CLOS", "BAD-DATE=OPEN", "# comment", ""],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary["matched_amount_cents"] == 1111
    assert summary["unmatched_amount_cents"] == 9999

def test_calendar_open_state_is_case_insensitive_for_exotic_casing():
    """OPEN state comparison must handle mixed casing beyond only OPEN/open."""
    compile_program()
    write_inputs(
        [src("CGCASE00001", "ACCT8101", "TNT", 500, "20260901", branch="BN01"), src("CGCASE00002", "ACCT8102", "RV", 600, "20260902", branch="BN02")],
        [action("CGCASE00001", "ACCT8101", "NT", 500, "20260903", "C02", branch="BN01"), action("CGCASE00002", "ACCT8102", "R0", 600, "20260903", "C06", branch="BN02")],
        ["20260901=oPeN", "20260902=opEN"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert summary["matched_amount_cents"] == 1100

def test_latest_source_date_wins_and_makes_earlier_candidate_available_later():
    """When two unused candidates qualify, the first action must consume the latest source date."""
    compile_program()
    write_inputs(
        [src("CGLATEST001", "ACCT8201", "TNT", 500, "20260801", branch="BO01"), src("CGLATEST001", "ACCT8201", "TNT", 500, "20260805", branch="BO01")],
        [action("CGLATEST001", "ACCT8201", "NT", 500, "20260810", "C02", branch="BO01"), action("CGLATEST001", "ACCT8201", "NT", 500, "20260803", "C02", branch="BO01")],
        ["20260801=OPEN", "20260805=OPEN"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert summary["matched_count"] == 2

def test_same_source_date_tie_uses_earliest_source_row_and_consumption_by_position():
    """Same-date duplicate rows must be consumed by physical source row position."""
    compile_program()
    write_inputs(
        [src("CGTIEM30001", "ACCT8301", "TNT", 500, "20260805", branch="BP01"), src("CGTIEM30001", "ACCT8301", "TNT", 500, "20260805", branch="BP01")],
        [action("CGTIEM30001", "ACCT8301", "NT", 500, "20260810", "C02", branch="BP01"), action("CGTIEM30001", "ACCT8301", "NT", 500, "20260810", "C02", branch="BP01"), action("CGTIEM30001", "ACCT8301", "NT", 500, "20260810", "C02", branch="BP01")],
        ["20260805=OPEN"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
    assert summary["matched_count"] == 2

def test_action_date_closed_calendar_entry_does_not_block_when_source_is_open():
    """M3 calendar checks the source date, not the action date."""
    compile_program()
    write_inputs(
        [src("CGACTCLOSE1", "ACCT8401", "CBN", 900, "20261001", branch="BQ01")],
        [action("CGACTCLOSE1", "ACCT8401", "CB", 900, "20261002", "C10", branch="BQ01")],
        ["20261001=OPEN", "20261002=CLOS"],
    )
    rows, _ = run_program()
    assert rows[0]["status"] == "MATCHED"

def test_invalid_action_dates_are_unmatched_and_do_not_consume_sources():
    """Action dates must be numeric and on or after the source date before source rows are consumed."""
    compile_program()
    write_inputs(
        [src("CGBADDATE01", "ACCT8501", "TNT", 300, "20261101", branch="BR01")],
        [action("CGBADDATE01", "ACCT8501", "NT", 300, "BAD-DATE", "C02", branch="BR01"), action("CGBADDATE01", "ACCT8501", "NT", 300, "20261102", "C02", branch="BR01")],
        ["20261101=OPEN"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert summary["matched_count"] == 1

def test_aliases_and_milestone_one_gates_still_apply_with_calendar():
    """Aliases, branch, amount, status, and reason gates remain active under calendar enforcement."""
    compile_program()
    write_inputs(
        [src("CGM3CARRY01", "ACCT8601", "CBN", 650, "20260901", branch="BS01"), src("CGM3CARRY02", "ACCT8602", "RV", 750, "20260901", status="X", branch="BS02")],
        [action("CGM3CARRY01", "ACCT8601", "CB", 650, "20260902", "C10", branch="BS01"), action("CGM3CARRY01", "ACCT8601", "CB", 651, "20260902", "C10", branch="BS01"), action("CGM3CARRY02", "ACCT8602", "R0", 750, "20260902", "C06", branch="BS02")],
        ["20260901=OPEN"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary["unmatched_count"] == 2
