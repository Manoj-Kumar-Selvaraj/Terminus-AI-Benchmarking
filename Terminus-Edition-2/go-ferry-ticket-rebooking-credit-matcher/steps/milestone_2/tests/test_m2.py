"""Verifier tests for the ticket credit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
TICKETS = APP / "data" / "tickets.csv"
CREDITS = APP / "data" / "credits.csv"
REPORT = APP / "out" / "ticket_credit_report.csv"
SUMMARY = APP / "out" / "ticket_credit_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go reconciliation CLI for the current source tree."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all verifier tests."""
    build_program()


def write_inputs(ticket_rows, credit_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    TICKETS.write_text("ticket_id,rider_id,amount_cents,status,fare_type\n" + "\n".join(ticket_rows) + "\n")
    CREDITS.write_text("ticket_id,rider_id,amount_cents,fare_type\n" + "\n".join(credit_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_bike_credit_matches_and_counts_positive_amount():
    """BIKE credits should match active tickets and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,ACTIVE,ECON",
            "INV20260401002,CUST1002,9900,ACTIVE,BIKE",
        ],
        [
            "INV20260401001,CUST1001,12500,ECON",
            "INV20260401002,CUST1002,9900,BIKE",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["fare_type"] == "BIKE"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_ticket_id_match_uses_full_identifier():
    """A credit must not match a ticket that only shares the leading ticket prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,ACTIVE,ECON",
            "INV777770002,CUST2001,3300,ACTIVE,ECON",
        ],
        [
            "INV777770003,CUST2001,3300,ECON",
            "INV777770002,CUST2001,3300,ECON",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["fare_type"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_fare_type_all_gate_matching():
    """Customer, amount, active status, and allowed fare_type must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,1000,ACTIVE,ECON",
            "INV3002,CUST3002,2000,ACTIVE,BIKE",
            "INV3003,CUST3003,3000,DRAFT,CABIN",
            "INV3004,CUST3004,4000,ACTIVE,CHECK",
            "INV3005,CUST3005,5000,ACTIVE,CABIN",
        ],
        [
            "INV3001,CUST9999,1000,ECON",
            "INV3002,CUST3002,2100,BIKE",
            "INV3003,CUST3003,3000,CABIN",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,CABIN",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["fare_type"] == "CABIN"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_credits_do_not_reuse_consumed_ticket():
    """Only the earliest eligible credit may consume a matching ticket."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,ACTIVE,BIKE",
            "INV5552,CUST5552,8800,ACTIVE,ECON",
        ],
        [
            "INV5551,CUST5551,7500,BIKE",
            "INV5551,CUST5551,7500,BIKE",
            "INV5552,CUST5552,8800,ECON",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["fare_type"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_fare_type_status_case():
    """Matching should tolerate surrounding spaces and case differences in fare_type/status values."""
    write_inputs(
        [
            " INV6601 , CUST6601 , 6100 , active , bike ",
            "INV6602,CUST6602,7200,ACTIVE,cabin",
        ],
        [
            "INV6601,CUST6601, 6100 ,BIKE",
            " INV6602 , CUST6602 ,7200, CABIN ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["ticket_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["rider_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["fare_type"] for row in rows] == ["BIKE", "CABIN"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_legacy_fare_type_aliases_match_and_emit_canonical_fare_types():
    """Legacy EC, BK, and CB credit fare_types should match and report canonical fare_types."""
    write_inputs(
        [
            "INV7701,CUST7701,8800,ACTIVE,BIKE",
            "INV7702,CUST7702,9100,active,cabin",
            "INV7703,CUST7703,4200,ACTIVE,ECON",
            "INV7704,CUST7704,5500,ACTIVE,ECON",
            "INV7705,CUST7705,3300,ACTIVE,CHECK",
        ],
        [
            "INV7701,CUST7701,8800,bk",
            "INV7702,CUST7702,9100,CB",
            "INV7703,CUST7703,4200,ec",
            "INV7704,CUST7704,5500,EC",
            "INV7705,CUST7705,3300,chk",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["fare_type"] for row in rows] == ["BIKE", "CABIN", "ECON", "ECON", ""]
    assert summary["matched_count"] == 4
    assert summary["matched_amount_cents"] == 27600
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 3300


def test_ec_alias_matches_econ_ticket_and_reports_canonical_fare_type():
    """A EC credit must match a ECON ticket and emit ECON as the fare_type."""
    write_inputs(
        ["INV7801,CUST7801,1234,ACTIVE,ECON"],
        ["INV7801,CUST7801,1234,ec"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["fare_type"] == "ECON"
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 1234,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_report_schema_and_credit_input_order_are_stable():
    """The report should use the required schema and preserve credit input order."""
    write_inputs(
        [
            "INV9001,CUST9001,100,ACTIVE,ECON",
            "INV9002,CUST9002,200,ACTIVE,BIKE",
            "INV9003,CUST9003,300,ACTIVE,CABIN",
        ],
        [
            "INV9003,CUST9003,300,CABIN",
            "INV9001,CUST9001,100,ECON",
            "INV9002,CUST9002,200,BIKE",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "ticket_id,rider_id,fare_type,amount_cents,status"
    assert [row["ticket_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }

def test_posted_and_blank_source_statuses_do_not_match():
    """Only ACTIVE source rows are eligible; POSTED or blank status rows must stay unmatched."""
    write_inputs(
        [
            "STATPOST1,CUSTSTAT1,1100,POSTED,ECON",
            "STATBLANK1,CUSTSTAT2,1200,,ECON",
        ],
        [
            "STATPOST1,CUSTSTAT1,1100,ECON",
            "STATBLANK1,CUSTSTAT2,1200,ECON",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
    assert [row["fare_type"] for row in rows] == ["", ""]
    assert summary["matched_count"] == 0
    assert summary["unmatched_count"] == 2
    assert summary["unmatched_amount_cents"] == 2300

def test_unmatched_report_fields_are_trimmed():
    """Unmatched report rows should still trim incidental spaces from action fields."""
    write_inputs(
        ["TRIMSRC1,CUSTSRC1,1900,ACTIVE,ECON"],
        [" TRIMACT1 , CUSTTRIM1 , 1700 , ECON "],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["ticket_id"] == "TRIMACT1"
    assert rows[0]["rider_id"] == "CUSTTRIM1"
    assert rows[0]["amount_cents"] == "1700"
    assert rows[0]["fare_type"] == ""
    assert summary["unmatched_amount_cents"] == 1700
