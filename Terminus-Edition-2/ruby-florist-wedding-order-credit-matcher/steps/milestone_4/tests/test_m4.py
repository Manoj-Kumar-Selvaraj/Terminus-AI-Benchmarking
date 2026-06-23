"""Milestone 4 verifier tests for method-gated florist wedding order credits."""

import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "orders.csv"
ACTIONS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
METHODS = APP / "config" / "methods.csv"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"


def write_inputs(source_rows, action_rows, calendar_rows, method_rows, dated=True):
    """Replace order, credit, calendar, and method inputs for one scenario."""
    source_header = "order_id,couple_id,amount_cents,status,arrangement" + (",delivery_date" if dated else "")
    action_header = "order_id,couple_id,amount_cents,arrangement" + (",credit_date" if dated else "")
    SOURCE.write_text(source_header + "\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text(action_header + "\n" + "\n".join(action_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    METHODS.write_text("arrangement,enabled\n" + "\n".join(method_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the Ruby batch and return parsed outputs."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


def test_methods_gate_allows_alias_enabled_centerpiece_and_blocks_disabled_arch():
    """Method aliases should enable canonical arrangements while disabled rows reject valid credits."""
    write_inputs(
        [
            "METH4001,CUST4001,1000,DELIVERED,CENTERPIECE,2026-05-10",
            "METH4002,CUST4002,2000,DELIVERED,ARCH,2026-05-10",
            "METH4003,CUST4003,3000,DELIVERED,BOUQUET,2026-05-10",
        ],
        [
            "METH4001,CUST4001,1000,CTR,2026-05-05",
            "METH4002,CUST4002,2000,ARC,2026-05-05",
            "METH4003,CUST4003,3000,bqt,2026-05-05",
        ],
        ["2026-05-05 open"],
        [" ctr , TRUE", "ARCH,false", "BOUQUET,true"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert [row["arrangement"] for row in rows] == ["CENTERPIECE", "", "BOUQUET"]
    assert summary == {
        "matched_count": 2,
        "matched_amount_cents": 4000,
        "unmatched_count": 1,
        "unmatched_amount_cents": 2000,
    }


def test_missing_nontrue_blank_and_unknown_method_rows_do_not_enable_arrangements():
    """Only recognized canonical arrangements with enabled=true should pass the method gate."""
    write_inputs(
        [
            "METH4101,CUST4101,1100,DELIVERED,CENTERPIECE,2026-05-12",
            "METH4102,CUST4102,1200,DELIVERED,ARCH,2026-05-12",
            "METH4103,CUST4103,1300,DELIVERED,BOUQUET,2026-05-12",
        ],
        [
            "METH4101,CUST4101,1100,CTR,2026-05-06",
            "METH4102,CUST4102,1200,ARC,2026-05-06",
            "METH4103,CUST4103,1300,BQT,2026-05-06",
        ],
        ["2026-05-06 open"],
        ["CENTERPIECE,maybe", "ARCH", ",true", "BAD,true", "BOUQUET,TRUE"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "MATCHED"]
    assert [row["arrangement"] for row in rows] == ["", "", "BOUQUET"]
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 1300,
        "unmatched_count": 2,
        "unmatched_amount_cents": 2300,
    }


def test_methods_gate_preserves_latest_delivery_date_and_row_consumption():
    """Enabled methods should not weaken latest delivery_date selection or per-row consumption."""
    write_inputs(
        [
            "METH4201,CUST4201,1400,DELIVERED,CENTERPIECE,2026-05-08",
            "METH4201,CUST4201,1400,DELIVERED,CENTERPIECE,2026-05-14",
            "METH4201,CUST4201,1400,DELIVERED,CENTERPIECE,2026-05-14",
        ],
        [
            "METH4201,CUST4201,1400,CTR,2026-05-07",
            "METH4201,CUST4201,1400,CTR,2026-05-07",
            "METH4201,CUST4201,1400,CTR,2026-05-07",
            "METH4201,CUST4201,1400,CTR,2026-05-07",
        ],
        ["2026-05-07 open"],
        ["CENTERPIECE,true"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["arrangement"] for row in rows] == ["CENTERPIECE", "CENTERPIECE", "CENTERPIECE", ""]
    assert summary["matched_count"] == 3
    assert summary["unmatched_amount_cents"] == 1400


def test_enabled_method_does_not_bypass_closed_calendar_date():
    """A method-enabled arrangement must still fail when the credit date is not open."""
    write_inputs(
        ["METH4301,CUST4301,1500,DELIVERED,CENTERPIECE,2026-05-15"],
        ["METH4301,CUST4301,1500,CTR,2026-05-09"],
        ["2026-05-09 closed"],
        ["CENTERPIECE,true"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["arrangement"] == ""
    assert summary == {
        "matched_count": 0,
        "matched_amount_cents": 0,
        "unmatched_count": 1,
        "unmatched_amount_cents": 1500,
    }
