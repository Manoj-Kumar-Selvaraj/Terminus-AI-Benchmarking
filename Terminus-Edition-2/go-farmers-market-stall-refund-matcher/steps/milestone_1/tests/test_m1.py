"""Milestone 1 tests for the stall refund reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "stalls.csv"
PAYMENTS = APP / "data" / "refunds.csv"
REPORT = APP / "out" / "refund_report.csv"
SUMMARY = APP / "out" / "refund_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go reconciliation CLI for the current source tree."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 1 tests."""
    build_program()


def write_inputs(bill_rows, refund_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    INVOICES.write_text("stall_id,vendor_id,amount_cents,status,stall_type\n" + "\n".join(bill_rows) + "\n")
    PAYMENTS.write_text("stall_id,vendor_id,amount_cents,stall_type\n" + "\n".join(refund_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())




class TestMilestone1:
    """Behavior checks for milestone 1."""

    def test_craft_refund_matches_and_counts_positive_amount(self):
        """CRAFT refunds should match reserved stalls and add positive cents to matched totals."""
        write_inputs(
            [
                "INV20260401001,CUST1001,12500,RESERVED,PRODUCE",
                "INV20260401002,CUST1002,9900,RESERVED,CRAFT",
            ],
            [
                "INV20260401001,CUST1001,12500,PRODUCE",
                "INV20260401002,CUST1002,9900,CRAFT",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["stall_type"] == "CRAFT"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 22400
        assert summary["unmatched_count"] == 0


    def test_stall_id_match_uses_full_identifier(self):
        """A refund must not match a stall that only shares the leading stall prefix."""
        write_inputs(
            [
                "INV777770001,CUST2001,3300,RESERVED,PRODUCE",
                "INV777770002,CUST2001,3300,RESERVED,PRODUCE",
            ],
            [
                "INV777770003,CUST2001,3300,PRODUCE",
                "INV777770002,CUST2001,3300,PRODUCE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["stall_type"] == ""
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300


    def test_customer_amount_status_and_stall_type_all_gate_matching(self):
        """Customer, amount, reserved status, and allowed stall_type must all be satisfied."""
        write_inputs(
            [
                "INV3001,CUST3001,1000,RESERVED,PRODUCE",
                "INV3002,CUST3002,2000,RESERVED,CRAFT",
                "INV3003,CUST3003,3000,DRAFT,FOOD",
                "INV3004,CUST3004,4000,RESERVED,CHECK",
                "INV3005,CUST3005,5000,RESERVED,FOOD",
            ],
            [
                "INV3001,CUST9999,1000,PRODUCE",
                "INV3002,CUST3002,2100,CRAFT",
                "INV3003,CUST3003,3000,FOOD",
                "INV3004,CUST3004,4000,CHECK",
                "INV3005,CUST3005,5000,FOOD",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["stall_type"] == "FOOD"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_count"] == 4
        assert summary["unmatched_amount_cents"] == 10100


    def test_duplicate_refunds_do_not_reuse_consumed_record(self):
        """Only the earliest eligible refund may consume a matching stall."""
        write_inputs(
            [
                "INV5551,CUST5551,7500,RESERVED,CRAFT",
                "INV5552,CUST5552,8800,RESERVED,PRODUCE",
            ],
            [
                "INV5551,CUST5551,7500,CRAFT",
                "INV5551,CUST5551,7500,CRAFT",
                "INV5552,CUST5552,8800,PRODUCE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["stall_type"] == ""
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 16300
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 7500


    def test_matching_trims_fields_and_normalizes_stall_type_status_case(self):
        """Matching should tolerate surrounding spaces and case differences in stall_type/status values."""
        write_inputs(
            [
                " INV6601 , CUST6601 , 6100 , reserved , craft ",
                "INV6602,CUST6602,7200,RESERVED,food",
            ],
            [
                "INV6601,CUST6601, 6100 ,CRAFT",
                " INV6602 , CUST6602 ,7200, FOOD ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["stall_id"] for row in rows] == ["INV6601", "INV6602"]
        assert [row["vendor_id"] for row in rows] == ["CUST6601", "CUST6602"]
        assert [row["stall_type"] for row in rows] == ["CRAFT", "FOOD"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 13300


    def test_report_output_trims_identifier_fields(self):
        """Report rows should trim incidental spaces from stall_id and vendor_id output fields."""
        write_inputs(
            [
                " INV7701 , CUST7701 , 4500 , RESERVED , PRODUCE ",
            ],
            [
                " INV7701 , CUST7701 , 4500 , PRODUCE ",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["stall_id"] == "INV7701"
        assert rows[0]["vendor_id"] == "CUST7701"
        assert rows[0]["stall_type"] == "PRODUCE"
        assert summary["matched_count"] == 1


    def test_report_schema_and_refund_input_order_are_stable(self):
        """The report should use the required schema and preserve refund input order."""
        write_inputs(
            [
                "INV9001,CUST9001,100,RESERVED,PRODUCE",
                "INV9002,CUST9002,200,RESERVED,CRAFT",
                "INV9003,CUST9003,300,RESERVED,FOOD",
            ],
            [
                "INV9003,CUST9003,300,FOOD",
                "INV9001,CUST9001,100,PRODUCE",
                "INV9002,CUST9002,200,CRAFT",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "stall_id,vendor_id,stall_type,amount_cents,status"
        assert [row["stall_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
        assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
