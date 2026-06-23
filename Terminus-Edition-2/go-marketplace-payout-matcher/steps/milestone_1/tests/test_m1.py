"""Tests for the order payout reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "orders.csv"
PAYMENTS = APP / "data" / "payouts.csv"
REPORT = APP / "out" / "payout_report.csv"
SUMMARY = APP / "out" / "payout_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go reconciliation CLI for the current source tree."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all tests."""
    build_program()


def write_inputs(bill_rows, refund_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    INVOICES.write_text("order_id,seller_id,amount_cents,status,lane\n" + "\n".join(bill_rows) + "\n")
    PAYMENTS.write_text("order_id,seller_id,amount_cents,lane\n" + "\n".join(refund_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_locker_refund_matches_and_counts_positive_amount():
    """LOCKER payouts should match shipped orders and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,SHIPPED,D2D",
            "INV20260401002,CUST1002,9900,SHIPPED,LOCKER",
        ],
        [
            "INV20260401001,CUST1001,12500,D2D",
            "INV20260401002,CUST1002,9900,LOCKER",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["lane"] == "LOCKER"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_order_id_match_uses_full_identifier():
    """A payout must not match an order that only shares the leading order prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,SHIPPED,D2D",
            "INV777770002,CUST2001,3300,SHIPPED,D2D",
        ],
        [
            "INV777770003,CUST2001,3300,D2D",
            "INV777770002,CUST2001,3300,D2D",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["lane"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_lane_all_gate_matching():
    """Customer, amount, shipped status, and allowed lane must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,1000,SHIPPED,D2D",
            "INV3002,CUST3002,2000,SHIPPED,LOCKER",
            "INV3003,CUST3003,3000,DRAFT,STORE",
            "INV3004,CUST3004,4000,SHIPPED,CHECK",
            "INV3005,CUST3005,5000,SHIPPED,STORE",
        ],
        [
            "INV3001,CUST9999,1000,D2D",
            "INV3002,CUST3002,2100,LOCKER",
            "INV3003,CUST3003,3000,STORE",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,STORE",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["lane"] == "STORE"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_refunds_do_not_reuse_consumed_bill():
    """Only the earliest eligible payout may consume a matching order."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,SHIPPED,LOCKER",
            "INV5552,CUST5552,8800,SHIPPED,D2D",
        ],
        [
            "INV5551,CUST5551,7500,LOCKER",
            "INV5551,CUST5551,7500,LOCKER",
            "INV5552,CUST5552,8800,D2D",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["lane"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_lane_status_case():
    """Matching should tolerate surrounding spaces and case differences in lane/status values."""
    write_inputs(
        [
            " INV6601 , CUST6601 , 6100 , shipped , locker ",
            "INV6602,CUST6602,7200,SHIPPED,store",
        ],
        [
            "INV6601,CUST6601, 6100 ,LOCKER",
            " INV6602 , CUST6602 ,7200, STORE ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["order_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["seller_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["lane"] for row in rows] == ["LOCKER", "STORE"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_report_schema_and_refund_input_order_are_stable():
    """The report should use the required schema and preserve payout input order."""
    write_inputs(
        [
            "INV9001,CUST9001,100,SHIPPED,D2D",
            "INV9002,CUST9002,200,SHIPPED,LOCKER",
            "INV9003,CUST9003,300,SHIPPED,STORE",
        ],
        [
            "INV9003,CUST9003,300,STORE",
            "INV9001,CUST9001,100,D2D",
            "INV9002,CUST9002,200,LOCKER",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "order_id,seller_id,lane,amount_cents,status"
    assert [row["order_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
