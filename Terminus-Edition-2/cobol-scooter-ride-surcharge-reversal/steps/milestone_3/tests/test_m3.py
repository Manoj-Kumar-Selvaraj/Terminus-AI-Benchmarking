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


class TestMilestone3:
    """Verify fleet calendar gates, latest-source-date selection, tie ordering, aliases, and consumption."""

    def test_closed_missing_and_malformed_calendar_dates_stay_unmatched(self):
        """Closed, missing, malformed, or unlisted source dates should never be treated as open."""
        compile_program()
        write_inputs(
            [
                src("SCCAL0000001", "ACCT3001", "CBD", 1111, "20260520", branch="BC01"),
                src("SCCAL0000002", "ACCT3002", "RES", 2222, "20260521", branch="BC02"),
                src("SCCAL0000003", "ACCT3003", "UNI", 3333, "20260522", branch="BC03"),
                src("SCCAL0000004", "ACCT3004", "CBD", 4444, "BAD-DATE", branch="BC04"),
            ],
            [
                action("SCCAL0000001", "ACCT3001", "CBD", 1111, "20260523", "S02", branch="BC01"),
                action("SCCAL0000002", "ACCT3002", "RES", 2222, "20260523", "S07", branch="BC02"),
                action("SCCAL0000003", "ACCT3003", "UNI", 3333, "20260523", "S15", branch="BC03"),
                action("SCCAL0000004", "ACCT3004", "CBD", 4444, "20260523", "S02", branch="BC04"),
            ],
            ["20260520=OPEN", "20260521=CLOS", "BAD-DATE=OPEN"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary["matched_amount_cents"] == 1111
        assert summary["unmatched_amount_cents"] == 9999

    def test_latest_source_date_wins_before_older_row_is_used(self):
        """The first action must consume the latest source date, leaving an older row for a narrower second action."""
        compile_program()
        write_inputs(
            [
                src("SCLAT0000001", "ACCT7001", "CBD", 500, "20260801", branch="BG01"),
                src("SCLAT0000001", "ACCT7001", "CBD", 500, "20260805", branch="BG01"),
            ],
            [
                action("SCLAT0000001", "ACCT7001", "CBD", 500, "20260810", "S02", branch="BG01"),
                action("SCLAT0000001", "ACCT7001", "CBD", 500, "20260803", "S02", branch="BG01"),
            ],
            ["20260801=OPEN", "20260805=OPEN", "20260803=OPEN", "20260810=OPEN"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 1000

    def test_same_source_date_tie_prefers_earliest_input_row_and_consumes_both(self):
        """When source dates tie, the earliest row is chosen first and the duplicate remains available for the next action."""
        compile_program()
        write_inputs(
            [
                src("SCTIE0000001", "ACCT7101", "CBD", 500, "20260805", branch="BG01"),
                src("SCTIE0000001", "ACCT7101", "CBD", 500, "20260805", branch="BG01"),
            ],
            [
                action("SCTIE0000001", "ACCT7101", "CBD", 500, "20260810", "S02", branch="BG01"),
                action("SCTIE0000001", "ACCT7101", "CBD", 500, "20260810", "S02", branch="BG01"),
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

    def test_duplicate_record_id_rows_are_consumed_by_position(self):
        """Two source rows with the same record id must be independently consumable by amount."""
        compile_program()
        write_inputs(
            [
                src("SCPOS000001", "ACCT9001", "CBD", 500, "20260810", branch="BX01"),
                src("SCPOS000001", "ACCT9001", "CBD", 700, "20260810", branch="BX01"),
            ],
            [
                action("SCPOS000001", "ACCT9001", "CBD", 500, "20260811", "S02", branch="BX01"),
                action("SCPOS000001", "ACCT9001", "CBD", 700, "20260811", "S02", branch="BX01"),
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

    def test_non_numeric_action_date_is_unmatched(self):
        """Non-numeric action dates must reject otherwise matching candidates."""
        compile_program()
        write_inputs(
            [src("SCNNA0000001", "ACCT9901", "CBD", 500, "20260901", branch="BX01")],
            [action("SCNNA0000001", "ACCT9901", "CBD", 500, "BAD-DATE", "S02", branch="BX01")],
            ["20260901=OPEN"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert summary["unmatched_count"] == 1

    def test_calendar_open_state_is_case_insensitive(self):
        """Mixed-case OPEN calendar states must still allow eligible source dates."""
        compile_program()
        write_inputs(
            [
                src("SCCASE000001", "ACCT9002", "CBD", 500, "20260901", branch="BX02"),
                src("SCCASE000002", "ACCT9003", "RES", 500, "20260902", branch="BX03"),
                src("SCCASE000003", "ACCT9004", "UNI", 500, "20260903", branch="BX04"),
            ],
            [
                action("SCCASE000001", "ACCT9002", "CB", 500, "20260904", "S02", branch="BX02"),
                action("SCCASE000002", "ACCT9003", "RE", 500, "20260904", "S07", branch="BX03"),
                action("SCCASE000003", "ACCT9004", "UN", 500, "20260904", "S15", branch="BX04"),
            ],
            ["20260901=oPeN", "20260902=OpEn", "20260903=Open", "20260904=OPEN"],
        )
        rows, summary = run_program()

        assert all(row["status"] == "MATCHED" for row in rows)
        assert [row["zone_code"] for row in rows] == ["CBD", "RES", "UNI"]
        assert summary["matched_count"] == 3

    def test_second_action_stays_unmatched_after_latest_source_row_is_consumed(self):
        """Once the only eligible source row is consumed, a second duplicate action must remain unmatched."""
        compile_program()
        write_inputs(
            [src("SCLAT0000002", "ACCT7002", "CBD", 1000, "20260805", branch="BG01")],
            [
                action("SCLAT0000002", "ACCT7002", "CB", 1000, "20260810", "S02", branch="BG01"),
                action("SCLAT0000002", "ACCT7002", "CB", 1000, "20260811", "S02", branch="BG01"),
            ],
            ["20260805=OPEN", "20260810=OPEN", "20260811=OPEN"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_aliases_still_work_under_calendar_gates(self):
        """Alias normalization must still apply when calendar gates are enforced."""
        compile_program()
        write_inputs(
            [src("SCALM3000001", "ACCT8001", "UNI", 650, "20260901", branch="BH01")],
            [action("SCALM3000001", "ACCT8001", "UN", 650, "20260902", "S15", branch="BH01")],
            ["20260901=OPEN", "20260902=OPEN"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["zone_code"] == "UNI"
        assert summary["matched_amount_cents"] == 650

    def test_action_date_before_open_source_date_is_not_eligible(self):
        """An action date before the source date should be unmatched even when the source date is open."""
        compile_program()
        write_inputs(
            [src("SCBEF0000001", "ACCT8101", "RES", 775, "20260910", branch="BH02")],
            [action("SCBEF0000001", "ACCT8101", "RE", 775, "20260909", "S07", branch="BH02")],
            ["20260909=OPEN", "20260910=OPEN"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["zone_code"] == ""
        assert summary["unmatched_amount_cents"] == 775
