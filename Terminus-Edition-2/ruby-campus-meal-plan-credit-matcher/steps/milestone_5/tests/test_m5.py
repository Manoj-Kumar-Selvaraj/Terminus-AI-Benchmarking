"""Milestone 5 verifier tests for student daily budget-gated meal plan credits."""

import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "plans.csv"
ACTIONS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
METHODS = APP / "config" / "methods.csv"
LIMITS = APP / "config" / "student_limits.csv"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"
CONSUMPTION = APP / "out" / "plan_consumption.csv"


def write_inputs(source_rows, action_rows, calendar_rows, method_rows, limit_rows, dated=True):
    """Replace all runtime inputs for one student-limit scenario."""
    source_header = "plan_id,student_id,amount_cents,status,location" + (",cycle_end" if dated else "")
    action_header = "plan_id,student_id,amount_cents,location" + (",credit_date" if dated else "")
    SOURCE.write_text(source_header + "\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text(action_header + "\n" + "\n".join(action_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    METHODS.write_text("location,enabled\n" + "\n".join(method_rows) + "\n")
    LIMITS.write_text("student_id,location,effective_date,max_daily_amount,status\n" + "\n".join(limit_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)
    CONSUMPTION.unlink(missing_ok=True)


def run_program():
    """Run the Ruby batch and return parsed outputs."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


def test_latest_effective_limit_wins_and_daily_budget_is_consumed_in_credit_order():
    """The latest effective active limit should cap same-student/location/date credits cumulatively."""
    write_inputs(
        [
            "LIM5001,CUST5001,600,ACTIVE,CAFE,2026-06-10",
            "LIM5002,CUST5001,500,ACTIVE,CAFE,2026-06-10",
            "LIM5003,CUST5001,400,ACTIVE,CAFE,2026-06-10",
        ],
        [
            "LIM5001,CUST5001,600,CAF,2026-06-05",
            "LIM5002,CUST5001,500,CAF,2026-06-05",
            "LIM5003,CUST5001,400,CAF,2026-06-05",
        ],
        ["2026-06-05 open"],
        ["CAFE,true"],
        [
            "CUST5001,CAF,2026-05-01,900,ACTIVE",
            "CUST5001,CAFE,2026-06-01,1100,ACTIVE",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["location"] for row in rows] == ["CAFE", "CAFE", ""]
    assert summary == {
        "matched_count": 2,
        "matched_amount_cents": 1100,
        "unmatched_count": 1,
        "unmatched_amount_cents": 400,
    }


def test_budget_is_partitioned_by_student_location_and_credit_date():
    """Budget consumption should be keyed by student, canonical location, and credit_date."""
    write_inputs(
        [
            "LIM5101,CUST5101,700,ACTIVE,DINING,2026-06-10",
            "LIM5102,CUST5101,700,ACTIVE,MARKET,2026-06-10",
            "LIM5103,CUST5101,700,ACTIVE,DINING,2026-06-11",
            "LIM5104,CUST5102,700,ACTIVE,DINING,2026-06-10",
        ],
        [
            "LIM5101,CUST5101,700,DIN,2026-06-05",
            "LIM5102,CUST5101,700,MKT,2026-06-05",
            "LIM5103,CUST5101,700,DIN,2026-06-06",
            "LIM5104,CUST5102,700,DIN,2026-06-05",
        ],
        ["2026-06-05 open", "2026-06-06 open"],
        ["DINING,true", "MARKET,true"],
        [
            "CUST5101,DIN,2026-06-01,700,ACTIVE",
            "CUST5101,MKT,2026-06-01,700,ACTIVE",
            "CUST5102,DINING,2026-06-01,700,ACTIVE",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "MATCHED"]
    assert [row["location"] for row in rows] == ["DINING", "MARKET", "DINING", "DINING"]
    assert summary["matched_count"] == 4
    assert summary["matched_amount_cents"] == 2800


def test_inactive_future_missing_and_malformed_limits_are_ignored():
    """Bad limit rows should not make otherwise valid dated credits eligible."""
    write_inputs(
        [
            "LIM5201,CUST5201,300,ACTIVE,CAFE,2026-06-10",
            "LIM5202,CUST5202,300,ACTIVE,CAFE,2026-06-10",
            "LIM5203,CUST5203,300,ACTIVE,CAFE,2026-06-10",
            "LIM5204,CUST5204,300,ACTIVE,CAFE,2026-06-10",
            "LIM5205,CUST5205,300,ACTIVE,CAFE,2026-06-10",
        ],
        [
            "LIM5201,CUST5201,300,CAF,2026-06-05",
            "LIM5202,CUST5202,300,CAF,2026-06-05",
            "LIM5203,CUST5203,300,CAF,2026-06-05",
            "LIM5204,CUST5204,300,CAF,2026-06-05",
            "LIM5205,CUST5205,300,CAF,2026-06-05",
        ],
        ["2026-06-05 open"],
        ["CAFE,true"],
        [
            "CUST5201,CAFE,2026-06-01,300,INACTIVE",
            "CUST5202,CAFE,2026-06-06,300,ACTIVE",
            "CUST5203,CAFE,2026-06-01,not-number,ACTIVE",
            "CUST5204,BAD,2026-06-01,300,ACTIVE",
            "CUST5205,CAF,2026-06-01,300,ACTIVE",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert [row["location"] for row in rows] == ["", "", "", "", "CAFE"]
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 300,
        "unmatched_count": 4,
        "unmatched_amount_cents": 1200,
    }


def test_budget_rejection_does_not_consume_plan_row_needed_by_later_credit():
    """A credit rejected by budget must not consume the plan row for a later eligible credit."""
    write_inputs(
        [
            "LIM5301,CUST5301,900,ACTIVE,CAFE,2026-06-10",
            "LIM5301,CUST5301,400,ACTIVE,CAFE,2026-06-10",
        ],
        [
            "LIM5301,CUST5301,900,CAF,2026-06-05",
            "LIM5301,CUST5301,400,CAF,2026-06-05",
        ],
        ["2026-06-05 open"],
        ["CAFE,true"],
        ["CUST5301,CAF,2026-06-01,500,ACTIVE"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert [row["location"] for row in rows] == ["", "CAFE"]
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 400,
        "unmatched_count": 1,
        "unmatched_amount_cents": 900,
    }


def test_same_effective_date_tie_uses_earliest_limit_row():
    """When effective_date ties, the earliest limit input row must be authoritative."""
    write_inputs(
        ["LIM5501,CUST5501,1000,ACTIVE,CAFE,2026-06-10"],
        ["LIM5501,CUST5501,1000,CAF,2026-06-05"],
        ["2026-06-05 open"],
        ["CAFE,true"],
        [
            "CUST5501, caf ,2026-06-01,900,ACTIVE",
            "CUST5501,CAFE,2026-06-01,1100,ACTIVE",
        ],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["location"] == ""
    assert summary == {
        "matched_count": 0,
        "matched_amount_cents": 0,
        "unmatched_count": 1,
        "unmatched_amount_cents": 1000,
    }


def test_undated_inputs_keep_milestone_4_behavior_without_budget_limits():
    """When credit_date is absent, student_limits.csv should not gate matching."""
    write_inputs(
        ["LIM5401,CUST5401,1000,ACTIVE,CAFE"],
        ["LIM5401,CUST5401,1000,CAF"],
        ["2026-06-05 closed"],
        ["CAFE,true"],
        [],
        dated=False,
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["location"] == "CAFE"
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 1000,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
