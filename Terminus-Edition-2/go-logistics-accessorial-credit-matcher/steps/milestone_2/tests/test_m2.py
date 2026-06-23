"""Verifier tests for the charge credit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "charges.csv"
PAYMENTS = APP / "data" / "credits.csv"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"
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
    INVOICES.write_text("charge_id,shipper_id,amount_cents,status,mode\n" + "\n".join(bill_rows) + "\n")
    PAYMENTS.write_text("charge_id,shipper_id,amount_cents,mode\n" + "\n".join(refund_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone2:
    """Milestone 2 behavior checks for the charge reconciliation CLI."""

    def test_legacy_mode_aliases_match_and_emit_canonical_modes(self):
        """Legacy LESS, FULL, and RR credit modes should match and report canonical modes."""
        write_inputs(
            [
                "INV7701,CUST7701,8800,BILLED,FTL",
                "INV7702,CUST7702,9100,billed,rail",
                "INV7703,CUST7703,4200,BILLED,LTL",
                "INV7704,CUST7704,3300,BILLED,CHECK",
            ],
            [
                "INV7701,CUST7701,8800,full",
                "INV7702,CUST7702,9100,RR",
                "INV7703,CUST7703,4200,LESS",
                "INV7704,CUST7704,3300,chk",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["mode"] for row in rows] == ["FTL", "RAIL", "LTL", ""]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 22100
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 3300

    def test_report_schema_and_refund_input_order_are_stable(self):
        """The report should use the required schema and preserve credit input order."""
        write_inputs(
            [
                "INV9001,CUST9001,100,BILLED,LTL",
                "INV9002,CUST9002,200,BILLED,FTL",
                "INV9003,CUST9003,300,BILLED,RAIL",
            ],
            [
                "INV9003,CUST9003,300,RAIL",
                "INV9001,CUST9001,100,LTL",
                "INV9002,CUST9002,200,FTL",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "charge_id,shipper_id,mode,amount_cents,status"
        assert [row["charge_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
        assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
