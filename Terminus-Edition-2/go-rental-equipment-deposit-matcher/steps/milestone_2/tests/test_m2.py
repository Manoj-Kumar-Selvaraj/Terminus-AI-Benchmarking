"""Verifier tests for the rental deposit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "rentals.csv"
PAYMENTS = APP / "data" / "deposits.csv"
REPORT = APP / "out" / "deposit_report.csv"
SUMMARY = APP / "out" / "deposit_summary.json"
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


def write_inputs(bill_rows, refund_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    INVOICES.write_text("rental_id,renter_id,amount_cents,status,depot\n" + "\n".join(bill_rows) + "\n")
    PAYMENTS.write_text("rental_id,renter_id,amount_cents,depot\n" + "\n".join(refund_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_delivery_refund_matches_and_counts_positive_amount():
    """DELIVERY deposits should match returned rentals and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,RETURNED,YARD",
            "INV20260401002,CUST1002,9900,RETURNED,DELIVERY",
        ],
        [
            "INV20260401001,CUST1001,12500,YARD",
            "INV20260401002,CUST1002,9900,DELIVERY",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["depot"] == "DELIVERY"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_rental_id_match_uses_full_identifier():
    """A deposit must not match a rental that only shares the leading rental prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,RETURNED,YARD",
            "INV777770002,CUST2001,3300,RETURNED,YARD",
        ],
        [
            "INV777770003,CUST2001,3300,YARD",
            "INV777770002,CUST2001,3300,YARD",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["depot"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_depot_all_gate_matching():
    """Customer, amount, returned status, and allowed depot must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,1000,RETURNED,YARD",
            "INV3002,CUST3002,2000,RETURNED,DELIVERY",
            "INV3003,CUST3003,3000,DRAFT,PICKUP",
            "INV3004,CUST3004,4000,RETURNED,CHECK",
            "INV3005,CUST3005,5000,RETURNED,PICKUP",
        ],
        [
            "INV3001,CUST9999,1000,YARD",
            "INV3002,CUST3002,2100,DELIVERY",
            "INV3003,CUST3003,3000,PICKUP",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,PICKUP",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["depot"] == "PICKUP"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_refunds_do_not_reuse_consumed_bill():
    """Only the earliest eligible deposit may consume a matching rental."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,RETURNED,DELIVERY",
            "INV5552,CUST5552,8800,RETURNED,YARD",
        ],
        [
            "INV5551,CUST5551,7500,DELIVERY",
            "INV5551,CUST5551,7500,DELIVERY",
            "INV5552,CUST5552,8800,YARD",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["depot"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_depot_status_case():
    """Matching should tolerate surrounding spaces and case differences in depot/status values."""
    write_inputs(
        [
            " INV6601 , CUST6601 , 6100 , returned , delivery ",
            "INV6602,CUST6602,7200,RETURNED,pickup",
        ],
        [
            "INV6601,CUST6601, 6100 ,DELIVERY",
            " INV6602 , CUST6602 ,7200, PICKUP ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["rental_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["renter_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["depot"] for row in rows] == ["DELIVERY", "PICKUP"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_legacy_depot_aliases_match_and_emit_canonical_depots():
    """Legacy YD, DEL, and PU deposit depots should match and report canonical depots."""
    write_inputs(
        [
            "INV7701,CUST7701,8800,RETURNED,DELIVERY",
            "INV7702,CUST7702,9100,returned,pickup",
            "INV7703,CUST7703,4200,RETURNED,YARD",
            "INV7704,CUST7704,3300,RETURNED,CHECK",
        ],
        [
            "INV7701,CUST7701,8800,del",
            "INV7702,CUST7702,9100,PU",
            "INV7703,CUST7703,4200,YD",
            "INV7704,CUST7704,3300,chk",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["depot"] for row in rows] == ["DELIVERY", "PICKUP", "YARD", ""]
    assert summary["matched_count"] == 3
    assert summary["matched_amount_cents"] == 22100
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 3300


def test_report_schema_and_refund_input_order_are_stable():
    """The report should use the required schema and preserve deposit input order."""
    write_inputs(
        [
            "INV9001,CUST9001,100,RETURNED,YARD",
            "INV9002,CUST9002,200,RETURNED,DELIVERY",
            "INV9003,CUST9003,300,RETURNED,PICKUP",
        ],
        [
            "INV9003,CUST9003,300,PICKUP",
            "INV9001,CUST9001,100,YARD",
            "INV9002,CUST9002,200,DELIVERY",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "rental_id,renter_id,depot,amount_cents,status"
    assert [row["rental_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
