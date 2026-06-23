"""Verifier tests for the token credit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "plays.csv"
PAYMENTS = APP / "data" / "token_credits.csv"
REPORT = APP / "out" / "token_credit_report.csv"
SUMMARY = APP / "out" / "token_credit_summary.json"
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


def write_inputs(bill_rows, credit_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    INVOICES.write_text("play_id,member_id,amount_cents,status,token_tier\n" + "\n".join(bill_rows) + "\n")
    PAYMENTS.write_text("play_id,member_id,amount_cents,token_tier\n" + "\n".join(credit_rows) + "\n")
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

    def test_month_credit_matches_and_counts_positive_amount(self):
        """PRO credits should match completed trips and add positive cents to matched totals."""
        write_inputs(
            [
                "ARC20260401001,CUST1001,12500,COMPLETED,ARC",
                "ARC20260401002,CUST1002,9900,COMPLETED,PRO",
            ],
            [
                "ARC20260401001,CUST1001,12500,ARC",
                "ARC20260401002,CUST1002,9900,PRO",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["token_tier"] == "PRO"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 22400
        assert summary["unmatched_count"] == 0


    def test_play_id_match_uses_full_identifier(self):
        """A credit must not match a trip that only shares the leading trip prefix."""
        write_inputs(
            [
                "ARC777770001,CUST2001,3300,COMPLETED,ARC",
                "ARC777770002,CUST2001,3300,COMPLETED,ARC",
            ],
            [
                "ARC777770003,CUST2001,3300,ARC",
                "ARC777770002,CUST2001,3300,ARC",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["token_tier"] == ""
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300


    def test_customer_amount_status_and_token_tier_all_gate_matching(self):
        """Customer, amount, completed status, and allowed token_tier must all be satisfied."""
        write_inputs(
            [
                "ARC3001,CUST3001,1000,COMPLETED,ARC",
                "ARC3002,CUST3002,2000,COMPLETED,PRO",
                "ARC3003,CUST3003,3000,DRAFT,VIP",
                "ARC3004,CUST3004,4000,COMPLETED,CHECK",
                "ARC3005,CUST3005,5000,COMPLETED,VIP",
            ],
            [
                "ARC3001,CUST9999,1000,ARC",
                "ARC3002,CUST3002,2100,PRO",
                "ARC3003,CUST3003,3000,VIP",
                "ARC3004,CUST3004,4000,CHECK",
                "ARC3005,CUST3005,5000,VIP",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["token_tier"] == "VIP"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_count"] == 4
        assert summary["unmatched_amount_cents"] == 10100


    def test_duplicate_credits_do_not_reuse_consumed_record(self):
        """Only the earliest eligible credit may consume a matching trip."""
        write_inputs(
            [
                "ARC5551,CUST5551,7500,COMPLETED,PRO",
                "ARC5552,CUST5552,8800,COMPLETED,ARC",
            ],
            [
                "ARC5551,CUST5551,7500,PRO",
                "ARC5551,CUST5551,7500,PRO",
                "ARC5552,CUST5552,8800,ARC",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["token_tier"] == ""
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 16300
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 7500


    def test_matching_trims_fields_and_normalizes_token_tier_status_case(self):
        """Matching should tolerate surrounding spaces and case differences in token_tier/status values."""
        write_inputs(
            [
                " ARC6601 , CUST6601 , 6100 , completed , arc ",
                "ARC6602,CUST6602,7200,COMPLETED,vip",
            ],
            [
                "ARC6601,CUST6601, 6100 ,ARC",
                " ARC6602 , CUST6602 ,7200, VIP ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["play_id"] for row in rows] == ["ARC6601", "ARC6602"]
        assert [row["member_id"] for row in rows] == ["CUST6601", "CUST6602"]
        assert [row["token_tier"] for row in rows] == ["ARC", "VIP"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 13300


    def test_report_schema_and_credit_input_order_are_stable(self):
        """The report should use the required schema and preserve credit input order."""
        write_inputs(
            [
                "ARC9001,CUST9001,100,COMPLETED,ARC",
                "ARC9002,CUST9002,200,COMPLETED,PRO",
                "ARC9003,CUST9003,300,COMPLETED,VIP",
            ],
            [
                "ARC9003,CUST9003,300,VIP",
                "ARC9001,CUST9001,100,ARC",
                "ARC9002,CUST9002,200,PRO",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "play_id,member_id,token_tier,amount_cents,status"
        assert [row["play_id"] for row in rows] == ["ARC9003", "ARC9001", "ARC9002"]
        assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
