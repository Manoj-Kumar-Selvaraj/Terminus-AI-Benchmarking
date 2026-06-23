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

def test_runtime_reason_config_is_authoritative_and_last_duplicate_wins():
    """Reasons are read from config at runtime; the last well-formed duplicate row controls eligibility."""
    compile_program()
    write_inputs(
        [src("CGREASON001", "ACCT9001", "TNT", 1000, "20261201", branch="BT01"), src("CGREASON002", "ACCT9002", "RV", 2000, "20261201", branch="BT02"), src("CGREASON003", "ACCT9003", "CBN", 3000, "20261201", branch="BT03")],
        [action("CGREASON001", "ACCT9001", "NT", 1000, "20261202", "C02", branch="BT01"), action("CGREASON002", "ACCT9002", "R0", 2000, "20261202", "C99", branch="BT02"), action("CGREASON003", "ACCT9003", "CB", 3000, "20261202", "C10", branch="BT03")],
        ["20261201=OPEN"],
        reason_lines=["code,eligible", "C02,N", "C99,y", "C10,Y", "C02,Y"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert summary["matched_count"] == 3

def test_removed_reason_is_not_hardcoded_as_eligible():
    """A reason that was historically eligible must be rejected if runtime config disables it."""
    compile_program()
    write_inputs(
        [src("CGREASON004", "ACCT9004", "TNT", 1000, "20261201", branch="BU01")],
        [action("CGREASON004", "ACCT9004", "NT", 1000, "20261202", "C06", branch="BU01")],
        ["20261201=OPEN"],
        reason_lines=["code,eligible", "C02,Y", "C06,N", "C10,Y"],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert summary["unmatched_amount_cents"] == 1000

def test_runtime_categories_enabled_and_disabled_values_are_authoritative():
    """Category config controls which canonical source categories are eligible."""
    compile_program()
    write_inputs(
        [src("CGCAT000001", "ACCT9101", "TNT", 1100, "20261201", branch="BV01"), src("CGCAT000002", "ACCT9102", "RV", 1200, "20261201", branch="BV02"), src("CGCAT000003", "ACCT9103", "CBN", 1300, "20261201", branch="BV03")],
        [action("CGCAT000001", "ACCT9101", "NT", 1100, "20261202", "C02", branch="BV01"), action("CGCAT000002", "ACCT9102", "R0", 1200, "20261202", "C06", branch="BV02"), action("CGCAT000003", "ACCT9103", "CB", 1300, "20261202", "C10", branch="BV03")],
        ["20261201=OPEN"],
        category_lines=["code,enabled,priority", "TNT,true,2", "RV,false,1", "CBN,TRUE,3"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert summary["matched_amount_cents"] == 2400

def test_any_matches_enabled_categories_and_emits_selected_canonical_category():
    """ANY action site_class can match any enabled source category but must report the chosen canonical source class."""
    compile_program()
    write_inputs(
        [src("CGANY000001", "ACCT9201", "TNT", 500, "20261201", branch="BW01"), src("CGANY000001", "ACCT9201", "CBN", 500, "20261203", branch="BW01")],
        [action("CGANY000001", "ACCT9201", "ANY", 500, "20261205", "C02", branch="BW01")],
        ["20261201=OPEN", "20261203=OPEN"],
        category_lines=["code,enabled,priority", "TNT,true,1", "CBN,true,2"],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["site_class"] == "CBN"
    assert summary["matched_count"] == 1

def test_any_same_date_uses_category_priority_before_source_order():
    """When ANY candidates share latest date, lower numeric category priority wins before source row order."""
    compile_program()
    write_inputs(
        [src("CGANYPRIO01", "ACCT9301", "TNT", 500, "20261210", branch="BX01"), src("CGANYPRIO01", "ACCT9301", "CBN", 500, "20261210", branch="BX01")],
        [action("CGANYPRIO01", "ACCT9301", "ANY", 500, "20261211", "C02", branch="BX01")],
        ["20261210=oPeN"],
        category_lines=["code,enabled,priority", "TNT,true,9", "CBN,true,1"],
    )
    rows, _ = run_program()
    assert rows[0]["site_class"] == "CBN"

def test_any_same_date_same_priority_uses_earliest_source_row():
    """If date and configured priority tie, ANY selection falls back to physical source row order."""
    compile_program()
    write_inputs(
        [src("CGANYROW001", "ACCT9401", "RV", 500, "20261210", branch="BY01"), src("CGANYROW001", "ACCT9401", "TNT", 500, "20261210", branch="BY01")],
        [action("CGANYROW001", "ACCT9401", "ANY", 500, "20261211", "C02", branch="BY01")],
        ["20261210=OPEN"],
        category_lines=["code,enabled,priority", "TNT,true,1", "RV,true,1"],
    )
    rows, _ = run_program()
    assert rows[0]["site_class"] == "RV"

def test_malformed_category_rows_do_not_create_eligible_categories():
    """Malformed enabled flags and blank category names are ignored instead of widening eligibility."""
    compile_program()
    write_inputs(
        [src("CGMALCAT001", "ACCT9501", "RV", 700, "20261201", branch="BZ01")],
        [action("CGMALCAT001", "ACCT9501", "R0", 700, "20261202", "C02", branch="BZ01")],
        ["20261201=OPEN"],
        category_lines=["code,enabled,priority", "RV,maybe,1", ",true,1", "TNT,true,2"],
    )
    rows, _ = run_program()
    assert rows[0]["status"] == "UNMATCHED"


def test_malformed_priority_ranks_after_numeric_priorities():
    """Malformed category priority ranks after numeric priorities when ANY selects among tied dates."""
    compile_program()
    write_inputs(
        [
            src("CGPRIO001", "ACCT9601", "TNT", 500, "20261210", branch="BA01"),
            src("CGPRIO001", "ACCT9601", "RV", 500, "20261210", branch="BA01"),
        ],
        [action("CGPRIO001", "ACCT9601", "ANY", 500, "20261211", "C02", branch="BA01")],
        ["20261210=OPEN"],
        category_lines=["code,enabled,priority", "TNT,true,abc", "RV,true,1"],
    )
    rows, _ = run_program()
    assert rows[0]["site_class"] == "RV"
