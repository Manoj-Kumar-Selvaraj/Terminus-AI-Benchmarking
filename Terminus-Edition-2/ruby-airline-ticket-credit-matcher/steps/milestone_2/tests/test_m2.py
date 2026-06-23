
"""Verifier tests for the Ruby airline reconciliation CLI."""
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


def write_inputs(source_rows, action_rows, calendar_rows=None, dated=False):
    """Replace CSV inputs and optional calendar with a focused scenario."""
    source_header = "ticket_id,traveler_id,amount_cents,status,fare_class" + (",flight_date" if dated else "")
    action_header = "ticket_id,traveler_id,amount_cents,fare_class" + (",credit_date" if dated else "")
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
        ["SRC1001,CUST1001,1200,FLOWN,ECONOMY", "SRC1002,CUST1002,2300,FLOWN,BUSINESS"],
        ["SRC1001,CUST1001,1200,ECONOMY", "SRC1002,CUST1002,2300,BUSINESS"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["fare_class"] == "BUSINESS"
    assert summary["matched_amount_cents"] == 3500


def test_allowed_fare_classes_must_match_exactly():
    """Two different allowed fare classes on the same ticket should not match."""
    write_inputs(
        ["SRC8001,CUST8001,1500,FLOWN,ECONOMY"],
        ["SRC8001,CUST8001,1500,BUSINESS"],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["fare_class"] == ""
    assert summary["matched_count"] == 0
    assert summary["unmatched_amount_cents"] == 1500


def test_full_identifier_matching_rejects_prefix_collision():
    """Only full ticket_id equality should match; shared prefixes are not enough."""
    write_inputs(
        ["PREFIX770001,CUST2001,3300,FLOWN,ECONOMY", "PREFIX770002,CUST2001,3300,FLOWN,ECONOMY"],
        ["PREFIX770003,CUST2001,3300,ECONOMY", "PREFIX770002,CUST2001,3300,ECONOMY"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["fare_class"] == ""
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_dimension_all_gate_matching():
    """Customer, amount, status, and allowed dimension must all gate matching."""
    write_inputs(
        [
            "SRC3001,CUST3001,1000,FLOWN,ECONOMY",
            "SRC3002,CUST3002,2000,FLOWN,BUSINESS",
            "SRC3003,CUST3003,3000,DRAFT,FIRST",
            "SRC3004,CUST3004,4000,FLOWN,CHECK",
            "SRC3005,CUST3005,5000,FLOWN,FIRST",
        ],
        [
            "SRC3001,CUST9999,1000,ECONOMY",
            "SRC3002,CUST3002,2100,BUSINESS",
            "SRC3003,CUST3003,3000,FIRST",
            "SRC3004,CUST3004,4000,CHECK",
            "SRC3005,CUST3005,5000,FIRST",
        ],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["fare_class"] == "FIRST"
    assert summary["matched_count"] == 1
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_actions_do_not_reuse_consumed_source_row():
    """Duplicate actions should not consume the same source row twice."""
    write_inputs(
        ["SRC4001,CUST4001,5500,FLOWN,BUSINESS"],
        ["SRC4001,CUST4001,5500,BUSINESS", "SRC4001,CUST4001,5500,BUSINESS"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert summary["matched_count"] == 1
    assert summary["unmatched_count"] == 1


def test_trimming_and_case_normalization_are_applied():
    """Fields should be trimmed and status/dimension comparisons should be case-insensitive."""
    write_inputs(
        [" SRC5001 , CUST5001 , 6600 , flown , business "],
        [" SRC5001 , CUST5001 , 6600 , BUSINESS "],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["fare_class"] == "BUSINESS"
    assert summary["matched_amount_cents"] == 6600


def test_report_schema_order_and_blank_unmatched_dimension():
    """Report schema, action input order, and blank unmatched dimension should be stable."""
    write_inputs(
        ["SRC6002,CUST6002,1200,FLOWN,ECONOMY", "SRC6001,CUST6001,1100,FLOWN,BUSINESS"],
        ["SRC6001,CUST6001,1100,BUSINESS", "NO_MATCH,CUST9999,9900,ECONOMY", "SRC6002,CUST6002,1200,ECONOMY"],
    )
    rows, summary = run_program()
    assert list(rows[0].keys()) == ["ticket_id", "traveler_id", "fare_class", "amount_cents", "status"]
    assert [row["ticket_id"] for row in rows] == ["SRC6001", "NO_MATCH", "SRC6002"]
    assert rows[1]["fare_class"] == ""
    assert summary == {"matched_count": 2, "matched_amount_cents": 2300, "unmatched_count": 1, "unmatched_amount_cents": 9900}


def test_all_legacy_aliases_match_and_emit_canonical_values():
    """Every documented legacy alias should normalize and emit canonical values."""
    write_inputs(
        [
            "ALIAS7001,CUST7001,3100,FLOWN,ECONOMY",
            "ALIAS7002,CUST7002,3200,FLOWN,BUSINESS",
            "ALIAS7003,CUST7003,3300,FLOWN,FIRST",
            "ALIAS7004,CUST7004,3400,FLOWN,CHECK",
        ],
        [
            "ALIAS7001,CUST7001,3100,eco",
            "ALIAS7002,CUST7002,3200,BIZ",
            "ALIAS7003,CUST7003,3300,FST",
            "ALIAS7004,CUST7004,3400,UNKNOWN",
        ],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["fare_class"] for row in rows] == ["ECONOMY", "BUSINESS", "FIRST", ""]
    assert summary["matched_amount_cents"] == 9600
    assert summary["unmatched_amount_cents"] == 3400


def test_alias_normalization_does_not_skip_exact_fare_class_gate():
    """A normalized alias must still equal the source fare class to match."""
    write_inputs(
        ["ALIAS8101,CUST8101,4100,FLOWN,ECONOMY"],
        ["ALIAS8101,CUST8101,4100,BIZ"],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["fare_class"] == ""
    assert summary == {
        "matched_count": 0,
        "matched_amount_cents": 0,
        "unmatched_count": 1,
        "unmatched_amount_cents": 4100,
    }
