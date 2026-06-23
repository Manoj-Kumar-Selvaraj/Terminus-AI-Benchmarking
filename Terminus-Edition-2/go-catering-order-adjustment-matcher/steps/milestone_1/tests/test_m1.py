"""Verifier tests for the order adjustment reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "orders.csv"
PAYMENTS = APP / "data" / "adjustments.csv"
REPORT = APP / "out" / "adjustment_report.csv"
SUMMARY = APP / "out" / "adjustment_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go reconciliation CLI for the current source tree."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all verifier tests."""
    build_program()


def write_inputs(bill_rows, refund_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    INVOICES.write_text("order_id,venue_id,amount_cents,status,service\n" + "\n".join(bill_rows) + "\n")
    PAYMENTS.write_text("order_id,venue_id,amount_cents,service\n" + "\n".join(refund_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_delivery_refund_matches_and_counts_positive_amount():
    """DELIVERY adjustments should match fulfilled orders and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,FULFILLED,PICKUP",
            "INV20260401002,CUST1002,9900,FULFILLED,DELIVERY",
        ],
        [
            "INV20260401001,CUST1001,12500,PICKUP",
            "INV20260401002,CUST1002,9900,DELIVERY",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["service"] == "DELIVERY"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_order_id_match_uses_full_identifier():
    """An adjustment must not match an order that only shares the leading order prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,FULFILLED,PICKUP",
            "INV777770002,CUST2001,3300,FULFILLED,PICKUP",
        ],
        [
            "INV777770003,CUST2001,3300,PICKUP",
            "INV777770002,CUST2001,3300,PICKUP",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["service"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_service_all_gate_matching():
    """Customer, amount, fulfilled status, and allowed service must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,1000,FULFILLED,PICKUP",
            "INV3002,CUST3002,2000,FULFILLED,DELIVERY",
            "INV3003,CUST3003,3000,DRAFT,ONSITE",
            "INV3004,CUST3004,4000,FULFILLED,CHECK",
            "INV3005,CUST3005,5000,FULFILLED,ONSITE",
        ],
        [
            "INV3001,CUST9999,1000,PICKUP",
            "INV3002,CUST3002,2100,DELIVERY",
            "INV3003,CUST3003,3000,ONSITE",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,ONSITE",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["service"] == "ONSITE"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_refunds_do_not_reuse_consumed_bill():
    """Only the earliest eligible adjustment may consume a matching order."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,FULFILLED,DELIVERY",
            "INV5552,CUST5552,8800,FULFILLED,PICKUP",
        ],
        [
            "INV5551,CUST5551,7500,DELIVERY",
            "INV5551,CUST5551,7500,DELIVERY",
            "INV5552,CUST5552,8800,PICKUP",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["service"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_service_status_case():
    """Matching should tolerate surrounding spaces and case differences in service/status values."""
    write_inputs(
        [
            " INV6601 , CUST6601 , 6100 , fulfilled , delivery ",
            "INV6602,CUST6602,7200,FULFILLED,onsite",
        ],
        [
            "INV6601,CUST6601, 6100 ,DELIVERY",
            " INV6602 , CUST6602 ,7200, ONSITE ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["order_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["venue_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["service"] for row in rows] == ["DELIVERY", "ONSITE"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_report_schema_and_refund_input_order_are_stable():
    """The report should use the required schema and preserve adjustment input order."""
    write_inputs(
        [
            "INV9001,CUST9001,100,FULFILLED,PICKUP",
            "INV9002,CUST9002,200,FULFILLED,DELIVERY",
            "INV9003,CUST9003,300,FULFILLED,ONSITE",
        ],
        [
            "INV9003,CUST9003,300,ONSITE",
            "INV9001,CUST9001,100,PICKUP",
            "INV9002,CUST9002,200,DELIVERY",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "order_id,venue_id,service,amount_cents,status"
    assert [row["order_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
