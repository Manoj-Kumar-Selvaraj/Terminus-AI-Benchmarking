"""Verifier tests for the rental credit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
RENTALS = APP / "data" / "rentals.csv"
CREDITS = APP / "data" / "credits.csv"
REPORT = APP / "out" / "rental_credit_report.csv"
SUMMARY = APP / "out" / "rental_credit_summary.json"
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


def write_inputs(rental_rows, credit_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    RENTALS.write_text("rental_id,account_id,amount_cents,status,equipment_type\n" + "\n".join(rental_rows) + "\n")
    CREDITS.write_text("rental_id,account_id,amount_cents,equipment_type\n" + "\n".join(credit_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_spray_credit_matches_and_counts_positive_amount():
    """SPRAY credits should match active rentals and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,ACTIVE,TRACTOR",
            "INV20260401002,CUST1002,9900,ACTIVE,SPRAY",
        ],
        [
            "INV20260401001,CUST1001,12500,TRACTOR",
            "INV20260401002,CUST1002,9900,SPRAY",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["equipment_type"] == "SPRAY"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_rental_id_match_uses_full_identifier():
    """A credit must not match a rental that only shares the leading rental prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,ACTIVE,TRACTOR",
            "INV777770002,CUST2001,3300,ACTIVE,TRACTOR",
        ],
        [
            "INV777770003,CUST2001,3300,TRACTOR",
            "INV777770002,CUST2001,3300,TRACTOR",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["equipment_type"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_equipment_type_all_gate_matching():
    """Customer, amount, active status, and allowed equipment_type must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,1000,ACTIVE,TRACTOR",
            "INV3002,CUST3002,2000,ACTIVE,SPRAY",
            "INV3003,CUST3003,3000,DRAFT,LIFT",
            "INV3004,CUST3004,4000,ACTIVE,CHECK",
            "INV3005,CUST3005,5000,ACTIVE,LIFT",
        ],
        [
            "INV3001,CUST9999,1000,TRACTOR",
            "INV3002,CUST3002,2100,SPRAY",
            "INV3003,CUST3003,3000,LIFT",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,LIFT",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["equipment_type"] == "LIFT"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_credits_do_not_reuse_consumed_rental():
    """Only the earliest eligible credit may consume a matching rental."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,ACTIVE,SPRAY",
            "INV5552,CUST5552,8800,ACTIVE,TRACTOR",
        ],
        [
            "INV5551,CUST5551,7500,SPRAY",
            "INV5551,CUST5551,7500,SPRAY",
            "INV5552,CUST5552,8800,TRACTOR",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["equipment_type"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_equipment_type_status_case():
    """Matching should tolerate surrounding spaces and case differences in equipment_type/status values."""
    write_inputs(
        [
            " INV6601 , CUST6601 , 6100 , active , spray ",
            "INV6602,CUST6602,7200,ACTIVE,lift",
        ],
        [
            "INV6601,CUST6601, 6100 ,SPRAY",
            " INV6602 , CUST6602 ,7200, LIFT ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["rental_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["account_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["equipment_type"] for row in rows] == ["SPRAY", "LIFT"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_report_schema_and_credit_input_order_are_stable():
    """The report should use the required schema and preserve credit input order."""
    write_inputs(
        [
            "INV9001,CUST9001,100,ACTIVE,TRACTOR",
            "INV9002,CUST9002,200,ACTIVE,SPRAY",
            "INV9003,CUST9003,300,ACTIVE,LIFT",
        ],
        [
            "INV9003,CUST9003,300,LIFT",
            "INV9001,CUST9001,100,TRACTOR",
            "INV9002,CUST9002,200,SPRAY",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "rental_id,account_id,equipment_type,amount_cents,status"
    assert [row["rental_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
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
            "STATPOST1,CUSTSTAT1,1100,POSTED,TRACTOR",
            "STATBLANK1,CUSTSTAT2,1200,,TRACTOR",
        ],
        [
            "STATPOST1,CUSTSTAT1,1100,TRACTOR",
            "STATBLANK1,CUSTSTAT2,1200,TRACTOR",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
    assert [row["equipment_type"] for row in rows] == ["", ""]
    assert summary["matched_count"] == 0
    assert summary["unmatched_count"] == 2
    assert summary["unmatched_amount_cents"] == 2300

def test_unmatched_report_fields_are_trimmed():
    """Unmatched report rows should still trim incidental spaces from action fields."""
    write_inputs(
        ["TRIMSRC1,CUSTSRC1,1900,ACTIVE,TRACTOR"],
        [" TRIMACT1 , CUSTTRIM1 , 1700 , TRACTOR "],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["rental_id"] == "TRIMACT1"
    assert rows[0]["account_id"] == "CUSTTRIM1"
    assert rows[0]["amount_cents"] == "1700"
    assert rows[0]["equipment_type"] == ""
    assert summary["unmatched_amount_cents"] == 1700
