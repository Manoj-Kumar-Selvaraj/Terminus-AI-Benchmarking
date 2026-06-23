"""Verifier tests for the visit credit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "visits.csv"
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
    INVOICES.write_text("visit_id,owner_id,amount_cents,status,clinic\n" + "\n".join(bill_rows) + "\n")
    PAYMENTS.write_text("visit_id,owner_id,amount_cents,clinic\n" + "\n".join(refund_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())



class TestMilestone1:
    def test_mobile_refund_matches_and_counts_positive_amount(self):
        """MOBILE credits should match closed visits and add positive cents to matched totals."""
        write_inputs(
            [
                "INV20260401001,CUST1001,12500,CLOSED,MAIN",
                "INV20260401002,CUST1002,9900,CLOSED,MOBILE",
            ],
            [
                "INV20260401001,CUST1001,12500,MAIN",
                "INV20260401002,CUST1002,9900,MOBILE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["clinic"] == "MOBILE"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 22400
        assert summary["unmatched_count"] == 0


    def test_visit_id_match_uses_full_identifier(self):
        """A credit must not match a visit that only shares the leading visit prefix."""
        write_inputs(
            [
                "INV777770001,CUST2001,3300,CLOSED,MAIN",
                "INV777770002,CUST2001,3300,CLOSED,MAIN",
            ],
            [
                "INV777770003,CUST2001,3300,MAIN",
                "INV777770002,CUST2001,3300,MAIN",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["clinic"] == ""
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300


    def test_customer_amount_status_and_clinic_all_gate_matching(self):
        """Customer, amount, closed status, and allowed clinic must all be satisfied."""
        write_inputs(
            [
                "INV3001,CUST3001,1000,CLOSED,MAIN",
                "INV3002,CUST3002,2000,CLOSED,MOBILE",
                "INV3003,CUST3003,3000,DRAFT,ER",
                "INV3004,CUST3004,4000,CLOSED,CHECK",
                "INV3005,CUST3005,5000,CLOSED,ER",
            ],
            [
                "INV3001,CUST9999,1000,MAIN",
                "INV3002,CUST3002,2100,MOBILE",
                "INV3003,CUST3003,3000,ER",
                "INV3004,CUST3004,4000,CHECK",
                "INV3005,CUST3005,5000,ER",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["clinic"] == "ER"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_count"] == 4
        assert summary["unmatched_amount_cents"] == 10100


    def test_duplicate_refunds_do_not_reuse_consumed_bill(self):
        """Only the earliest eligible credit may consume a matching visit."""
        write_inputs(
            [
                "INV5551,CUST5551,7500,CLOSED,MOBILE",
                "INV5552,CUST5552,8800,CLOSED,MAIN",
            ],
            [
                "INV5551,CUST5551,7500,MOBILE",
                "INV5551,CUST5551,7500,MOBILE",
                "INV5552,CUST5552,8800,MAIN",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["clinic"] == ""
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 16300
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 7500


    def test_matching_trims_fields_and_normalizes_clinic_status_case(self):
        """Matching should tolerate surrounding spaces and case differences in clinic/status values."""
        write_inputs(
            [
                " INV6601 , CUST6601 , 6100 , closed , mobile ",
                "INV6602,CUST6602,7200,CLOSED,er",
            ],
            [
                "INV6601,CUST6601, 6100 ,MOBILE",
                " INV6602 , CUST6602 ,7200, ER ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["visit_id"] for row in rows] == ["INV6601", "INV6602"]
        assert [row["owner_id"] for row in rows] == ["CUST6601", "CUST6602"]
        assert [row["clinic"] for row in rows] == ["MOBILE", "ER"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 13300


    def test_report_schema_and_refund_input_order_are_stable(self):
        """The report should use the required schema and preserve credit input order."""
        write_inputs(
            [
                "INV9001,CUST9001,100,CLOSED,MAIN",
                "INV9002,CUST9002,200,CLOSED,MOBILE",
                "INV9003,CUST9003,300,CLOSED,ER",
            ],
            [
                "INV9003,CUST9003,300,ER",
                "INV9001,CUST9001,100,MAIN",
                "INV9002,CUST9002,200,MOBILE",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "visit_id,owner_id,clinic,amount_cents,status"
        assert [row["visit_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
        assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_report_output_trims_identifier_fields(self):
        """Report rows should trim incidental spaces from visit_id and owner_id output fields."""
        write_inputs(
            [
                " INV7701 , CUST7701 , 4500 , CLOSED , MOBILE ",
            ],
            [
                " INV7701 , CUST7701 , 4500 , MOBILE ",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["visit_id"] == "INV7701"
        assert rows[0]["owner_id"] == "CUST7701"
        assert rows[0]["clinic"] == "MOBILE"
        assert rows[0]["amount_cents"] == "4500"
        assert summary["matched_count"] == 1
