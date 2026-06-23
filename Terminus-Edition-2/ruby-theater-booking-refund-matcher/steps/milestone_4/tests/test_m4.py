"""Tests for methods-config-gated theater refunds."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "bookings.csv"
ACTIONS = APP / "data" / "refunds.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
METHODS = APP / "config" / "methods.csv"
REPORT = APP / "out" / "refund_report.csv"
SUMMARY = APP / "out" / "refund_summary.json"


def write_inputs(source_rows, action_rows, calendar_rows, methods_rows, dated=True):
    """Replace input data and config with a focused scenario."""
    source_header = "booking_id,patron_id,amount_cents,status,seat_zone" + (",show_date" if dated else "")
    action_header = "booking_id,patron_id,amount_cents,seat_zone" + (",refund_date" if dated else "")
    SOURCE.write_text(source_header + "\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text(action_header + "\n" + "\n".join(action_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    METHODS.write_text("fund,enabled\n" + "\n".join(methods_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run ruby batch and parse report and summary."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


def test_enabled_mapping_required_after_alias_normalization():
    """ORCH/MEZZ/BALC should map to GENERAL/CAPITAL/RELIEF methods flags."""
    write_inputs(
        [
            "T4101,P4101,1000,TICKETED,ORCH,2026-05-08",
            "T4102,P4102,2000,TICKETED,MEZZ,2026-05-08",
            "T4103,P4103,3000,TICKETED,BALC,2026-05-08",
        ],
        [
            "T4101,P4101,1000,ORC,2026-05-05",
            "T4102,P4102,2000,MEZ,2026-05-05",
            "T4103,P4103,3000,BAL,2026-05-05",
        ],
        ["2026-05-05 open", "2026-05-06 open", "2026-05-08 open"],
        ["GENERAL,true", "CAPITAL,false", "RELIEF,true"],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert [r["seat_zone"] for r in rows] == ["ORCH", "", "BALC"]
    assert summary == {
        "matched_count": 2,
        "matched_amount_cents": 4000,
        "unmatched_count": 1,
        "unmatched_amount_cents": 2000,
    }


def test_missing_or_malformed_methods_rows_are_ineligible():
    """Missing and malformed methods entries should not enable a zone."""
    write_inputs(
        ["T4201,P4201,900,TICKETED,MEZZ,2026-05-10"],
        ["T4201,P4201,900,MEZ,2026-05-07"],
        ["2026-05-07 open", "2026-05-08 open", "2026-05-10 open"],
        ["GENERAL,true", "BROKENROW", "CAPITAL,yes"],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["seat_zone"] == ""
    assert summary["matched_count"] == 0
    assert summary["unmatched_amount_cents"] == 900


def test_methods_gate_applies_in_undated_mode():
    """When date columns are absent, methods gate should still block disabled zones."""
    write_inputs(
        ["T4301,P4301,800,TICKETED,ORCH"],
        ["T4301,P4301,800,ORC"],
        ["2026-05-01 open"],
        ["GENERAL,false", "CAPITAL,true", "RELIEF,true"],
        dated=False,
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["seat_zone"] == ""
    assert summary["matched_count"] == 0
    assert summary["unmatched_count"] == 1


def test_methods_gate_does_not_override_date_and_lead_time_rules():
    """Enabled methods cannot bypass closed-calendar or lead-time requirements."""
    write_inputs(
        [
            "T4401,P4401,1200,TICKETED,BALC,2026-06-10",
            "T4402,P4402,1300,TICKETED,ORCH,2026-06-11",
        ],
        [
            "T4401,P4401,1200,BAL,2026-06-09",
            "T4402,P4402,1300,ORC,2026-06-10",
        ],
        ["2026-06-09 closed", "2026-06-10 open", "2026-06-11 open"],
        ["GENERAL,true", "CAPITAL,true", "RELIEF,true"],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["UNMATCHED", "UNMATCHED"]
    assert [r["seat_zone"] for r in rows] == ["", ""]
    assert summary["matched_count"] == 0
    assert summary["unmatched_amount_cents"] == 2500


def test_enabled_field_is_case_insensitive_and_whitespace_tolerant():
    """TRUE, True, and surrounding whitespace should enable methods entries."""
    write_inputs(
        [
            "T4501,P4501,500,TICKETED,ORCH,2026-05-08",
            "T4502,P4502,600,TICKETED,BALC,2026-05-08",
        ],
        [
            "T4501,P4501,500,ORC,2026-05-05",
            "T4502,P4502,600,BAL,2026-05-05",
        ],
        ["2026-05-05 open", "2026-05-06 open", "2026-05-08 open"],
        [" GENERAL , TRUE ", " RELIEF , True "],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert summary["matched_count"] == 2


def test_whitespace_in_fund_column_is_tolerated():
    """Surrounding whitespace around a fund name should not disable its zone."""
    write_inputs(
        ["T4601,P4601,700,TICKETED,MEZZ,2026-05-08"],
        ["T4601,P4601,700,MEZ,2026-05-05"],
        ["2026-05-05 open", "2026-05-06 open", "2026-05-08 open"],
        ["  CAPITAL  ,true"],
    )
    rows, _summary = run_program()
    assert rows[0]["status"] == "MATCHED"


def test_absent_fund_row_disables_zone():
    """A canonical zone with no methods.csv fund row should stay ineligible."""
    write_inputs(
        ["T4701,P4701,900,TICKETED,BALC,2026-05-08"],
        ["T4701,P4701,900,BAL,2026-05-05"],
        ["2026-05-05 open", "2026-05-06 open", "2026-05-08 open"],
        ["GENERAL,true", "CAPITAL,true"],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["seat_zone"] == ""
    assert summary["matched_count"] == 0
    assert summary["unmatched_amount_cents"] == 900

