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

def test_core_exact_gates_all_canonical_classes_match():
    """Full identifiers, canonical classes, eligible reasons, status, branch, and date ordering gate matches."""
    compile_program()
    write_inputs(
        [src("CGM100000001", "ACCT1001", "TNT", 1200, "20260601", branch="BR01"), src("CGM100000002", "ACCT1002", "RV", 3400, "20260601", branch="BR02"), src("CGM100000003", "ACCT1003", "CBN", 5600, "20260601", branch="BR03")],
        [action("CGM100000001", "ACCT1001", "TNT", 1200, "20260602", "C02", branch="BR01"), action("CGM100000002", "ACCT1002", "RV", 3400, "20260602", "C06", branch="BR02"), action("CGM100000003", "ACCT1003", "CBN", 5600, "20260602", "C10", branch="BR03")],
        ["20260601=CLOS"],
    )
    rows, summary = run_program()
    assert REPORT.read_text().splitlines()[0] == "record_id,account,site_class,amount_cents,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["site_class"] for row in rows] == ["TNT", "RV", "CBN"]
    assert summary == {"matched_count": 3, "matched_amount_cents": 10200, "unmatched_count": 0, "unmatched_amount_cents": 0}

def test_m1_does_not_apply_calendar_closed_or_missing_source_dates():
    """Milestone 1 has no calendar gate; closed or absent calendar dates must not block exact matches."""
    compile_program()
    write_inputs(
        [src("CGNOCAL00001", "ACCT9999", "TNT", 500, "20260601", branch="BZ01"), src("CGNOCAL00002", "ACCT9998", "RV", 700, "20260603", branch="BZ02")],
        [action("CGNOCAL00001", "ACCT9999", "TNT", 500, "20260602", "C02", branch="BZ01"), action("CGNOCAL00002", "ACCT9998", "RV", 700, "20260604", "C06", branch="BZ02")],
        ["20260601=CLOS"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert summary["matched_amount_cents"] == 1200

def test_full_identifier_prefix_collision_and_record_type_are_handled():
    """The record type byte must not appear in output and prefix-matched record ids must not collide."""
    compile_program()
    write_inputs(
        [src("CGPREFIX0001", "ACCT2001", "TNT", 1000, "20260601", branch="BP01"), src("CGPREFIX0002", "ACCT2001", "TNT", 1000, "20260601", branch="BP01")],
        [action("CGPREFIX0001", "ACCT2001", "TNT", 1000, "20260602", "C02", branch="BP01"), action("CGPREFIX000", "ACCT2001", "TNT", 1000, "20260602", "C02", branch="BP01")],
        ["20260601=OPEN"],
    )
    rows, summary = run_program()
    assert rows[0]["record_id"] == "CGPREFIX0001"
    assert rows[0]["record_id"].startswith("S") is False
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert summary["unmatched_count"] == 1

def test_every_non_calendar_gate_rejects_without_reusing_source_rows():
    """Account, amount, branch, reason, status, source category, date order, and consumption all reject candidates."""
    compile_program()
    write_inputs(
        [src("CGGATE000001", "ACCT3001", "TNT", 1000, "20260610", branch="BA01"), src("CGGATE000002", "ACCT3002", "TNT", 2000, "20260610", status="X", branch="BA02"), src("CGGATE000003", "ACCT3003", "RV", 3000, "20260611", branch="BA03"), src("CGGATE000004", "ACCT3004", "BAD", 4000, "20260612", branch="BA04")],
        [action("CGGATE000001", "ACCT3001", "TNT", 1000, "20260614", "C02", branch="BA01"), action("CGGATE000001", "ACCT3001", "TNT", 1000, "20260614", "C02", branch="BA01"), action("CGGATE000002", "ACCT3002", "TNT", 2000, "20260614", "C02", branch="BA02"), action("CGGATE000003", "ACCT3999", "RV", 3000, "20260614", "C06", branch="BA03"), action("CGGATE000003", "ACCT3003", "RV", 3999, "20260614", "C06", branch="BA03"), action("CGGATE000003", "ACCT3003", "RV", 3000, "20260609", "C06", branch="BA03"), action("CGGATE000003", "ACCT3003", "RV", 3000, "20260614", "BAD", branch="BA03"), action("CGGATE000004", "ACCT3004", "BAD", 4000, "20260614", "C02", branch="BA04")],
        ["20260610=OPEN", "20260611=OPEN", "20260612=OPEN"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert rows[1]["site_class"] == ""
    assert summary["matched_amount_cents"] == 1000
    assert summary["unmatched_amount_cents"] == 19999

def test_report_order_schema_blank_unmatched_and_zero_padded_amount_text():
    """Report rows must keep action order, exact header, blank unmatched class, and amount text including zeros."""
    compile_program()
    write_inputs(
        [src("CGORDER00001", "ACCT4001", "TNT", 101, "20260601", branch="BD01"), src("CGORDER00002", "ACCT4002", "RV", 202, "20260601", branch="BD02"), src("CGORDER00003", "ACCT4003", "CBN", 303, "20260601", branch="BD03")],
        [action("CGORDER00003", "ACCT4003", "CBN", 303, "20260602", "C10", branch="BD03"), action("CGORDER00002", "ACCT4002", "RV", 999, "20260602", "C06", branch="BD02"), action("CGORDER00001", "ACCT4001", "TNT", 101, "20260602", "C02", branch="BD01")],
        ["20260601=CLOS"],
    )
    rows, summary = run_program()
    assert [row["record_id"] for row in rows] == ["CGORDER00003", "CGORDER00002", "CGORDER00001"]
    assert [row["amount_cents"] for row in rows] == ["0000000303", "0000000999", "0000000101"]
    assert rows[1]["site_class"] == ""
    assert summary == {"matched_count": 2, "matched_amount_cents": 404, "unmatched_count": 1, "unmatched_amount_cents": 999}

def test_invalid_action_amounts_count_unmatched_but_not_amount_totals():
    """Malformed and zero action amounts are unmatched rows but must not inflate unmatched amount totals."""
    compile_program()
    write_inputs(
        [src("CGBADAMT0001", "ACCT5001", "TNT", 123, "20260601", branch="BE01"), src("CGBADAMT0002", "ACCT5002", "RV", "00000A0123", "20260601", branch="BE02")],
        [action("CGBADAMT0001", "ACCT5001", "TNT", "00000A0123", "20260602", "C02", branch="BE01"), action("CGBADAMT0001", "ACCT5001", "TNT", 0, "20260602", "C02", branch="BE01"), action("CGBADAMT0002", "ACCT5002", "RV", "00000A0123", "20260602", "C06", branch="BE02")],
        ["20260601=OPEN"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary["unmatched_count"] == 3
    assert summary["unmatched_amount_cents"] == 0

def test_nonpositive_source_amount_rejects_match():
    """A valid action must not match a source with zero amount."""
    compile_program()
    write_inputs(
        [src("CGBADSRC0001", "ACCT6001", "TNT", 0, "20260601", branch="BG01")],
        [action("CGBADSRC0001", "ACCT6001", "TNT", 0, "20260602", "C02", branch="BG01")],
        ["20260601=CLOS"],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert summary["matched_count"] == 0

def test_outputs_are_regenerated_not_appended_or_reused():
    """Preexisting output files must be replaced with current report and summary content."""
    compile_program()
    write_inputs(
        [src("CGSTALE00001", "ACCT6001", "TNT", 888, "20260601", branch="BF01")],
        [action("CGSTALE00001", "ACCT6001", "TNT", 888, "20260602", "C02", branch="BF01")],
        ["20260601=CLOS"],
    )
    rows, summary = run_program()
    assert "stale" not in REPORT.read_text()
    assert "stale" not in SUMMARY.read_text()
    assert rows[0]["status"] == "MATCHED"
    assert summary["matched_count"] == 1
