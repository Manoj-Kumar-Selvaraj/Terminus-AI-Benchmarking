
"""Verifier tests for the Ruby brewery reconciliation CLI."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "kegs.csv"
ACTIONS = APP / "data" / "deposits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
METHODS = APP / "config" / "methods.csv"
REPORT = APP / "out" / "deposit_report.csv"
SUMMARY = APP / "out" / "deposit_summary.json"


def write_inputs(source_rows, action_rows, calendar_rows=None, dated=False):
    """Replace CSV inputs and optional calendar with a focused scenario."""
    source_header = "keg_id,distributor_id,amount_cents,status,keg_type" + (",return_date" if dated else "")
    action_header = "keg_id,distributor_id,amount_cents,keg_type" + (",deposit_date" if dated else "")
    SOURCE.write_text(source_header + "\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text(action_header + "\n" + "\n".join(action_rows) + "\n")
    if calendar_rows is not None:
        CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_methods(rows):
    """Replace keg type policy with enabled flags and priorities."""
    METHODS.write_text("keg_type,enabled,priority\n" + "\n".join(rows) + "\n")


def run_program():
    """Run the Ruby batch and return parsed report and summary outputs."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())






class TestMilestone4DateSelection:
    """Date gates, latest source-date selection, aliases, and row consumption."""

    def test_open_action_date_and_latest_due_date_win(self):
        """Open action dates should gate matching and latest eligible due date should win."""
        write_inputs(
            [
                "DATE9001,CUST9001,1000,RETURNED,HALF,2026-04-03",
                "DATE9001,CUST9001,1000,RETURNED,SIXTH,2026-04-08",
                "DATE9002,CUST9002,2000,RETURNED,SIXTH,2026-04-02",
            ],
            [
                "DATE9001,CUST9001,1000,SIX,2026-04-02",
                "DATE9002,CUST9002,2000,SIX,2026-04-04",
            ],
            ["2026-04-02 open", "2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[0]["keg_type"] == "SIXTH"
        assert summary["matched_amount_cents"] == 1000
        assert summary["unmatched_amount_cents"] == 2000

    def test_latest_due_date_wins_even_when_later_row_appears_cornelius(self):
        """The latest due date must beat file order, not simply last eligible row."""
        write_inputs(
            [
                "DATE9101,CUST9101,850,RETURNED,SIXTH,2026-04-08",
                "DATE9101,CUST9101,850,RETURNED,HALF,2026-04-05",
            ],
            ["DATE9101,CUST9101,850,SIX,2026-04-04"],
            ["2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["keg_type"] == "SIXTH"
        assert summary["matched_count"] == 1

    def test_same_due_date_tie_uses_source_order_and_consumption(self):
        """Same-date candidates should visibly use source row order before consumption."""
        write_inputs(
            [
                "DATE9201,CUST9201,500,RETURNED,HALF,2026-04-05",
                "DATE9201,CUST9201,500,RETURNED,SIXTH,2026-04-05",
                "DATE9201,CUST9201,500,RETURNED,CORNELIUS,2026-04-04",
            ],
            [
                "DATE9201,CUST9201,500,HLF,2026-04-04",
                "DATE9201,CUST9201,500,SIX,2026-04-04",
                "DATE9201,CUST9201,500,HLF,2026-04-04",
            ],
            ["2026-04-04 open", "2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["keg_type"] for row in rows] == ["HALF", "SIXTH", ""]
        assert summary["matched_count"] == 2
        assert summary["unmatched_count"] == 1

    def test_closed_unlisted_and_missing_action_dates_are_ineligible(self):
        """Closed, unlisted, and blank action dates should not match."""
        write_inputs(
            [
                "DATE9301,CUST9301,100,RETURNED,HALF,2026-04-10",
                "DATE9302,CUST9302,200,RETURNED,HALF,2026-04-10",
                "DATE9303,CUST9303,300,RETURNED,HALF,2026-04-10",
            ],
            [
                "DATE9301,CUST9301,100,HALF,2026-04-05",
                "DATE9302,CUST9302,200,HALF,2026-04-06",
                "DATE9303,CUST9303,300,HALF,",
            ],
            ["2026-04-05 closed"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 600

    def test_missing_due_date_and_action_after_due_date_are_ineligible(self):
        """Missing source due dates and action dates after due date should reject matching."""
        write_inputs(
            [
                "DATE9401,CUST9401,700,RETURNED,SIXTH,",
                "DATE9402,CUST9402,800,RETURNED,SIXTH,2026-04-03",
            ],
            [
                "DATE9401,CUST9401,700,SIX,2026-04-02",
                "DATE9402,CUST9402,800,SIX,2026-04-04",
            ],
            ["2026-04-02 open", "2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert summary["unmatched_amount_cents"] == 1500

    def test_cornelius_alias_still_works_with_dated_matching(self):
        """The cornelius documented alias should still normalize under dated matching."""
        write_inputs(
            ["DATE9501,CUST9501,650,RETURNED,HALF,2026-04-10"],
            ["DATE9501,CUST9501,650,HLF,2026-04-05"],
            ["2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["keg_type"] == "HALF"
        assert summary == {"matched_count": 1, "matched_amount_cents": 650, "unmatched_count": 0, "unmatched_amount_cents": 0}

    def test_mismatched_dimension_does_not_match_even_with_valid_dates(self):
        """Date logic must not bypass the original dimension equality requirement."""
        write_inputs(
            ["DATE9451,CUST9451,775,RETURNED,HALF,2026-04-10"],
            ["DATE9451,CUST9451,775,SIXTH,2026-04-05"],
            ["2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["keg_type"] == ""
        assert summary["unmatched_amount_cents"] == 775


    def test_old_schema_without_dates_preserves_prior_matching(self):
        """Older CSVs without date columns should keep the previous matching behavior."""
        write_inputs(
            ["OLD9601,CUST9601,450,RETURNED,HALF"],
            ["OLD9601,CUST9601,450,HLF"],
            ["2026-04-05 closed"],
            dated=False,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["keg_type"] == "HALF"
        assert summary["matched_amount_cents"] == 450


class TestMilestone4:
    """Config-driven keg type policy and ANY type ranking."""

    def test_disabled_configured_keg_type_rejects_otherwise_valid_deposit(self):
        """Disabled methods.csv keg types must not match even with valid ids, dates, and aliases."""
        write_methods(["HALF,true,2", "SIXTH,false,1", "CORNELIUS,true,3"])
        write_inputs(
            ["CFG1001,DIST1001,1200,RETURNED,SIXTH,2026-04-10"],
            ["CFG1001,DIST1001,1200,SIX,2026-04-05"],
            ["2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["keg_type"] == ""
        assert summary == {"matched_count": 0, "matched_amount_cents": 0, "unmatched_count": 1, "unmatched_amount_cents": 1200}

    def test_any_same_date_uses_config_priority_before_source_order(self):
        """ANY ties on return date should use configured priority before source row order."""
        write_methods(["HALF,true,5", "SIXTH,true,1", "CORNELIUS,true,3"])
        write_inputs(
            [
                "ANY2001,DIST2001,700,RETURNED,HALF,2026-04-08",
                "ANY2001,DIST2001,700,RETURNED,CORNELIUS,2026-04-08",
                "ANY2001,DIST2001,700,RETURNED,SIXTH,2026-04-08",
            ],
            ["ANY2001,DIST2001,700,ANY,2026-04-04"],
            ["2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["keg_type"] == "SIXTH"
        assert summary["matched_count"] == 1

    def test_any_equal_priority_tie_uses_earliest_visible_source_row(self):
        """ANY ties on date and priority should visibly choose the earliest source row."""
        write_methods(["HALF,true,1", "SIXTH,true,1", "CORNELIUS,true,9"])
        write_inputs(
            [
                "ANY3001,DIST3001,800,RETURNED,HALF,2026-04-09",
                "ANY3001,DIST3001,800,RETURNED,SIXTH,2026-04-09",
            ],
            ["ANY3001,DIST3001,800,ANY,2026-04-04"],
            ["2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["keg_type"] == "HALF"
        assert summary["matched_amount_cents"] == 800

    def test_any_consumes_selected_row_and_next_refund_uses_next_best_candidate(self):
        """ANY matching should consume by row position and rerank remaining candidates."""
        write_methods(["HALF,true,1", "SIXTH,true,2", "CORNELIUS,true,3"])
        write_inputs(
            [
                "ANY4001,DIST4001,500,RETURNED,HALF,2026-04-07",
                "ANY4001,DIST4001,500,RETURNED,SIXTH,2026-04-07",
            ],
            [
                "ANY4001,DIST4001,500,ANY,2026-04-04",
                "ANY4001,DIST4001,500,ANY,2026-04-04",
                "ANY4001,DIST4001,500,ANY,2026-04-04",
            ],
            ["2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["keg_type"] for row in rows] == ["HALF", "SIXTH", ""]
        assert summary == {"matched_count": 2, "matched_amount_cents": 1000, "unmatched_count": 1, "unmatched_amount_cents": 500}

    def test_non_any_still_requires_exact_canonical_keg_type_under_config_policy(self):
        """Config policy must not turn named keg type deposits into wildcard matches."""
        write_methods(["HALF,true,1", "SIXTH,true,2", "CORNELIUS,true,3"])
        write_inputs(
            ["CFG5001,DIST5001,900,RETURNED,HALF,2026-04-10"],
            ["CFG5001,DIST5001,900,SIX,2026-04-05"],
            ["2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["keg_type"] == ""
        assert summary["unmatched_amount_cents"] == 900
