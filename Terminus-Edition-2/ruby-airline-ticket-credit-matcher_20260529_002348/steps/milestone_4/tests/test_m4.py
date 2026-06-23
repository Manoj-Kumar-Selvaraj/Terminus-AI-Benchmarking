"""Milestone 4 verifier tests for methods.csv fare-class eligibility."""

import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "tickets.csv"
ACTIONS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"
METHODS = APP / "config" / "methods.csv"


def write_inputs(source_rows, action_rows, calendar_rows=None, dated=False, methods_rows=None):
    """Write focused CSV inputs plus optional calendar and methods config."""
    source_header = "ticket_id,traveler_id,amount_cents,status,fare_class" + (",flight_date" if dated else "")
    action_header = "ticket_id,traveler_id,amount_cents,fare_class" + (",credit_date" if dated else "")
    SOURCE.write_text(source_header + "\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text(action_header + "\n" + "\n".join(action_rows) + "\n")
    if calendar_rows is not None:
        CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    if methods_rows is not None:
        METHODS.write_text("fare_class,enabled\n" + "\n".join(methods_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the Ruby batch and return parsed report and summary outputs."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


def test_methods_gate_blocks_disabled_class_in_undated_mode():
    """Undated credits must not match when methods.csv marks the canonical class false."""
    write_inputs(
        ["M41001,CUST1,900,FLOWN,FIRST"],
        ["M41001,CUST1,900,FST"],
        methods_rows=["ECONOMY,true", "BUSINESS,true", "FIRST,false"],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["fare_class"] == ""
    assert summary["matched_count"] == 0


def test_methods_gate_blocks_missing_class_mapping():
    """A canonical fare class absent from methods.csv must be treated as disabled."""
    write_inputs(
        ["M42001,CUST2,1000,FLOWN,BUSINESS"],
        ["M42001,CUST2,1000,BIZ"],
        methods_rows=["ECONOMY,true", "FIRST,true"],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert summary["unmatched_amount_cents"] == 1000


def test_methods_gate_allows_trimmed_case_insensitive_true():
    """Whitespace-padded TRUE in methods.csv must enable the canonical fare class."""
    write_inputs(
        ["M43001,CUST3,1100,FLOWN,BUSINESS,2026-04-10"],
        ["M43001,CUST3,1100,BIZ,2026-04-05"],
        ["2026-04-05 open"],
        dated=True,
        methods_rows=[" BUSINESS , TRUE "],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["fare_class"] == "BUSINESS"
    assert summary["matched_count"] == 1


def test_methods_file_reload_respects_runtime_changes():
    """Each batch run must reload methods.csv and honor updated enabled flags."""
    write_inputs(
        ["M44001,CUST4,1200,FLOWN,ECONOMY"],
        ["M44001,CUST4,1200,ECO"],
        methods_rows=["ECONOMY,false"],
    )
    rows, _ = run_program()
    assert rows[0]["status"] == "UNMATCHED"

    write_inputs(
        ["M44001,CUST4,1200,FLOWN,ECONOMY"],
        ["M44001,CUST4,1200,ECO"],
        methods_rows=["ECONOMY,true"],
    )
    rows, _ = run_program()
    assert rows[0]["status"] == "MATCHED"


def test_methods_gate_ignores_malformed_rows():
    """Malformed methods.csv rows must not enable a fare class by accident."""
    write_inputs(
        ["M45001,CUST5,1300,FLOWN,FIRST"],
        ["M45001,CUST5,1300,FST"],
        methods_rows=["FIRST", "BROKENROW", "ECONOMY,yes"],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["fare_class"] == ""
    assert summary["matched_count"] == 0
