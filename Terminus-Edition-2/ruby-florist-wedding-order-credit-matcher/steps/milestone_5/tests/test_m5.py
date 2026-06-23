"""Milestone 5 verifier tests for couple daily budget-gated florist credits."""

import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "orders.csv"
ACTIONS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
METHODS = APP / "config" / "methods.csv"
LIMITS = APP / "config" / "couple_limits.csv"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"


def write_inputs(source_rows, action_rows, calendar_rows, method_rows, limit_rows, dated=True):
    """Replace all runtime inputs for one couple-limit scenario."""
    source_header = "order_id,couple_id,amount_cents,status,arrangement" + (",delivery_date" if dated else "")
    action_header = "order_id,couple_id,amount_cents,arrangement" + (",credit_date" if dated else "")
    SOURCE.write_text(source_header + "\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text(action_header + "\n" + "\n".join(action_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    METHODS.write_text("arrangement,enabled\n" + "\n".join(method_rows) + "\n")
    LIMITS.write_text("couple_id,arrangement,effective_date,max_daily_amount,status\n" + "\n".join(limit_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the Ruby batch and return parsed outputs."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


def test_latest_effective_limit_wins_and_daily_budget_is_consumed_in_credit_order():
    """The latest effective active limit should cap same-couple arrangement/date credits cumulatively."""
    write_inputs(
        [
            "LIM5001,CUST5001,600,DELIVERED,CENTERPIECE,2026-06-10",
            "LIM5002,CUST5001,500,DELIVERED,CENTERPIECE,2026-06-10",
            "LIM5003,CUST5001,400,DELIVERED,CENTERPIECE,2026-06-10",
        ],
        [
            "LIM5001,CUST5001,600,CTR,2026-06-05",
            "LIM5002,CUST5001,500,CTR,2026-06-05",
            "LIM5003,CUST5001,400,CTR,2026-06-05",
        ],
        ["2026-06-05 open"],
        ["CENTERPIECE,true"],
        [
            "CUST5001,CTR,2026-05-01,900,ACTIVE",
            "CUST5001,CENTERPIECE,2026-06-01,1100,ACTIVE",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["arrangement"] for row in rows] == ["CENTERPIECE", "CENTERPIECE", ""]
    assert summary == {
        "matched_count": 2,
        "matched_amount_cents": 1100,
        "unmatched_count": 1,
        "unmatched_amount_cents": 400,
    }


def test_budget_is_partitioned_by_couple_arrangement_and_credit_date():
    """Budget consumption should be keyed by couple, canonical arrangement, and credit_date."""
    write_inputs(
        [
            "LIM5101,CUST5101,700,DELIVERED,BOUQUET,2026-06-10",
            "LIM5102,CUST5101,700,DELIVERED,ARCH,2026-06-10",
            "LIM5103,CUST5101,700,DELIVERED,BOUQUET,2026-06-11",
            "LIM5104,CUST5102,700,DELIVERED,BOUQUET,2026-06-10",
        ],
        [
            "LIM5101,CUST5101,700,BQT,2026-06-05",
            "LIM5102,CUST5101,700,ARC,2026-06-05",
            "LIM5103,CUST5101,700,BQT,2026-06-06",
            "LIM5104,CUST5102,700,BQT,2026-06-05",
        ],
        ["2026-06-05 open", "2026-06-06 open"],
        ["BOUQUET,true", "ARCH,true"],
        [
            "CUST5101,BQT,2026-06-01,700,ACTIVE",
            "CUST5101,ARCH,2026-06-01,700,ACTIVE",
            "CUST5102,BOUQUET,2026-06-01,700,ACTIVE",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "MATCHED"]
    assert [row["arrangement"] for row in rows] == ["BOUQUET", "ARCH", "BOUQUET", "BOUQUET"]
    assert summary["matched_count"] == 4
    assert summary["matched_amount_cents"] == 2800


def test_inactive_future_missing_and_malformed_limits_are_ignored():
    """Bad limit rows should not make otherwise valid dated credits eligible."""
    write_inputs(
        [
            "LIM5201,CUST5201,300,DELIVERED,CENTERPIECE,2026-06-10",
            "LIM5202,CUST5202,300,DELIVERED,CENTERPIECE,2026-06-10",
            "LIM5203,CUST5203,300,DELIVERED,CENTERPIECE,2026-06-10",
            "LIM5204,CUST5204,300,DELIVERED,CENTERPIECE,2026-06-10",
            "LIM5205,CUST5205,300,DELIVERED,CENTERPIECE,2026-06-10",
        ],
        [
            "LIM5201,CUST5201,300,CTR,2026-06-05",
            "LIM5202,CUST5202,300,CTR,2026-06-05",
            "LIM5203,CUST5203,300,CTR,2026-06-05",
            "LIM5204,CUST5204,300,CTR,2026-06-05",
            "LIM5205,CUST5205,300,CTR,2026-06-05",
        ],
        ["2026-06-05 open"],
        ["CENTERPIECE,true"],
        [
            "CUST5201,CENTERPIECE,2026-06-01,300,INACTIVE",
            "CUST5202,CENTERPIECE,2026-06-06,300,ACTIVE",
            "CUST5203,CENTERPIECE,2026-06-01,not-number,ACTIVE",
            "CUST5204,BAD,2026-06-01,300,ACTIVE",
            "CUST5205,CTR,2026-06-01,300,ACTIVE",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert [row["arrangement"] for row in rows] == ["", "", "", "", "CENTERPIECE"]
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 300,
        "unmatched_count": 4,
        "unmatched_amount_cents": 1200,
    }


def test_budget_rejection_does_not_consume_order_row_needed_by_later_credit():
    """A credit rejected by budget must not consume the order row for a later eligible credit."""
    write_inputs(
        [
            "LIM5301,CUST5301,900,DELIVERED,CENTERPIECE,2026-06-10",
            "LIM5301,CUST5301,400,DELIVERED,CENTERPIECE,2026-06-10",
        ],
        [
            "LIM5301,CUST5301,900,CTR,2026-06-05",
            "LIM5301,CUST5301,400,CTR,2026-06-05",
        ],
        ["2026-06-05 open"],
        ["CENTERPIECE,true"],
        ["CUST5301,CTR,2026-06-01,500,ACTIVE"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert [row["arrangement"] for row in rows] == ["", "CENTERPIECE"]
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 400,
        "unmatched_count": 1,
        "unmatched_amount_cents": 900,
    }


def test_undated_inputs_keep_milestone_4_behavior_without_budget_limits():
    """When credit_date is absent, couple_limits.csv should not gate matching."""
    write_inputs(
        ["LIM5401,CUST5401,1000,DELIVERED,CENTERPIECE"],
        ["LIM5401,CUST5401,1000,CTR"],
        ["2026-06-05 closed"],
        ["CENTERPIECE,true"],
        [],
        dated=False,
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["arrangement"] == "CENTERPIECE"
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 1000,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
