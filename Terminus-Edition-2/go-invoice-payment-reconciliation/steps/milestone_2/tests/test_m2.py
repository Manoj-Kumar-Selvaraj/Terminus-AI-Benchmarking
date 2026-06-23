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


class TestMilestone2:
    """Milestone 2 verifier scenarios for aliases."""

    def test_legacy_method_aliases_match_and_emit_canonical_methods(self):
        """CC and WIR should match as CARD and WIRE and report canonical methods."""
        write_inputs(
            ["INV7701,CUST7701,8800,POSTED,CARD", "INV7702,CUST7702,9100,posted,wire", "INV7703,CUST7703,4200,POSTED,ACH"],
            ["INV7701,CUST7701,8800,cc", "INV7702,CUST7702,9100, WIR ", "INV7703,CUST7703,4200,ach"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["method"] for row in rows] == ["CARD", "WIRE", "ACH"]
        assert summary["matched_amount_cents"] == 22100

    def test_cross_alias_method_mismatch_stays_unmatched(self):
        """An alias resolving to one method must not match a different invoice method."""
        write_inputs(
            ["INV-A,CUST-A,1000,POSTED,CARD", "INV-B,CUST-B,2000,POSTED,WIRE"],
            ["INV-A,CUST-A,1000,WIR", "INV-B,CUST-B,2000,CC"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert [row["method"] for row in rows] == ["", ""]
        assert summary["unmatched_amount_cents"] == 3000

    def test_aliases_preserve_identity_amount_status_and_consumption_gates(self):
        """Aliases cannot bypass prior gates or one-time invoice consumption."""
        write_inputs(
            [
                "INV8801,CUST8801,5000,POSTED,CARD",
                "INV8802,CUST8802,6000,DRAFT,WIRE",
                "INV8803,CUST8803,7000,POSTED,WIRE",
            ],
            [
                "INV8801,CUST8801,5000,CC",
                "INV8801,CUST8801,5000,CC",
                "INV8802,CUST8802,6000,WIR",
                "INV8803,CUST9999,7000,WIR",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert [row["method"] for row in rows] == ["CARD", "", "", ""]
        assert summary == {"matched_count": 1, "matched_amount_cents": 5000, "unmatched_count": 3, "unmatched_amount_cents": 18000}

    def test_invalid_amount_regression_under_alias_normalization(self):
        """Alias logic must not make malformed payment amounts crash or count as cents."""
        write_inputs(
            ["INV9901,CUST9901,1200,POSTED,CARD"],
            ["INV9901,CUST9901,12O0,CC"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["method"] == ""
        assert summary == {"matched_count": 0, "matched_amount_cents": 0, "unmatched_count": 1, "unmatched_amount_cents": 0}

    def test_milestone_one_core_behaviors_still_hold(self):
        """Full IDs, field trimming, schema, and input order remain intact."""
        write_inputs(
            [
                " INV6601 , CUST6601 , 6100 , posted , card ",
                "INV777770002,CUST2001,3300,POSTED,ACH",
            ],
            [
                "INV777770003,CUST2001,3300,ACH",
                "INV6601,CUST6601,6100,CC",
                "INV777770002,CUST2001,3300,ACH",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED", "MATCHED"]
        assert [row["method"] for row in rows] == ["", "CARD", "ACH"]
        assert REPORT.read_text().splitlines()[0] == "invoice_id,customer_id,method,amount_cents,status"
        assert summary["matched_amount_cents"] == 9400
