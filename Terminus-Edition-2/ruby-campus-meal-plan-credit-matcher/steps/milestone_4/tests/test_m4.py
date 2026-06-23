"""Milestone 4 verifier tests for method-gated campus meal plan credits."""

import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "plans.csv"
ACTIONS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
METHODS = APP / "config" / "methods.csv"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"
CONSUMPTION = APP / "out" / "plan_consumption.csv"


def write_inputs(source_rows, action_rows, calendar_rows, method_rows, dated=True):
    """Replace plan, credit, calendar, and method inputs for one scenario."""
    source_header = "plan_id,student_id,amount_cents,status,location" + (",cycle_end" if dated else "")
    action_header = "plan_id,student_id,amount_cents,location" + (",credit_date" if dated else "")
    SOURCE.write_text(source_header + "\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text(action_header + "\n" + "\n".join(action_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    METHODS.write_text("location,enabled\n" + "\n".join(method_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)
    CONSUMPTION.unlink(missing_ok=True)


def run_program():
    """Run the Ruby batch and return parsed outputs."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


def read_consumption():
    """Return physical plan-row selections emitted for matched credits."""
    with CONSUMPTION.open(newline="") as handle:
        return list(csv.DictReader(handle))


def test_methods_gate_allows_alias_enabled_location_and_blocks_disabled_market():
    """Method aliases should enable canonical locations while disabled rows reject otherwise valid credits."""
    write_inputs(
        [
            "METH4001,CUST4001,1000,ACTIVE,CAFE,2026-05-10",
            "METH4002,CUST4002,2000,ACTIVE,MARKET,2026-05-10",
            "METH4003,CUST4003,3000,ACTIVE,DINING,2026-05-10",
        ],
        [
            "METH4001,CUST4001,1000,CAF,2026-05-05",
            "METH4002,CUST4002,2000,MKT,2026-05-05",
            "METH4003,CUST4003,3000,din,2026-05-05",
        ],
        ["2026-05-05 open"],
        [" caf , TRUE", "MARKET,false", "DINING,true"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert [row["location"] for row in rows] == ["CAFE", "", "DINING"]
    assert summary == {
        "matched_count": 2,
        "matched_amount_cents": 4000,
        "unmatched_count": 1,
        "unmatched_amount_cents": 2000,
    }


def test_missing_nontrue_blank_and_unknown_method_rows_do_not_enable_locations():
    """Only recognized canonical locations with enabled=true should pass the method gate."""
    write_inputs(
        [
            "METH4101,CUST4101,1100,ACTIVE,CAFE,2026-05-12",
            "METH4102,CUST4102,1200,ACTIVE,MARKET,2026-05-12",
            "METH4103,CUST4103,1300,ACTIVE,DINING,2026-05-12",
        ],
        [
            "METH4101,CUST4101,1100,CAF,2026-05-06",
            "METH4102,CUST4102,1200,MKT,2026-05-06",
            "METH4103,CUST4103,1300,DIN,2026-05-06",
        ],
        ["2026-05-06 open"],
        ["CAFE,maybe", "MARKET", ",true", "BAD,true", "DINING,TRUE"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "MATCHED"]
    assert [row["location"] for row in rows] == ["", "", "DINING"]
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 1300,
        "unmatched_count": 2,
        "unmatched_amount_cents": 2300,
    }


def test_methods_gate_preserves_latest_cycle_end_and_row_consumption():
    """Enabled methods should not weaken latest cycle_end selection or per-row consumption."""
    write_inputs(
        [
            "METH4201,CUST4201,1400,ACTIVE,CAFE,2026-05-08",
            "METH4201,CUST4201,1400,ACTIVE,CAFE,2026-05-14",
            "METH4201,CUST4201,1400,ACTIVE,CAFE,2026-05-14",
        ],
        [
            "METH4201,CUST4201,1400,CAF,2026-05-07",
            "METH4201,CUST4201,1400,CAF,2026-05-07",
            "METH4201,CUST4201,1400,CAF,2026-05-07",
            "METH4201,CUST4201,1400,CAF,2026-05-07",
        ],
        ["2026-05-07 open"],
        ["CAFE,true"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["location"] for row in rows] == ["CAFE", "CAFE", "CAFE", ""]
    assert summary["matched_count"] == 3
    assert summary["unmatched_amount_cents"] == 1400
    assert [row["plan_row"] for row in read_consumption()] == ["1", "2", "0"]


def test_enabled_method_does_not_bypass_closed_calendar_date():
    """A method-enabled location must still fail when the credit date is not open."""
    write_inputs(
        ["METH4301,CUST4301,1500,ACTIVE,CAFE,2026-05-15"],
        ["METH4301,CUST4301,1500,CAF,2026-05-09"],
        ["2026-05-09 closed"],
        ["CAFE,true"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["location"] == ""
    assert summary == {
        "matched_count": 0,
        "matched_amount_cents": 0,
        "unmatched_count": 1,
        "unmatched_amount_cents": 1500,
    }


def test_all_method_location_aliases_are_trimmed_case_folded_and_enabled():
    """DIN, CAF, and MKT method aliases should all enable their canonical locations."""
    write_inputs(
        [
            "METH4401,CUST4401,400,ACTIVE,DINING,2026-05-15",
            "METH4402,CUST4402,500,ACTIVE,CAFE,2026-05-15",
            "METH4403,CUST4403,600,ACTIVE,MARKET,2026-05-15",
        ],
        [
            "METH4401,CUST4401,400,DIN,2026-05-10",
            "METH4402,CUST4402,500,CAF,2026-05-10",
            "METH4403,CUST4403,600,MKT,2026-05-10",
        ],
        ["2026-05-10 open"],
        [" din ,TrUe", " caf ,TRUE", " mkt ,true"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["location"] for row in rows] == ["DINING", "CAFE", "MARKET"]
    assert summary["matched_amount_cents"] == 1500
