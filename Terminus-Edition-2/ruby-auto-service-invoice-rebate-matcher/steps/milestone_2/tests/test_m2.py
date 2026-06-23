
"""Verifier tests for the Ruby auto-service reconciliation CLI."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "invoices.csv"
ACTIONS = APP / "data" / "rebates.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "rebate_report.csv"
SUMMARY = APP / "out" / "rebate_summary.json"


def write_inputs(source_rows, action_rows, calendar_rows=None, dated=False):
    """Replace CSV inputs and optional calendar with a focused scenario."""
    source_header = "invoice_id,vehicle_id,amount_cents,status,bay" + (",service_date" if dated else "")
    action_header = "invoice_id,vehicle_id,amount_cents,bay" + (",rebate_date" if dated else "")
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


def test_middle_value_matches_and_counts_positive_amount():
    """The middle allowed value should match and matched totals should be positive."""
    write_inputs(
        ["SRC1001,CUST1001,1200,CLOSED,EXPRESS", "SRC1002,CUST1002,2300,CLOSED,STANDARD"],
        ["SRC1001,CUST1001,1200,EXPRESS", "SRC1002,CUST1002,2300,STANDARD"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["bay"] == "STANDARD"
    assert summary["matched_amount_cents"] == 3500


def test_full_identifier_matching_rejects_prefix_collision():
    """Only full invoice_id equality should match; shared prefixes are not enough."""
    write_inputs(
        ["PREFIX770001,CUST2001,3300,CLOSED,EXPRESS", "PREFIX770002,CUST2001,3300,CLOSED,EXPRESS"],
        ["PREFIX770003,CUST2001,3300,EXPRESS", "PREFIX770002,CUST2001,3300,EXPRESS"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["bay"] == ""
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_dimension_all_gate_matching():
    """Customer, amount, status, and allowed dimension must all gate matching."""
    write_inputs(
        [
            "SRC3001,CUST3001,1000,CLOSED,EXPRESS",
            "SRC3002,CUST3002,2000,CLOSED,STANDARD",
            "SRC3003,CUST3003,3000,DRAFT,DETAIL",
            "SRC3004,CUST3004,4000,CLOSED,CHECK",
            "SRC3005,CUST3005,5000,CLOSED,DETAIL",
        ],
        [
            "SRC3001,CUST9999,1000,EXPRESS",
            "SRC3002,CUST3002,2100,STANDARD",
            "SRC3003,CUST3003,3000,DETAIL",
            "SRC3004,CUST3004,4000,CHECK",
            "SRC3005,CUST3005,5000,DETAIL",
        ],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["bay"] == "DETAIL"
    assert summary["matched_count"] == 1
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_actions_do_not_reuse_consumed_source_row():
    """Duplicate actions should not consume the same source row twice."""
    write_inputs(
        ["SRC4001,CUST4001,5500,CLOSED,STANDARD"],
        ["SRC4001,CUST4001,5500,STANDARD", "SRC4001,CUST4001,5500,STANDARD"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert summary["matched_count"] == 1
    assert summary["unmatched_count"] == 1


def test_trimming_and_case_normalization_are_applied():
    """Fields should be trimmed and status/dimension comparisons should be case-insensitive."""
    write_inputs(
        [" SRC5001 , CUST5001 , 6600 , closed , standard "],
        [" SRC5001 , CUST5001 , 6600 , STANDARD "],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["bay"] == "STANDARD"
    assert summary["matched_amount_cents"] == 6600


def test_report_schema_order_and_blank_unmatched_dimension():
    """Report schema, action input order, and blank unmatched dimension should be stable."""
    write_inputs(
        ["SRC6002,CUST6002,1200,CLOSED,EXPRESS", "SRC6001,CUST6001,1100,CLOSED,STANDARD"],
        ["SRC6001,CUST6001,1100,STANDARD", "NO_MATCH,CUST9999,9900,EXPRESS", "SRC6002,CUST6002,1200,EXPRESS"],
    )
    rows, summary = run_program()
    assert list(rows[0].keys()) == ["invoice_id", "vehicle_id", "bay", "amount_cents", "status"]
    assert [row["invoice_id"] for row in rows] == ["SRC6001", "NO_MATCH", "SRC6002"]
    assert rows[1]["bay"] == ""
    assert summary == {"matched_count": 2, "matched_amount_cents": 2300, "unmatched_count": 1, "unmatched_amount_cents": 9900}


def test_all_legacy_aliases_match_and_emit_canonical_values():
    """Every documented legacy alias should normalize and emit canonical values."""
    write_inputs(
        [
            "ALIAS7001,CUST7001,3100,CLOSED,EXPRESS",
            "ALIAS7002,CUST7002,3200,CLOSED,STANDARD",
            "ALIAS7003,CUST7003,3300,CLOSED,DETAIL",
            "ALIAS7004,CUST7004,3400,CLOSED,CHECK",
        ],
        [
            "ALIAS7001,CUST7001,3100,exp",
            "ALIAS7002,CUST7002,3200,STD",
            "ALIAS7003,CUST7003,3300,DTL",
            "ALIAS7004,CUST7004,3400,UNKNOWN",
        ],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["bay"] for row in rows] == ["EXPRESS", "STANDARD", "DETAIL", ""]
    assert summary["matched_amount_cents"] == 9600
    assert summary["unmatched_amount_cents"] == 3400
