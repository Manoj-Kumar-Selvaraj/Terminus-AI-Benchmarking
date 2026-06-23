
"""Verifier tests for the Ruby florist reconciliation CLI."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "orders.csv"
ACTIONS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"


def write_inputs(source_rows, action_rows, calendar_rows=None, dated=False):
    """Replace CSV inputs and optional calendar with a focused scenario."""
    source_header = "order_id,couple_id,amount_cents,status,arrangement" + (",delivery_date" if dated else "")
    action_header = "order_id,couple_id,amount_cents,arrangement" + (",credit_date" if dated else "")
    SOURCE.write_text(source_header + "\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text(action_header + "\n" + "\n".join(action_rows) + "\n")
    if calendar_rows is not None:
        CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the Ruby batch and return parsed report and summary outputs."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())






class TestMilestone3:
    """Date gates, latest source-date selection, aliases, and row consumption."""

    def test_open_action_date_and_latest_delivery_date_win(self):
        """Open action dates should gate matching and latest eligible delivery_date should win."""
        write_inputs(
            [
                "DATE9001,CUST9001,1000,DELIVERED,BOUQUET,2026-04-03",
                "DATE9001,CUST9001,1000,DELIVERED,CENTERPIECE,2026-04-08",
                "DATE9002,CUST9002,2000,DELIVERED,CENTERPIECE,2026-04-02",
            ],
            [
                "DATE9001,CUST9001,1000,CTR,2026-04-02",
                "DATE9002,CUST9002,2000,CTR,2026-04-04",
            ],
            ["2026-04-02 open", "2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[0]["arrangement"] == "CENTERPIECE"
        assert summary["matched_amount_cents"] == 1000
        assert summary["unmatched_amount_cents"] == 2000

    def test_latest_delivery_date_wins_even_when_later_row_appears_first(self):
        """The latest delivery_date must beat file order, not simply last eligible row."""
        write_inputs(
            [
                "DATE9101,CUST9101,850,DELIVERED,CENTERPIECE,2026-04-08",
                "DATE9101,CUST9101,850,DELIVERED,BOUQUET,2026-04-05",
            ],
            ["DATE9101,CUST9101,850,CTR,2026-04-04"],
            ["2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["arrangement"] == "CENTERPIECE"
        assert summary["matched_count"] == 1

    def test_same_delivery_date_tie_uses_source_order_and_consumption(self):
        """Same-date candidates should use source row order while preserving consumption."""
        write_inputs(
            [
                "DATE9201,CUST9201,500,DELIVERED,ARCH,2026-04-05",
                "DATE9201,CUST9201,500,DELIVERED,ARCH,2026-04-05",
            ],
            [
                "DATE9201,CUST9201,500,ARC,2026-04-04",
                "DATE9201,CUST9201,500,ARC,2026-04-04",
                "DATE9201,CUST9201,500,ARC,2026-04-04",
            ],
            ["2026-04-04 open", "2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 2
        assert summary["unmatched_count"] == 1

    def test_closed_unlisted_and_missing_action_dates_are_ineligible(self):
        """Closed, unlisted, and blank action dates should not match."""
        write_inputs(
            [
                "DATE9301,CUST9301,100,DELIVERED,BOUQUET,2026-04-10",
                "DATE9302,CUST9302,200,DELIVERED,BOUQUET,2026-04-10",
                "DATE9303,CUST9303,300,DELIVERED,BOUQUET,2026-04-10",
            ],
            [
                "DATE9301,CUST9301,100,BOUQUET,2026-04-05",
                "DATE9302,CUST9302,200,BOUQUET,2026-04-06",
                "DATE9303,CUST9303,300,BOUQUET,",
            ],
            ["2026-04-05 closed"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 600

    def test_missing_delivery_date_and_action_after_delivery_date_are_ineligible(self):
        """Missing delivery dates and action dates after delivery_date should reject matching."""
        write_inputs(
            [
                "DATE9401,CUST9401,700,DELIVERED,CENTERPIECE,",
                "DATE9402,CUST9402,800,DELIVERED,CENTERPIECE,2026-04-03",
            ],
            [
                "DATE9401,CUST9401,700,CTR,2026-04-02",
                "DATE9402,CUST9402,800,CTR,2026-04-04",
            ],
            ["2026-04-02 open", "2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert summary["unmatched_amount_cents"] == 1500

    def test_arch_alias_still_works_with_dated_matching(self):
        """The arch documented alias should still normalize under dated matching."""
        write_inputs(
            ["DATE9501,CUST9501,650,DELIVERED,BOUQUET,2026-04-10"],
            ["DATE9501,CUST9501,650,BQT,2026-04-05"],
            ["2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["arrangement"] == "BOUQUET"
        assert summary == {"matched_count": 1, "matched_amount_cents": 650, "unmatched_count": 0, "unmatched_amount_cents": 0}

    def test_mismatched_dimension_does_not_match_even_with_valid_dates(self):
        """Date logic must not bypass the original dimension equality requirement."""
        write_inputs(
            ["DATE9451,CUST9451,775,DELIVERED,BOUQUET,2026-04-10"],
            ["DATE9451,CUST9451,775,CENTERPIECE,2026-04-05"],
            ["2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["arrangement"] == ""
        assert summary["unmatched_amount_cents"] == 775


    def test_old_schema_without_dates_preserves_prior_matching(self):
        """Older CSVs without date columns should keep the previous matching behavior."""
        write_inputs(
            ["OLD9601,CUST9601,450,DELIVERED,BOUQUET"],
            ["OLD9601,CUST9601,450,BQT"],
            ["2026-04-05 closed"],
            dated=False,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["arrangement"] == "BOUQUET"
        assert summary["matched_amount_cents"] == 450
