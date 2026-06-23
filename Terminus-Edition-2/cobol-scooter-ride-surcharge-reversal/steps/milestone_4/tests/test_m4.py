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


class TestMilestone4:
    """Verify runtime reason eligibility layered on calendar, alias, latest-date, and consumption rules."""

    def test_reason_file_enables_only_configured_reason_rows(self):
        """Only reasons listed with eligible=Y should authorize otherwise matching actions."""
        compile_program()
        write_inputs(
            [
                src("SCRSN0000001", "ACCT9101", "CBD", 100, "20261001", branch="CJ01"),
                src("SCRSN0000002", "ACCT9102", "RES", 200, "20261001", branch="CJ02"),
                src("SCRSN0000003", "ACCT9103", "UNI", 300, "20261001", branch="CJ03"),
            ],
            [
                action("SCRSN0000001", "ACCT9101", "CBD", 100, "20261002", "S02", branch="CJ01"),
                action("SCRSN0000002", "ACCT9102", "RES", 200, "20261002", "S07", branch="CJ02"),
                action("SCRSN0000003", "ACCT9103", "UNI", 300, "20261002", "S15", branch="CJ03"),
            ],
            ["20261001=OPEN", "20261002=OPEN"],
            ["code,eligible", "S02,Y", "S07,N"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED"]
        assert [row["zone_code"] for row in rows] == ["CBD", "", ""]
        assert summary["matched_amount_cents"] == 100
        assert summary["unmatched_amount_cents"] == 500

    def test_reason_enabled_is_trimmed_and_case_insensitive(self):
        """Reason code and eligible flags should tolerate surrounding spaces and lowercase values."""
        compile_program()
        write_inputs(
            [src("SCRSN0000004", "ACCT9104", "RES", 450, "20261003", branch="CJ04")],
            [action("SCRSN0000004", "ACCT9104", "RE", 450, "20261004", "S07", branch="CJ04")],
            ["20261003=Open", "20261004=OPEN"],
            ["code,eligible", "  s07 , y "],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["zone_code"] == "RES"
        assert summary["matched_count"] == 1

    def test_uppercase_csv_reason_matches_lowercase_action_reason(self):
        """Reason matching must be case-insensitive on both the CSV code and action reason."""
        compile_program()
        write_inputs(
            [src("SCRSN0000099", "ACCT9199", "RES", 500, "20261001", branch="CJ99")],
            [action("SCRSN0000099", "ACCT9199", "RE", 500, "20261002", "s07", branch="CJ99")],
            ["20261001=OPEN", "20261002=OPEN"],
            ["code,eligible", "S07,Y"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["zone_code"] == "RES"
        assert summary["matched_count"] == 1

    def test_malformed_blank_and_unlisted_reason_rows_do_not_enable_matching(self):
        """Malformed or blank reason policy rows should not authorize a reason or crash the batch."""
        compile_program()
        write_inputs(
            [
                src("SCRSN0000005", "ACCT9105", "UNI", 600, "20261005", branch="CJ05"),
                src("SCRSN0000006", "ACCT9106", "CBD", 700, "20261005", branch="CJ06"),
            ],
            [
                action("SCRSN0000005", "ACCT9105", "UN", 600, "20261006", "S15", branch="CJ05"),
                action("SCRSN0000006", "ACCT9106", "CB", 700, "20261006", "S02", branch="CJ06"),
            ],
            ["20261005=OPEN", "20261006=OPEN"],
            ["code,eligible", "S15,", "just-one-column", ",Y", "S02,Y"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert summary["matched_amount_cents"] == 700
        assert summary["unmatched_amount_cents"] == 600

    def test_later_reason_row_is_authoritative(self):
        """The last well-formed row for a reason should override an earlier setting."""
        compile_program()
        write_inputs(
            [
                src("SCRSN0000007", "ACCT9107", "CBD", 800, "20261007", branch="CJ07"),
                src("SCRSN0000008", "ACCT9108", "RES", 900, "20261007", branch="CJ08"),
            ],
            [
                action("SCRSN0000007", "ACCT9107", "CBD", 800, "20261008", "S02", branch="CJ07"),
                action("SCRSN0000008", "ACCT9108", "RES", 900, "20261008", "S07", branch="CJ08"),
            ],
            ["20261007=OPEN", "20261008=OPEN"],
            ["code,eligible", "S02,Y", "S02,N", "S07,N", "S07,Y"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert summary["matched_amount_cents"] == 900
        assert summary["unmatched_amount_cents"] == 800

    def test_reason_gate_preserves_latest_date_selection_and_aliases(self):
        """Runtime reasons should combine with alias normalization and latest source date selection."""
        compile_program()
        write_inputs(
            [
                src("SCRSN0000009", "ACCT9109", "RES", 1000, "20261001", branch="CJ09"),
                src("SCRSN0000009", "ACCT9109", "RES", 1000, "20261005", branch="CJ09"),
            ],
            [
                action("SCRSN0000009", "ACCT9109", "RE", 1000, "20261010", "S07", branch="CJ09"),
                action("SCRSN0000009", "ACCT9109", "RE", 1000, "20261003", "S07", branch="CJ09"),
            ],
            ["20261001=OPEN", "20261003=OPEN", "20261005=OPEN", "20261010=OPEN"],
            ["code,eligible", "S07,Y"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["zone_code"] for row in rows] == ["RES", "RES"]
        assert summary["matched_amount_cents"] == 2000

    def test_enabled_reason_does_not_bypass_other_gates(self):
        """A valid reason should not bypass amount, account, status, or calendar gates."""
        compile_program()
        write_inputs(
            [
                src("SCRSN0000010", "ACCT9110", "CBD", 1100, "20261011", branch="CJ10"),
                src("SCRSN0000011", "ACCT9111", "CBD", 1200, "20261012", status="X", branch="CJ11"),
            ],
            [
                action("SCRSN0000010", "ACCT9110", "CB", 1199, "20261013", "S02", branch="CJ10"),
                action("SCRSN0000011", "ACCT9111", "CB", 1200, "20261013", "S02", branch="CJ11"),
            ],
            ["20261011=OPEN", "20261012=OPEN", "20261013=OPEN"],
            ["code,eligible", "S02,Y"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 2399
