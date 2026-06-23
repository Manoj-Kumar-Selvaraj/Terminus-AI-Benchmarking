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

def test_branch_policy_exact_key_and_amount_cap_allow_match():
    """An enabled exact branch/category policy with sufficient max amount allows an otherwise valid match."""
    compile_program()
    write_inputs(
        [src("CGPOL000001", "ACCTA001", "TNT", 2500, "20270101", branch="PA01")],
        [action("CGPOL000001", "ACCTA001", "NT", 2500, "20270102", "C02", branch="PA01")],
        ["20270101=OPEN"],
        policy_lines=["branch,site_class,max_deposit_cents,enabled,allow_any", "PA01,TNT,2500,true,true"],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert summary["matched_amount_cents"] == 2500

def test_missing_wrong_disabled_and_over_limit_policies_reject_without_consuming_sources():
    """Policy failures are candidate-ineligible and must not consume source rows."""
    compile_program()
    write_inputs(
        [src("CGPOL000002", "ACCTA002", "TNT", 1000, "20270101", branch="PA02"), src("CGPOL000003", "ACCTA003", "RV", 2000, "20270101", branch="PA03"), src("CGPOL000004", "ACCTA004", "CBN", 3000, "20270101", branch="PA04")],
        [action("CGPOL000002", "ACCTA002", "NT", 1000, "20270102", "C02", branch="ZZ99"), action("CGPOL000003", "ACCTA003", "R0", 2000, "20270102", "C06", branch="PA03"), action("CGPOL000004", "ACCTA004", "CB", 3000, "20270102", "C10", branch="PA04")],
        ["20270101=OPEN"],
        policy_lines=["branch,site_class,max_deposit_cents,enabled,allow_any", "PA03,RV,9999,false,true", "PA04,CBN,2999,true,true"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary["unmatched_amount_cents"] == 6000

def test_last_well_formed_duplicate_policy_row_is_authoritative():
    """Duplicate branch/category policy keys use the last well-formed row, including disabling rows."""
    compile_program()
    write_inputs(
        [src("CGPOLDUP001", "ACCTA101", "TNT", 1000, "20270101", branch="PB01"), src("CGPOLDUP002", "ACCTA102", "RV", 1000, "20270101", branch="PB02")],
        [action("CGPOLDUP001", "ACCTA101", "NT", 1000, "20270102", "C02", branch="PB01"), action("CGPOLDUP002", "ACCTA102", "R0", 1000, "20270102", "C06", branch="PB02")],
        ["20270101=OPEN"],
        policy_lines=["branch,site_class,max_deposit_cents,enabled,allow_any", "PB01,TNT,5000,true,true", "PB01,TNT,5000,false,true", "PB02,RV,10,true,true", "PB02,RV,5000,true,true"],
    )
    rows, _ = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]

def test_any_requires_allow_any_true_and_filters_candidates_before_ranking():
    """ANY candidates blocked by policy must be skipped so the next eligible source can match."""
    compile_program()
    write_inputs(
        [src("CGPOLANY001", "ACCTA201", "CBN", 500, "20270105", branch="PC01"), src("CGPOLANY001", "ACCTA201", "TNT", 500, "20270104", branch="PC01")],
        [action("CGPOLANY001", "ACCTA201", "ANY", 500, "20270106", "C02", branch="PC01")],
        ["20270104=OPEN", "20270105=OPEN"],
        category_lines=["code,enabled,priority", "TNT,true,1", "CBN,true,2"],
        policy_lines=["branch,site_class,max_deposit_cents,enabled,allow_any", "PC01,CBN,9999,true,false", "PC01,TNT,9999,true,true"],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["site_class"] == "TNT"
    assert summary["matched_count"] == 1

def test_policy_does_not_bypass_reason_category_calendar_or_status_gates():
    """A permissive policy cannot make earlier failed gates eligible."""
    compile_program()
    write_inputs(
        [src("CGPOLGATE01", "ACCTA301", "TNT", 1000, "20270101", status="X", branch="PD01"), src("CGPOLGATE02", "ACCTA302", "RV", 1000, "20270102", branch="PD02"), src("CGPOLGATE03", "ACCTA303", "CBN", 1000, "20270103", branch="PD03")],
        [action("CGPOLGATE01", "ACCTA301", "NT", 1000, "20270104", "C02", branch="PD01"), action("CGPOLGATE02", "ACCTA302", "R0", 1000, "20270104", "BAD", branch="PD02"), action("CGPOLGATE03", "ACCTA303", "CB", 1000, "20270104", "C10", branch="PD03")],
        ["20270101=OPEN", "20270102=OPEN", "20270103=CLOS"],
        policy_lines=["branch,site_class,max_deposit_cents,enabled,allow_any", "PD01,TNT,9999,true,true", "PD02,RV,9999,true,true", "PD03,CBN,9999,true,true"],
    )
    rows, _ = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]

def test_invalid_policy_rows_are_ignored_rather_than_widening_eligibility():
    """Malformed booleans and non-positive or nonnumeric caps do not create usable policies."""
    compile_program()
    write_inputs(
        [src("CGPOLBAD001", "ACCTA401", "TNT", 1000, "20270101", branch="PE01"), src("CGPOLBAD002", "ACCTA402", "RV", 1000, "20270101", branch="PE02")],
        [action("CGPOLBAD001", "ACCTA401", "NT", 1000, "20270102", "C02", branch="PE01"), action("CGPOLBAD002", "ACCTA402", "R0", 1000, "20270102", "C06", branch="PE02")],
        ["20270101=OPEN"],
        policy_lines=["branch,site_class,max_deposit_cents,enabled,allow_any", "PE01,TNT,NaN,true,true", "PE02,RV,0,true,true", "PE02,RV,5000,maybe,true"],
    )
    rows, _ = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]

def test_policy_blocked_first_action_does_not_consume_source_needed_by_later_valid_action():
    """If a row is policy-blocked, the same source remains available for a later policy-allowed action."""
    compile_program()
    write_inputs(
        [src("CGPOLNOUSE1", "ACCTA501", "TNT", 1000, "20270101", branch="PF01")],
        [action("CGPOLNOUSE1", "ACCTA501", "ANY", 1000, "20270102", "C02", branch="PF01"), action("CGPOLNOUSE1", "ACCTA501", "NT", 1000, "20270102", "C02", branch="PF01")],
        ["20270101=OPEN"],
        policy_lines=["branch,site_class,max_deposit_cents,enabled,allow_any", "PF01,TNT,9999,true,false"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert summary["matched_count"] == 1
