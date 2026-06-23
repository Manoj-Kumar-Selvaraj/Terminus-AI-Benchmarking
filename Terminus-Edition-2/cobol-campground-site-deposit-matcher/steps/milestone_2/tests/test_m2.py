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

def test_legacy_aliases_match_and_emit_canonical_categories():
    """Legacy NT, R0, and CB action aliases must normalize to canonical source categories."""
    compile_program()
    write_inputs(
        [src("CGALIAS00001", "ACCT7001", "TNT", 1500, "20260701", branch="BG01"), src("CGALIAS00002", "ACCT7002", "RV", 2500, "20260701", branch="BG02"), src("CGALIAS00003", "ACCT7003", "CBN", 3500, "20260701", branch="BG03")],
        [action("CGALIAS00001", "ACCT7001", "NT", 1500, "20260702", "C02", branch="BG01"), action("CGALIAS00002", "ACCT7002", "R0", 2500, "20260702", "C06", branch="BG02"), action("CGALIAS00003", "ACCT7003", "CB", 3500, "20260702", "C10", branch="BG03")],
        ["20260701=CLOS"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["site_class"] for row in rows] == ["TNT", "RV", "CBN"]
    assert summary["matched_amount_cents"] == 7500

def test_alias_lookup_trims_and_case_folds_first_two_characters():
    """Padded and lowercase alias prefixes should match the same as canonical uppercase aliases."""
    compile_program()
    write_inputs(
        [src("CGCASEAL001", "ACCT7101", "TNT", 100, "20260701", branch="BH01"), src("CGCASEAL002", "ACCT7102", "RV", 200, "20260701", branch="BH02")],
        [action("CGCASEAL001", "ACCT7101", "ntx", 100, "20260702", "C02", branch="BH01"), action("CGCASEAL002", "ACCT7102", "r0 ", 200, "20260702", "C06", branch="BH02")],
        ["20260701=CLOS"],
    )
    rows, _ = run_program()
    assert [row["site_class"] for row in rows] == ["TNT", "RV"]

def test_unknown_alias_and_any_are_unmatched_in_milestone_2():
    """Only documented aliases are active in milestone 2; ANY and unknown prefixes are not wildcards."""
    compile_program()
    write_inputs(
        [src("CGUNKAL0001", "ACCT7201", "TNT", 100, "20260701", branch="BI01"), src("CGUNKAL0002", "ACCT7202", "RV", 200, "20260701", branch="BI02")],
        [action("CGUNKAL0001", "ACCT7201", "ZZ", 100, "20260702", "C02", branch="BI01"), action("CGUNKAL0002", "ACCT7202", "ANY", 200, "20260702", "C06", branch="BI02")],
        ["20260701=OPEN"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
    assert summary["unmatched_amount_cents"] == 300

def test_alias_does_not_bypass_amount_branch_reason_status_or_consumption():
    """Alias normalization must still honor all milestone 1 gates and one-time source consumption."""
    compile_program()
    write_inputs(
        [src("CGALGT00001", "ACCT7301", "TNT", 900, "20260701", branch="BJ01"), src("CGALGT00002", "ACCT7302", "RV", 1000, "20260701", status="X", branch="BJ02")],
        [action("CGALGT00001", "ACCT7301", "NT", 900, "20260702", "C02", branch="BJ01"), action("CGALGT00001", "ACCT7301", "NT", 900, "20260702", "C02", branch="BJ01"), action("CGALGT00001", "ACCT7301", "NT", 901, "20260702", "C02", branch="BJ01"), action("CGALGT00001", "ACCT7301", "NT", 900, "20260702", "BAD", branch="BJ01"), action("CGALGT00002", "ACCT7302", "R0", 1000, "20260702", "C06", branch="BJ02")],
        ["20260701=OPEN"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary["matched_amount_cents"] == 900
    assert summary["unmatched_count"] == 4

def test_m2_still_does_not_apply_calendar_gate():
    """Calendar validation is introduced later, so closed or missing calendar dates cannot block M2 matches."""
    compile_program()
    write_inputs(
        [src("CGM2NOCAL01", "ACCT7401", "CBN", 777, "20260707", branch="BK01")],
        [action("CGM2NOCAL01", "ACCT7401", "CB", 777, "20260708", "C10", branch="BK01")],
        ["20260707=CLOS"],
    )
    rows, _ = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["site_class"] == "CBN"

def test_milestone_1_output_contract_survives_alias_support():
    """Alias support must not change the report schema, action order, blank unmatched fields, or summary keys."""
    compile_program()
    write_inputs(
        [src("CGM2SCHEMA1", "ACCT7501", "TNT", 111, "20260701", branch="BL01")],
        [action("CGM2SCHEMA1", "ACCT7501", "NT", 111, "20260702", "C02", branch="BL01"), action("CGM2SCHEMA2", "ACCT7502", "CB", 222, "20260702", "C10", branch="BL02")],
        ["20260701=OPEN"],
    )
    rows, summary = run_program()
    assert REPORT.read_text().splitlines()[0] == "record_id,account,site_class,amount_cents,reason,status"
    assert [row["record_id"] for row in rows] == ["CGM2SCHEMA1", "CGM2SCHEMA2"]
    assert rows[1]["site_class"] == ""
    assert set(summary) == {"matched_count", "matched_amount_cents", "unmatched_count", "unmatched_amount_cents"}
