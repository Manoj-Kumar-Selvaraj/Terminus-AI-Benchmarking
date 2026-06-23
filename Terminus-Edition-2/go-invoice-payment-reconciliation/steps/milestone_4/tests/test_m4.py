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


class TestMilestone4:
    """Milestone 4 verifier scenarios for policy, wildcard, limits, and audit output."""

    def setup_method(self):
        """Install a default open calendar for each test."""
        write_calendar(["2026-04-01 open", "2026-04-02 open", "2026-04-03 open", "2026-04-04 open", "2026-04-05 open"])
        write_methods(["ACH,true,2", "CARD,true,1", "WIRE,true,3"])
        write_limits([])

    def test_any_skips_disabled_high_priority_method_and_falls_back(self):
        """ANY must ignore disabled methods before ranking candidates."""
        write_inputs(
            [
                "INVANY1,CUSTA,500,POSTED,CARD,2026-04-05",
                "INVANY1,CUSTA,500,POSTED,ACH,2026-04-05",
            ],
            ["INVANY1,CUSTA,500,ANY,2026-04-02"],
            "invoice_id,customer_id,amount_cents,status,method,due_date",
            "invoice_id,customer_id,amount_cents,method,payment_date",
        )
        write_methods(["CARD,false,1", "ACH,true,2", "WIRE,true,3"])
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["method"] == "ACH"
        assert summary["matched_amount_cents"] == 500

    def test_any_ranks_by_latest_due_date_then_priority_then_row_order(self):
        """Wildcard candidate ranking should use due date, priority, then source row order."""
        write_inputs(
            [
                "INVANY2,CUSTB,700,POSTED,ACH,2026-04-04",
                "INVANY2,CUSTB,700,POSTED,WIRE,2026-04-05",
                "INVANY2,CUSTB,700,POSTED,CARD,2026-04-05",
                "INVANY2,CUSTB,700,POSTED,CARD,2026-04-05",
            ],
            ["INVANY2,CUSTB,700,ANY,2026-04-02", "INVANY2,CUSTB,700,ANY,2026-04-02"],
            "invoice_id,customer_id,amount_cents,status,method,due_date",
            "invoice_id,customer_id,amount_cents,method,payment_date",
        )
        write_methods(["ACH,true,1", "WIRE,true,3", "CARD,true,2"])
        rows, _ = run_program()
        assert [row["method"] for row in rows] == ["CARD", "CARD"]
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]

    def test_customer_limit_resets_per_payment_date_and_excludes_future_limits(self):
        """Limit budgets are independent per date and future effective limits are ignored."""
        write_inputs(
            [
                "INV-L1,CUST-L,800,POSTED,CARD,2026-04-10",
                "INV-L2,CUST-L,800,POSTED,CARD,2026-04-11",
                "INV-L3,CUST-L,800,POSTED,CARD,2026-04-11",
            ],
            [
                "INV-L1,CUST-L,800,CARD,2026-04-04",
                "INV-L2,CUST-L,800,CARD,2026-04-05",
                "INV-L3,CUST-L,800,CARD,2026-04-05",
            ],
            "invoice_id,customer_id,amount_cents,status,method,due_date",
            "invoice_id,customer_id,amount_cents,method,payment_date",
        )
        write_calendar(["2026-04-04 open", "2026-04-05 open"])
        write_limits(["CUST-L,CARD,1000,2026-04-01,true", "CUST-L,CARD,500,2026-04-06,true"])
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert summary == {"matched_count": 2, "matched_amount_cents": 1600, "unmatched_count": 1, "unmatched_amount_cents": 800}

    def test_methods_enabled_parsing_is_case_and_whitespace_tolerant(self):
        """Enabled values and method names should be trimmed and case-insensitive."""
        write_inputs(
            ["INV-M1,CUST-M,600,POSTED,WIRE,2026-04-08"],
            ["INV-M1,CUST-M,600,WIR,2026-04-03"],
            "invoice_id,customer_id,amount_cents,status,method,due_date",
            "invoice_id,customer_id,amount_cents,method,payment_date",
        )
        write_methods([" WIRE , TrUe , 1", "CARD,false,2"])
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["method"] == "WIRE"
        assert summary["matched_count"] == 1

    def test_audit_rows_reconcile_report_and_summary(self):
        """Audit output should summarize matched and unmatched payment outcomes by method group."""
        write_inputs(
            ["INV-AUD1,CUST-AUD,100,POSTED,ACH,2026-04-05", "INV-AUD2,CUST-AUD,200,POSTED,CARD,2026-04-05"],
            ["INV-AUD1,CUST-AUD,100,ACH,2026-04-02", "INV-AUD2,CUST-AUD,200,ANY,2026-04-02", "INV-MISS,CUST-AUD,300,ANY,2026-04-02"],
            "invoice_id,customer_id,amount_cents,status,method,due_date",
            "invoice_id,customer_id,amount_cents,method,payment_date",
        )
        rows, summary = run_program()
        audit = read_audit()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert summary == {"matched_count": 2, "matched_amount_cents": 300, "unmatched_count": 1, "unmatched_amount_cents": 300}
        assert [row["method"] for row in audit] == ["ACH", "CARD", "ANY"]
        assert audit[0]["matched_amount_cents"] == "100"
        assert audit[1]["matched_amount_cents"] == "200"
        assert audit[2]["unmatched_amount_cents"] == "300"
