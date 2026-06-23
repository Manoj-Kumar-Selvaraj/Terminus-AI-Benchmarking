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


class TestMilestone1:
    """Milestone 1 behavior checks for the charge reconciliation CLI."""

    def test_ftl_refund_matches_and_counts_positive_amount(self):
        """FTL credits should match billed charges and add positive cents to matched totals."""
        write_inputs(
            [
                "INV20260401001,CUST1001,12500,BILLED,LTL",
                "INV20260401002,CUST1002,9900,BILLED,FTL",
            ],
            [
                "INV20260401001,CUST1001,12500,LTL",
                "INV20260401002,CUST1002,9900,FTL",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["mode"] == "FTL"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 22400
        assert summary["unmatched_count"] == 0

    def test_charge_id_match_uses_full_identifier(self):
        """A credit must not match a charge that only shares the leading charge prefix."""
        write_inputs(
            [
                "INV777770001,CUST2001,3300,BILLED,LTL",
                "INV777770002,CUST2001,3300,BILLED,LTL",
            ],
            [
                "INV777770003,CUST2001,3300,LTL",
                "INV777770002,CUST2001,3300,LTL",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["mode"] == ""
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300

    def test_customer_amount_status_and_mode_all_gate_matching(self):
        """Customer, amount, billed status, and allowed mode must all be satisfied."""
        write_inputs(
            [
                "INV3001,CUST3001,1000,BILLED,LTL",
                "INV3002,CUST3002,2000,BILLED,FTL",
                "INV3003,CUST3003,3000,DRAFT,RAIL",
                "INV3004,CUST3004,4000,BILLED,CHECK",
                "INV3005,CUST3005,5000,BILLED,RAIL",
            ],
            [
                "INV3001,CUST9999,1000,LTL",
                "INV3002,CUST3002,2100,FTL",
                "INV3003,CUST3003,3000,RAIL",
                "INV3004,CUST3004,4000,CHECK",
                "INV3005,CUST3005,5000,RAIL",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["mode"] == "RAIL"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_count"] == 4
        assert summary["unmatched_amount_cents"] == 10100

    def test_duplicate_refunds_do_not_reuse_consumed_bill(self):
        """Only the earliest eligible credit may consume a matching charge."""
        write_inputs(
            [
                "INV5551,CUST5551,7500,BILLED,FTL",
                "INV5552,CUST5552,8800,BILLED,LTL",
            ],
            [
                "INV5551,CUST5551,7500,FTL",
                "INV5551,CUST5551,7500,FTL",
                "INV5552,CUST5552,8800,LTL",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["mode"] == ""
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 16300
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 7500

    def test_matching_trims_fields_and_normalizes_mode_status_case(self):
        """Matching should tolerate surrounding spaces and case differences in mode/status values."""
        write_inputs(
            [
                " INV6601 , CUST6601 , 6100 , billed , ftl ",
                "INV6602,CUST6602,7200,BILLED,rail",
            ],
            [
                "INV6601,CUST6601, 6100 ,FTL",
                " INV6602 , CUST6602 ,7200, RAIL ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["charge_id"] for row in rows] == ["INV6601", "INV6602"]
        assert [row["shipper_id"] for row in rows] == ["CUST6601", "CUST6602"]
        assert [row["mode"] for row in rows] == ["FTL", "RAIL"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 13300

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
