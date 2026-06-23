"""Verifier tests for the loyalty adjustment reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "accruals.csv"
PAYMENTS = APP / "data" / "adjustments.csv"
REPORT = APP / "out" / "adjustment_report.csv"
SUMMARY = APP / "out" / "adjustment_summary.json"
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


def write_inputs(accrual_rows, adjustment_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    INVOICES.write_text("accrual_id,member_id,amount_cents,status,reason\n" + "\n".join(accrual_rows) + "\n")
    PAYMENTS.write_text("accrual_id,member_id,amount_cents,reason\n" + "\n".join(adjustment_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())



class TestMilestone1:
    """Milestone 1 verifier scenarios for loyalty adjustments."""

    def test_bonus_adjustment_matches_and_counts_positive_amount(self):
        """BONUS adjustments should match posted accruals and add positive cents to matched totals."""
        write_inputs(
            [
                "INV20260401001,CUST1001,12500,POSTED,PURCHASE",
                "INV20260401002,CUST1002,9900,POSTED,BONUS",
            ],
            [
                "INV20260401001,CUST1001,12500,PURCHASE",
                "INV20260401002,CUST1002,9900,BONUS",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["reason"] == "BONUS"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 22400
        assert summary["unmatched_count"] == 0


    def test_accrual_id_match_uses_full_identifier(self):
        """An adjustment must not match an accrual that only shares the leading accrual prefix."""
        write_inputs(
            [
                "INV777770001,CUST2001,3300,POSTED,PURCHASE",
                "INV777770002,CUST2001,3300,POSTED,PURCHASE",
            ],
            [
                "INV777770003,CUST2001,3300,PURCHASE",
                "INV777770002,CUST2001,3300,PURCHASE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["reason"] == ""
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300


    def test_member_amount_status_and_reason_all_gate_matching(self):
        """Member, amount, posted status, and allowed reason must all be satisfied."""
        write_inputs(
            [
                "INV3001,CUST3001,1000,POSTED,PURCHASE",
                "INV3002,CUST3002,2000,POSTED,BONUS",
                "INV3003,CUST3003,3000,DRAFT,PROMO",
                "INV3004,CUST3004,4000,POSTED,CHECK",
                "INV3005,CUST3005,5000,POSTED,PROMO",
            ],
            [
                "INV3001,CUST9999,1000,PURCHASE",
                "INV3002,CUST3002,2100,BONUS",
                "INV3003,CUST3003,3000,PROMO",
                "INV3004,CUST3004,4000,CHECK",
                "INV3005,CUST3005,5000,PROMO",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["reason"] == "PROMO"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_count"] == 4
        assert summary["unmatched_amount_cents"] == 10100


    def test_duplicate_adjustments_do_not_reuse_consumed_accrual(self):
        """Only the earliest eligible adjustment may consume a matching accrual."""
        write_inputs(
            [
                "INV5551,CUST5551,7500,POSTED,BONUS",
                "INV5552,CUST5552,8800,POSTED,PURCHASE",
            ],
            [
                "INV5551,CUST5551,7500,BONUS",
                "INV5551,CUST5551,7500,BONUS",
                "INV5552,CUST5552,8800,PURCHASE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["reason"] == ""
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 16300
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 7500


    def test_matching_trims_fields_and_normalizes_reason_status_case(self):
        """Matching should tolerate surrounding spaces and case differences in reason/status values."""
        write_inputs(
            [
                " INV6601 , CUST6601 , 6100 , posted , bonus ",
                "INV6602,CUST6602,7200,POSTED,promo",
            ],
            [
                "INV6601,CUST6601, 6100 ,BONUS",
                " INV6602 , CUST6602 ,7200, PROMO ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["accrual_id"] for row in rows] == ["INV6601", "INV6602"]
        assert [row["member_id"] for row in rows] == ["CUST6601", "CUST6602"]
        assert [row["reason"] for row in rows] == ["BONUS", "PROMO"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 13300


    def test_report_schema_and_adjustment_input_order_are_stable(self):
        """The report should use the required schema and preserve adjustment input order."""
        write_inputs(
            [
                "INV9001,CUST9001,100,POSTED,PURCHASE",
                "INV9002,CUST9002,200,POSTED,BONUS",
                "INV9003,CUST9003,300,POSTED,PROMO",
            ],
            [
                "INV9003,CUST9003,300,PROMO",
                "INV9001,CUST9001,100,PURCHASE",
                "INV9002,CUST9002,200,BONUS",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "accrual_id,member_id,reason,amount_cents,status"
        assert [row["accrual_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
        assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
