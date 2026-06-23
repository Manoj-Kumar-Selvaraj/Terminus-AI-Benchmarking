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


class TestMilestone2:
    """Verify legacy zone aliases while preserving milestone 1 matching and consumption behavior."""

    def test_legacy_aliases_match_and_emit_canonical_categories(self):
        """Legacy aliases should normalize to canonical categories before matching and in the report."""
        compile_program()
        write_inputs(
            [
                src("SCAL00000001", "ACCT5001", "CBD", 1500, "20260701", branch="BE01"),
                src("SCAL00000002", "ACCT5002", "RES", 2500, "20260701", branch="BE02"),
                src("SCAL00000003", "ACCT5003", "UNI", 3500, "20260701", branch="BE03"),
            ],
            [
                action("SCAL00000001", "ACCT5001", "CB", 1500, "20260702", "S02", branch="BE01"),
                action("SCAL00000002", "ACCT5002", "RE", 2500, "20260702", "S07", branch="BE02"),
                action("SCAL00000003", "ACCT5003", "UN", 3500, "20260702", "S15", branch="BE03"),
            ],
            ["20260701=OPEN"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["zone_code"] for row in rows] == ["CBD", "RES", "UNI"]
        assert summary["matched_count"] == 3

    def test_duplicate_actions_do_not_reuse_the_same_source_row(self):
        """Only the first eligible action may consume a matching source row."""
        compile_program()
        write_inputs(
            [src("SCDUP0000001", "ACCT6001", "CBD", 900, "20260710", branch="BF01")],
            [
                action("SCDUP0000001", "ACCT6001", "CBD", 900, "20260711", "S02", branch="BF01"),
                action("SCDUP0000001", "ACCT6001", "CBD", 900, "20260712", "S02", branch="BF01"),
            ],
            ["20260710=OPEN"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[1]["zone_code"] == ""
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 900,
            "unmatched_count": 1,
            "unmatched_amount_cents": 900,
        }

    def test_alias_mismatch_is_not_a_wildcard_match(self):
        """A normalized alias must still equal the source zone rather than matching any allowed source zone."""
        compile_program()
        write_inputs(
            [src("SCMISM000001", "ACCT6101", "CBD", 700, "20260720", branch="BF02")],
            [action("SCMISM000001", "ACCT6101", "RE", 700, "20260721", "S02", branch="BF02")],
            ["20260720=OPEN", "20260721=OPEN"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["zone_code"] == ""
        assert summary["unmatched_amount_cents"] == 700

    def test_canonical_and_alias_actions_share_consumption_in_one_batch(self):
        """Canonical and aliased action rows should compete for the same physical source row."""
        compile_program()
        write_inputs(
            [
                src("SCMIX0000001", "ACCT6201", "CBD", 300, "20260722", branch="BF03"),
                src("SCMIX0000002", "ACCT6202", "RES", 400, "20260722", branch="BF04"),
            ],
            [
                action("SCMIX0000001", "ACCT6201", "CB", 300, "20260723", "S02", branch="BF03"),
                action("SCMIX0000001", "ACCT6201", "CBD", 300, "20260724", "S02", branch="BF03"),
                action("SCMIX0000002", "ACCT6202", "RES", 400, "20260723", "S07", branch="BF04"),
            ],
            ["20260722=OPEN", "20260723=OPEN", "20260724=OPEN"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["zone_code"] for row in rows] == ["CBD", "", "RES"]
        assert summary["matched_amount_cents"] == 700
        assert summary["unmatched_amount_cents"] == 300

    def test_unknown_two_character_prefix_stays_unmatched(self):
        """Only CB, RE, and UN aliases should normalize; other prefixes remain unsupported."""
        compile_program()
        write_inputs(
            [src("SCUNK0000001", "ACCT6301", "UNI", 800, "20260725", branch="BF05")],
            [action("SCUNK0000001", "ACCT6301", "UX", 800, "20260726", "S15", branch="BF05")],
            ["20260725=OPEN", "20260726=OPEN"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["zone_code"] == ""
        assert summary["unmatched_count"] == 1
