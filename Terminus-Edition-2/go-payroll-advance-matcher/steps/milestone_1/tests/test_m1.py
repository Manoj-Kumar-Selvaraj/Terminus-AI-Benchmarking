"""Verifier tests for the advance repayment reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "advances.csv"
PAYMENTS = APP / "data" / "repayments.csv"
REPORT = APP / "out" / "repayment_report.csv"
SUMMARY = APP / "out" / "repayment_summary.json"
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
    INVOICES.write_text("advance_id,employee_id,amount_cents,status,method\n" + "\n".join(bill_rows) + "\n")
    PAYMENTS.write_text("advance_id,employee_id,amount_cents,method\n" + "\n".join(refund_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_payroll_refund_matches_and_counts_positive_amount():
    """PAYROLL repayments should match active advances and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,ACTIVE,DIRECT",
            "INV20260401002,CUST1002,9900,ACTIVE,PAYROLL",
        ],
        [
            "INV20260401001,CUST1001,12500,DIRECT",
            "INV20260401002,CUST1002,9900,PAYROLL",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["method"] == "PAYROLL"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_advance_id_match_uses_full_identifier():
    """A repayment must not match a advance that only shares the leading advance prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,ACTIVE,DIRECT",
            "INV777770002,CUST2001,3300,ACTIVE,DIRECT",
        ],
        [
            "INV777770003,CUST2001,3300,DIRECT",
            "INV777770002,CUST2001,3300,DIRECT",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["method"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_method_all_gate_matching():
    """Customer, amount, active status, and allowed method must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,1000,ACTIVE,DIRECT",
            "INV3002,CUST3002,2000,ACTIVE,PAYROLL",
            "INV3003,CUST3003,3000,DRAFT,DEBIT",
            "INV3004,CUST3004,4000,ACTIVE,CHECK",
            "INV3005,CUST3005,5000,ACTIVE,DEBIT",
        ],
        [
            "INV3001,CUST9999,1000,DIRECT",
            "INV3002,CUST3002,2100,PAYROLL",
            "INV3003,CUST3003,3000,DEBIT",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,DEBIT",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["method"] == "DEBIT"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_refunds_do_not_reuse_consumed_bill():
    """Only the earliest eligible repayment may consume a matching advance."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,ACTIVE,PAYROLL",
            "INV5552,CUST5552,8800,ACTIVE,DIRECT",
        ],
        [
            "INV5551,CUST5551,7500,PAYROLL",
            "INV5551,CUST5551,7500,PAYROLL",
            "INV5552,CUST5552,8800,DIRECT",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["method"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_method_status_case():
    """Matching should tolerate surrounding spaces and case differences in method/status values."""
    write_inputs(
        [
            " INV6601 , CUST6601 , 6100 , active , payroll ",
            "INV6602,CUST6602,7200,ACTIVE,debit",
        ],
        [
            "INV6601,CUST6601, 6100 ,PAYROLL",
            " INV6602 , CUST6602 ,7200, DEBIT ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["advance_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["employee_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["method"] for row in rows] == ["PAYROLL", "DEBIT"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_report_schema_and_refund_input_order_are_stable():
    """The report should use the required schema and preserve repayment input order."""
    write_inputs(
        [
            "INV9001,CUST9001,100,ACTIVE,DIRECT",
            "INV9002,CUST9002,200,ACTIVE,PAYROLL",
            "INV9003,CUST9003,300,ACTIVE,DEBIT",
        ],
        [
            "INV9003,CUST9003,300,DEBIT",
            "INV9001,CUST9001,100,DIRECT",
            "INV9002,CUST9002,200,PAYROLL",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "advance_id,employee_id,method,amount_cents,status"
    assert [row["advance_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
