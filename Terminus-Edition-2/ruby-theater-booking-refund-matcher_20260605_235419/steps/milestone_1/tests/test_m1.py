"""Verifier tests for the Ruby theater reconciliation CLI."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "bookings.csv"
ACTIONS = APP / "data" / "refunds.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "refund_report.csv"
SUMMARY = APP / "out" / "refund_summary.json"


def write_inputs(source_rows, action_rows, calendar_rows=None, dated=False):
    """Replace CSV inputs and optional calendar with a focused scenario."""
    source_header = "booking_id,patron_id,amount_cents,status,seat_zone" + (",show_date" if dated else "")
    action_header = "booking_id,patron_id,amount_cents,seat_zone" + (",refund_date" if dated else "")
    SOURCE.write_text(source_header + "\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text(action_header + "\n" + "\n".join(action_rows) + "\n")
    if calendar_rows is not None:
        CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the Ruby batch and return parsed report and summary outputs."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


def test_middle_value_matches_and_counts_positive_amount():
    """The middle allowed value should match and matched totals should be positive."""
    write_inputs(
        ["SRC1001,CUST1001,1200,TICKETED,ORCH", "SRC1002,CUST1002,2300,TICKETED,MEZZ"],
        ["SRC1001,CUST1001,1200,ORCH", "SRC1002,CUST1002,2300,MEZZ"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["seat_zone"] == "MEZZ"
    assert summary["matched_amount_cents"] == 3500


def test_full_identifier_matching_rejects_prefix_collision():
    """Only full booking_id equality should match; shared prefixes are not enough."""
    write_inputs(
        ["PREFIX770001,CUST2001,3300,TICKETED,ORCH", "PREFIX770002,CUST2001,3300,TICKETED,ORCH"],
        ["PREFIX770003,CUST2001,3300,ORCH", "PREFIX770002,CUST2001,3300,ORCH"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["seat_zone"] == ""
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_allowed_seat_zones_must_match_exactly():
    """Two different allowed seat zones on the same booking should not match."""
    write_inputs(
        ["SRC8001,CUST8001,1500,TICKETED,ORCH"],
        ["SRC8001,CUST8001,1500,MEZZ"],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["seat_zone"] == ""
    assert summary["matched_count"] == 0
    assert summary["unmatched_amount_cents"] == 1500


def test_customer_amount_status_and_dimension_all_gate_matching():
    """Customer, amount, status, and allowed dimension must all gate matching."""
    write_inputs(
        [
            "SRC3001,CUST3001,1000,TICKETED,ORCH",
            "SRC3002,CUST3002,2000,TICKETED,MEZZ",
            "SRC3003,CUST3003,3000,DRAFT,BALC",
            "SRC3004,CUST3004,4000,TICKETED,CHECK",
            "SRC3005,CUST3005,5000,TICKETED,BALC",
        ],
        [
            "SRC3001,CUST9999,1000,ORCH",
            "SRC3002,CUST3002,2100,MEZZ",
            "SRC3003,CUST3003,3000,BALC",
            "SRC3004,CUST3004,4000,CHECK",
            "SRC3005,CUST3005,5000,BALC",
        ],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["seat_zone"] == "BALC"
    assert summary["matched_count"] == 1
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_actions_do_not_reuse_consumed_source_row():
    """Duplicate actions should not consume the same source row twice."""
    write_inputs(
        ["SRC4001,CUST4001,5500,TICKETED,MEZZ"],
        ["SRC4001,CUST4001,5500,MEZZ", "SRC4001,CUST4001,5500,MEZZ"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert summary["matched_count"] == 1
    assert summary["unmatched_count"] == 1


def test_trimming_and_case_normalization_are_applied():
    """Fields should be trimmed and status/dimension comparisons should be case-insensitive."""
    write_inputs(
        ["SRC5001,CUST5001,6600,ticketed,mezz"],
        [" SRC5001 ,  CUST5001   , 6600 , MEZZ "],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["seat_zone"] == "MEZZ"
    assert summary["matched_amount_cents"] == 6600


def test_report_schema_order_and_blank_unmatched_dimension():
    """Report schema, action input order, and blank unmatched dimension should be stable."""
    write_inputs(
        ["SRC6002,CUST6002,1200,TICKETED,ORCH", "SRC6001,CUST6001,1100,TICKETED,MEZZ"],
        ["SRC6001,CUST6001,1100,MEZZ", "NO_MATCH,CUST9999,9900,ORCH", "SRC6002,CUST6002,1200,ORCH"],
    )
    rows, summary = run_program()
    assert list(rows[0].keys()) == ["booking_id", "patron_id", "seat_zone", "amount_cents", "status"]
    assert [row["booking_id"] for row in rows] == ["SRC6001", "NO_MATCH", "SRC6002"]
    assert rows[1]["seat_zone"] == ""
    assert summary == {"matched_count": 2, "matched_amount_cents": 2300, "unmatched_count": 1, "unmatched_amount_cents": 9900}
