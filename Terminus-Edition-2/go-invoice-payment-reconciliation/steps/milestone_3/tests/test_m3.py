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


class TestMilestone3:
    """Milestone 3 verifier scenarios for date controls."""

    def test_open_payment_dates_aliases_and_latest_due_date_selection(self):
        """Open payment dates gate matching and latest eligible due date wins."""
        write_inputs(
            [
                "INV9101,CUST9101,1000,POSTED,ACH,2026-04-03",
                "INV9101,CUST9101,1000,POSTED,WIRE,2026-04-04",
                "INV9102,CUST9102,2000,POSTED,CARD,2026-04-02",
            ],
            [
                "INV9101,CUST9101,1000,WIR,2026-04-02",
                "INV9102,CUST9102,2000,CC,2026-04-04",
            ],
            "invoice_id,customer_id,amount_cents,status,method,due_date",
            "invoice_id,customer_id,amount_cents,method,payment_date",
        )
        write_calendar(["2026-04-02 open", "2026-04-04 open"])
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["method"] for row in rows] == ["WIRE", ""]
        assert summary == {"matched_count": 1, "matched_amount_cents": 1000, "unmatched_count": 1, "unmatched_amount_cents": 2000}

    def test_latest_due_date_choice_is_observable(self):
        """Picking the old row first makes the second payment fail, so latest due date is observable."""
        write_inputs(
            ["INV9301,CUST9301,800,POSTED,ACH,2026-04-01", "INV9301,CUST9301,800,POSTED,ACH,2026-04-03"],
            ["INV9301,CUST9301,800,ACH,2026-04-01", "INV9301,CUST9301,800,ACH,2026-04-02"],
            "invoice_id,customer_id,amount_cents,status,method,due_date",
            "invoice_id,customer_id,amount_cents,method,payment_date",
        )
        write_calendar(["2026-04-01 open", "2026-04-02 open"])
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 1

    def test_same_due_date_tie_uses_invoice_input_order_and_consumption(self):
        """Same due-date candidates use row order and remain one-use rows."""
        write_inputs(
            ["INV9201,CUST9201,500,POSTED,CARD,2026-04-05", "INV9201,CUST9201,500,POSTED,CARD,2026-04-05"],
            ["INV9201,CUST9201,500,CC,2026-04-04", "INV9201,CUST9201,500,CC,2026-04-04", "INV9201,CUST9201,500,CC,2026-04-04"],
            "invoice_id,customer_id,amount_cents,status,method,due_date",
            "invoice_id,customer_id,amount_cents,method,payment_date",
        )
        write_calendar(["2026-04-04 open", "2026-04-05 open"])
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert summary == {"matched_count": 2, "matched_amount_cents": 1000, "unmatched_count": 1, "unmatched_amount_cents": 500}

    def test_closed_missing_malformed_and_case_corrected_calendar_dates_reject(self):
        """Closed, missing, malformed, and overridden calendar states are enforced."""
        write_inputs(
            [
                "INV1,C1,100,POSTED,ACH,2026-04-10",
                "INV2,C2,200,POSTED,CARD,2026-04-10",
                "INV3,C3,300,POSTED,WIRE,2026-04-10",
                "INV4,C4,400,POSTED,ACH,2026-04-10",
            ],
            [
                "INV1,C1,100,ACH,2026-04-03",
                "INV2,C2,200,CC,2026-04-04",
                "INV3,C3,300,WIR,bad-date",
                "INV4,C4,400,ACH,2026-04-05",
            ],
            "invoice_id,customer_id,amount_cents,status,method,due_date",
            "invoice_id,customer_id,amount_cents,method,payment_date",
        )
        write_calendar(["2026-04-03 open", "2026-04-03 CLOSED", "2026-04-04 closed", "2026-04-05 OpEn"])
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert summary == {"matched_count": 1, "matched_amount_cents": 400, "unmatched_count": 3, "unmatched_amount_cents": 600}

    def test_missing_or_malformed_due_dates_are_ineligible_without_crashing(self):
        """Invoice rows without valid due dates cannot match dated payments."""
        write_inputs(
            ["INV9451,CUST9451,500,POSTED,ACH", "INV9452,CUST9452,650,POSTED,CARD,bad-date"],
            ["INV9451,CUST9451,500,ACH,2026-04-04", "INV9452,CUST9452,650,CC,2026-04-04"],
            "invoice_id,customer_id,amount_cents,status,method,due_date",
            "invoice_id,customer_id,amount_cents,method,payment_date",
        )
        write_calendar(["2026-04-04 open"])
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert summary["unmatched_amount_cents"] == 1150
