"""Verifier tests for the invoice payment reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "invoices.csv"
PAYMENTS = APP / "data" / "payments.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
METHODS = APP / "config" / "methods.csv"
LIMITS = APP / "config" / "customer_limits.csv"
REPORT = APP / "out" / "payment_report.csv"
SUMMARY = APP / "out" / "payment_summary.json"
AUDIT = APP / "out" / "payment_audit.csv"
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


def write_inputs(invoice_rows, payment_rows, invoice_header=None, payment_header=None):
    """Replace invoice/payment CSVs and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    invoice_header = invoice_header or "invoice_id,customer_id,amount_cents,status,method"
    payment_header = payment_header or "invoice_id,customer_id,amount_cents,method"
    INVOICES.write_text(invoice_header + "\n" + "\n".join(invoice_rows) + "\n")
    PAYMENTS.write_text(payment_header + "\n" + "\n".join(payment_rows) + "\n")
    for path in (REPORT, SUMMARY, AUDIT):
        path.unlink(missing_ok=True)


def write_calendar(rows):
    """Replace the cutoff calendar."""
    CALENDAR.write_text("\n".join(rows) + "\n")


def write_methods(rows):
    """Replace method policy config."""
    METHODS.write_text("method,enabled,priority\n" + "\n".join(rows) + "\n")


def write_limits(rows):
    """Replace customer limits config."""
    LIMITS.write_text("customer_id,method,max_amount_cents,effective_date,enabled\n" + "\n".join(rows) + "\n")


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def read_audit():
    """Return parsed audit rows."""
    with AUDIT.open(newline="") as f:
        return list(csv.DictReader(f))


class TestMilestone1:
    """Milestone 1 verifier scenarios."""

    def test_card_payment_matches_and_counts_positive_amount(self):
        """CARD payments should match posted invoices and add positive cents."""
        write_inputs(
            ["INV20260401001,CUST1001,12500,POSTED,ACH", "INV20260401002,CUST1002,9900,POSTED,CARD"],
            ["INV20260401001,CUST1001,12500,ACH", "INV20260401002,CUST1002,9900,CARD"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["method"] for row in rows] == ["ACH", "CARD"]
        assert summary["matched_amount_cents"] == 22400

    def test_all_matching_gates_and_full_invoice_id_are_enforced(self):
        """Identity, status, amount, method, and full ID checks must gate matching."""
        write_inputs(
            [
                "INV777770001,CUST2001,3300,POSTED,ACH",
                "INV777770002,CUST2001,3300,POSTED,ACH",
                "INV3001,CUST3001,1000,DRAFT,WIRE",
                "INV3002,CUST3002,2000,POSTED,CHECK",
                "INV3003,CUST3003,3000,POSTED,CARD",
            ],
            [
                "INV777770003,CUST2001,3300,ACH",
                "INV777770002,CUST2001,3300,ACH",
                "INV3001,CUST3001,1000,WIRE",
                "INV3002,CUST3002,2000,CHECK",
                "INV3003,CUST9999,3000,CARD",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary == {"matched_count": 1, "matched_amount_cents": 3300, "unmatched_count": 4, "unmatched_amount_cents": 9300}

    def test_duplicate_payments_do_not_reuse_consumed_invoice(self):
        """Only the earliest eligible payment may consume a matching invoice row."""
        write_inputs(
            ["INV5551,CUST5551,7500,POSTED,CARD", "INV5552,CUST5552,8800,POSTED,ACH"],
            ["INV5551,CUST5551,7500,CARD", "INV5551,CUST5551,7500,CARD", "INV5552,CUST5552,8800,ACH"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["method"] == ""
        assert summary["matched_amount_cents"] == 16300
        assert summary["unmatched_amount_cents"] == 7500

    def test_trimming_case_and_first_qualifying_invoice_row_are_observable(self):
        """Whitespace and case normalize, and first qualifying invoice row is consumed."""
        write_inputs(
            [
                " INV6601 , CUST6601 , 6100 , posted , card ",
                "INV6601,CUST6601,6100,POSTED,WIRE",
                "INV6602,CUST6602,7200,POSTED,wire",
            ],
            ["INV6601,CUST6601,6100,CARD", "INV6601,CUST6601,6100,WIRE", " INV6602 , CUST6602 ,7200, WIRE "],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["method"] for row in rows] == ["CARD", "WIRE", "WIRE"]
        assert [row["invoice_id"] for row in rows] == ["INV6601", "INV6601", "INV6602"]
        assert summary["matched_count"] == 3

    def test_invalid_amount_formats_do_not_crash_and_contribute_zero(self):
        """Malformed and non-positive payment amounts are unmatched with zero amount contribution."""
        write_inputs(
            [
                "INV8001,CUST8001,1200,POSTED,ACH",
                "INV8002,CUST8002,-5,POSTED,CARD",
                "INV8003,CUST8003,12.0,POSTED,WIRE",
            ],
            [
                "INV8001,CUST8001,12O0,ACH",
                "INV8002,CUST8002,-5,CARD",
                "INV8003,CUST8003,12.0,WIRE",
                "INV8004,CUST8004,0,ACH",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary == {"matched_count": 0, "matched_amount_cents": 0, "unmatched_count": 4, "unmatched_amount_cents": 0}

    def test_report_schema_and_payment_input_order_are_stable(self):
        """Report schema and payment input order must remain stable."""
        write_inputs(
            ["INV9001,CUST9001,100,POSTED,ACH", "INV9002,CUST9002,200,POSTED,CARD", "INV9003,CUST9003,300,POSTED,WIRE"],
            ["INV9003,CUST9003,300,WIRE", "INV9001,CUST9001,100,ACH", "INV9002,CUST9002,200,CARD"],
        )
        rows, summary = run_program()
        assert REPORT.read_text().splitlines()[0] == "invoice_id,customer_id,method,amount_cents,status"
        assert [row["invoice_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
        assert summary == {"matched_count": 3, "matched_amount_cents": 600, "unmatched_count": 0, "unmatched_amount_cents": 0}
