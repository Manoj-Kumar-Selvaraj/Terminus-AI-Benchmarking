"""Tests for the scooter ride surcharge reversal COBOL reconciler."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
SRC = APP / "src" / "scooter_surcharge_reconcile.cbl"
BIN = APP / "build" / "scooter_surcharge_reconcile"
SOURCE = APP / "data" / "ride_charges.dat"
ACTION = APP / "data" / "surcharge_reversals.dat"
CALENDAR = APP / "config" / "fleet_calendar.txt"
REASONS = APP / "config" / "reasons.csv"
CATEGORIES = APP / "config" / "categories.csv"
REPORT = APP / "out" / "scooter_surcharge_report.csv"
SUMMARY = APP / "out" / "scooter_surcharge_summary.txt"


def src(record_id, account, category, amount, date, status="Z", branch="B001"):
    """Create one fixed-width source record."""
    amount_text = f"{amount:010d}" if isinstance(amount, int) else str(amount).ljust(10)[:10]
    return f"S{record_id:<12}{account:<8}{category:<3}{amount_text}{date:<8}{status}{branch:<4}"


def action(record_id, account, category, amount, date, reason, branch="B001"):
    """Create one fixed-width action record."""
    amount_text = f"{amount:010d}" if isinstance(amount, int) else str(amount).ljust(10)[:10]
    return f"A{record_id:<12}{account:<8}{category:<3}{amount_text}{date:<8}{reason:<3}{branch:<4}"


def compile_program():
    """Compile the COBOL program for one test scenario."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cobc", "-x", "-free", "-O2", "-o", str(BIN), str(SRC)], check=True, cwd=APP, timeout=60)


def write_inputs(source_lines, action_lines, calendar_lines, reason_lines=None, category_lines=None):
    """Replace input files so outputs cannot be precomputed from shipped fixtures."""
    SOURCE.write_text("\n".join(source_lines) + "\n")
    ACTION.write_text("\n".join(action_lines) + "\n")
    CALENDAR.write_text("\n".join(calendar_lines) + "\n")
    if reason_lines is not None:
        REASONS.write_text("\n".join(reason_lines) + "\n")
    if category_lines is not None:
        CATEGORIES.write_text("\n".join(category_lines) + "\n")
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


class TestMilestone5:
    """Verify category policy limits layered after aliases, calendar gates, runtime reasons, and consumption."""

    def test_category_gate_requires_enabled_row_and_amount_within_limit(self):
        """Only enabled categories with enough max_reversal_cents should remain eligible."""
        compile_program()
        write_inputs(
            [
                src("SCPOL0000001", "ACCT9201", "CBD", 400, "20261101", branch="DK01"),
                src("SCPOL0000002", "ACCT9202", "RES", 500, "20261101", branch="DK02"),
                src("SCPOL0000003", "ACCT9203", "UNI", 600, "20261101", branch="DK03"),
            ],
            [
                action("SCPOL0000001", "ACCT9201", "CB", 400, "20261102", "S02", branch="DK01"),
                action("SCPOL0000002", "ACCT9202", "RE", 500, "20261102", "S07", branch="DK02"),
                action("SCPOL0000003", "ACCT9203", "UN", 600, "20261102", "S15", branch="DK03"),
            ],
            ["20261101=OPEN", "20261102=OPEN"],
            ["code,eligible", "S02,Y", "S07,Y", "S15,Y"],
            ["zone_code,surcharge_enabled,max_reversal_cents", "CBD,true,400", "RES,false,900"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary["matched_amount_cents"] == 400
        assert summary["unmatched_amount_cents"] == 1100

    def test_category_limit_greater_than_amount_still_matches(self):
        """A limit strictly above the action amount should remain eligible."""
        compile_program()
        write_inputs(
            [src("SCPOL0000020", "ACCT9220", "CBD", 400, "20261120", branch="DK20")],
            [action("SCPOL0000020", "ACCT9220", "CB", 400, "20261121", "S02", branch="DK20")],
            ["20261120=OPEN", "20261121=OPEN"],
            ["code,eligible", "S02,Y"],
            ["zone_code,surcharge_enabled,max_reversal_cents", "CBD,true,1000"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert summary["matched_count"] == 1

    def test_category_limit_below_amount_rejects_even_when_enabled(self):
        """An enabled zone with a limit below the action amount must stay unmatched."""
        compile_program()
        write_inputs(
            [src("SCPOL0000021", "ACCT9221", "CBD", 500, "20261120", branch="DK21")],
            [action("SCPOL0000021", "ACCT9221", "CB", 500, "20261121", "S02", branch="DK21")],
            ["20261120=OPEN", "20261121=OPEN"],
            ["code,eligible", "S02,Y"],
            ["zone_code,surcharge_enabled,max_reversal_cents", "CBD,true,300"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert summary["unmatched_count"] == 1

    def test_category_enabled_case_trim_and_aliases_are_normalized(self):
        """Category policy parsing should trim and case-normalize enabled values and zone keys."""
        compile_program()
        write_inputs(
            [src("SCPOL0000004", "ACCT9204", "CBD", 550, "20261103", branch="DK04")],
            [action("SCPOL0000004", "ACCT9204", "CB", 550, "20261104", "S02", branch="DK04")],
            ["20261103=oPeN", "20261104=OPEN"],
            ["code,eligible", "S02,Y"],
            ["zone_code,surcharge_enabled,max_reversal_cents", " cbd , TRUE , 0550 "],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["zone_code"] == "CBD"
        assert summary["matched_count"] == 1

    def test_category_last_row_is_authoritative_for_each_zone(self):
        """Later category policy rows should override earlier rows for the same canonical zone."""
        compile_program()
        write_inputs(
            [
                src("SCPOL0000005", "ACCT9205", "CBD", 700, "20261105", branch="DK05"),
                src("SCPOL0000006", "ACCT9206", "RES", 800, "20261105", branch="DK06"),
            ],
            [
                action("SCPOL0000005", "ACCT9205", "CBD", 700, "20261106", "S02", branch="DK05"),
                action("SCPOL0000006", "ACCT9206", "RES", 800, "20261106", "S07", branch="DK06"),
            ],
            ["20261105=OPEN", "20261106=OPEN"],
            ["code,eligible", "S02,Y", "S07,Y"],
            [
                "zone_code,surcharge_enabled,max_reversal_cents",
                "CBD,true,1000", "CBD,false,1000",
                "RES,false,1000", "RES,true,800",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert summary["matched_amount_cents"] == 800
        assert summary["unmatched_amount_cents"] == 700

    def test_malformed_blank_negative_and_noninteger_limits_are_ineligible(self):
        """Malformed policy rows or invalid max values should not authorize a category."""
        compile_program()
        write_inputs(
            [
                src("SCPOL0000007", "ACCT9207", "UNI", 900, "20261107", branch="DK07"),
                src("SCPOL0000008", "ACCT9208", "CBD", 1000, "20261107", branch="DK08"),
                src("SCPOL0000009", "ACCT9209", "RES", 1100, "20261107", branch="DK09"),
            ],
            [
                action("SCPOL0000007", "ACCT9207", "UN", 900, "20261108", "S15", branch="DK07"),
                action("SCPOL0000008", "ACCT9208", "CB", 1000, "20261108", "S02", branch="DK08"),
                action("SCPOL0000009", "ACCT9209", "RE", 1100, "20261108", "S07", branch="DK09"),
            ],
            ["20261107=OPEN", "20261108=OPEN"],
            ["code,eligible", "S02,Y", "S07,Y", "S15,Y"],
            [
                "zone_code,surcharge_enabled,max_reversal_cents",
                "UNI,true,abc", "CBD,true,-1", "RES,true,", "BADROW",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 3000

    def test_category_limit_is_enforced_after_latest_date_selection(self):
        """The category amount limit should combine with latest-date selection and row consumption."""
        compile_program()
        write_inputs(
            [
                src("SCPOL0000010", "ACCT9210", "CBD", 600, "20261101", branch="DK10"),
                src("SCPOL0000010", "ACCT9210", "CBD", 600, "20261105", branch="DK10"),
            ],
            [
                action("SCPOL0000010", "ACCT9210", "CB", 600, "20261110", "S02", branch="DK10"),
                action("SCPOL0000010", "ACCT9210", "CB", 600, "20261103", "S02", branch="DK10"),
            ],
            ["20261101=OPEN", "20261103=OPEN", "20261105=OPEN", "20261110=OPEN"],
            ["code,eligible", "S02,Y"],
            ["zone_code,surcharge_enabled,max_reversal_cents", "CBD,true,600"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert summary["matched_amount_cents"] == 1200

    def test_category_policy_does_not_bypass_reason_or_calendar_gates(self):
        """Enabled category policy should not make disabled reasons or closed calendar dates match."""
        compile_program()
        write_inputs(
            [
                src("SCPOL0000011", "ACCT9211", "CBD", 500, "20261111", branch="DK11"),
                src("SCPOL0000012", "ACCT9212", "RES", 500, "20261112", branch="DK12"),
            ],
            [
                action("SCPOL0000011", "ACCT9211", "CB", 500, "20261113", "S02", branch="DK11"),
                action("SCPOL0000012", "ACCT9212", "RE", 500, "20261113", "S07", branch="DK12"),
            ],
            ["20261111=CLOS", "20261112=OPEN", "20261113=OPEN"],
            ["code,eligible", "S02,Y", "S07,N"],
            ["zone_code,surcharge_enabled,max_reversal_cents", "CBD,true,500", "RES,true,500"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert summary["unmatched_amount_cents"] == 1000

    def test_category_policies_are_independent_per_zone(self):
        """Disabling one zone should not disable unrelated enabled zones."""
        compile_program()
        write_inputs(
            [
                src("SCPOL0000013", "ACCT9213", "CBD", 300, "20261114", branch="DK13"),
                src("SCPOL0000014", "ACCT9214", "RES", 300, "20261114", branch="DK14"),
                src("SCPOL0000015", "ACCT9215", "UNI", 300, "20261114", branch="DK15"),
            ],
            [
                action("SCPOL0000013", "ACCT9213", "CB", 300, "20261115", "S02", branch="DK13"),
                action("SCPOL0000014", "ACCT9214", "RE", 300, "20261115", "S07", branch="DK14"),
                action("SCPOL0000015", "ACCT9215", "UN", 300, "20261115", "S15", branch="DK15"),
            ],
            ["20261114=OPEN", "20261115=OPEN"],
            ["code,eligible", "S02,Y", "S07,Y", "S15,Y"],
            ["zone_code,surcharge_enabled,max_reversal_cents", "CBD,true,300", "RES,false,300", "UNI,true,300"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert summary["matched_amount_cents"] == 600
        assert summary["unmatched_amount_cents"] == 300
