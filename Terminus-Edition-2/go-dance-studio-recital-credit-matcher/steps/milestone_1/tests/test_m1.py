"""Verifier tests for the booking credit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
BOOKINGS = APP / "data" / "bookings.csv"
CREDITS = APP / "data" / "credits.csv"
REPORT = APP / "out" / "recital_credit_report.csv"
SUMMARY = APP / "out" / "recital_credit_summary.json"
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


def write_inputs(booking_rows, credit_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    BOOKINGS.write_text("booking_id,dancer_id,amount_cents,status,recital_type\n" + "\n".join(booking_rows) + "\n")
    CREDITS.write_text("booking_id,dancer_id,amount_cents,recital_type\n" + "\n".join(credit_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_group_credit_matches_and_counts_positive_amount():
    """GROUP credits should match active bookings and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,ACTIVE,SOLO",
            "INV20260401002,CUST1002,9900,ACTIVE,GROUP",
        ],
        [
            "INV20260401001,CUST1001,12500,SOLO",
            "INV20260401002,CUST1002,9900,GROUP",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["recital_type"] == "GROUP"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_booking_id_match_uses_full_identifier():
    """A credit must not match a booking that only shares the leading booking prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,ACTIVE,SOLO",
            "INV777770002,CUST2001,3300,ACTIVE,SOLO",
        ],
        [
            "INV777770003,CUST2001,3300,SOLO",
            "INV777770002,CUST2001,3300,SOLO",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["recital_type"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_recital_type_all_gate_matching():
    """Customer, amount, active status, and allowed recital_type must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,1000,ACTIVE,SOLO",
            "INV3002,CUST3002,2000,ACTIVE,GROUP",
            "INV3003,CUST3003,3000,DRAFT,STAGE",
            "INV3004,CUST3004,4000,ACTIVE,CHECK",
            "INV3005,CUST3005,5000,ACTIVE,STAGE",
        ],
        [
            "INV3001,CUST9999,1000,SOLO",
            "INV3002,CUST3002,2100,GROUP",
            "INV3003,CUST3003,3000,STAGE",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,STAGE",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["recital_type"] == "STAGE"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_credits_do_not_reuse_consumed_booking():
    """Only the earliest eligible credit may consume a matching booking."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,ACTIVE,GROUP",
            "INV5552,CUST5552,8800,ACTIVE,SOLO",
        ],
        [
            "INV5551,CUST5551,7500,GROUP",
            "INV5551,CUST5551,7500,GROUP",
            "INV5552,CUST5552,8800,SOLO",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["recital_type"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_recital_type_status_case():
    """Matching should tolerate surrounding spaces and case differences in recital_type/status values."""
    write_inputs(
        [
            " INV6601 , CUST6601 , 6100 , active , group ",
            "INV6602,CUST6602,7200,ACTIVE,stage",
        ],
        [
            "INV6601,CUST6601, 6100 ,GROUP",
            " INV6602 , CUST6602 ,7200, STAGE ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["booking_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["dancer_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["recital_type"] for row in rows] == ["GROUP", "STAGE"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_report_schema_and_credit_input_order_are_stable():
    """The report should use the required schema and preserve credit input order."""
    write_inputs(
        [
            "INV9001,CUST9001,100,ACTIVE,SOLO",
            "INV9002,CUST9002,200,ACTIVE,GROUP",
            "INV9003,CUST9003,300,ACTIVE,STAGE",
        ],
        [
            "INV9003,CUST9003,300,STAGE",
            "INV9001,CUST9001,100,SOLO",
            "INV9002,CUST9002,200,GROUP",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "booking_id,dancer_id,recital_type,amount_cents,status"
    assert [row["booking_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
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
            "STATPOST1,CUSTSTAT1,1100,POSTED,SOLO",
            "STATBLANK1,CUSTSTAT2,1200,,SOLO",
        ],
        [
            "STATPOST1,CUSTSTAT1,1100,SOLO",
            "STATBLANK1,CUSTSTAT2,1200,SOLO",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
    assert [row["recital_type"] for row in rows] == ["", ""]
    assert summary["matched_count"] == 0
    assert summary["unmatched_count"] == 2
    assert summary["unmatched_amount_cents"] == 2300

def test_unmatched_report_fields_are_trimmed():
    """Unmatched report rows should still trim incidental spaces from action fields."""
    write_inputs(
        ["TRIMSRC1,CUSTSRC1,1900,ACTIVE,SOLO"],
        [" TRIMACT1 , CUSTTRIM1 , 1700 , SOLO "],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["booking_id"] == "TRIMACT1"
    assert rows[0]["dancer_id"] == "CUSTTRIM1"
    assert rows[0]["amount_cents"] == "1700"
    assert rows[0]["recital_type"] == ""
    assert summary["unmatched_amount_cents"] == 1700
