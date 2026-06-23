"""Verifier tests for the rebate reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
SOURCE_FILE = APP / "data" / "weighins.csv"
ACTION_FILE = APP / "data" / "rebates.csv"
REPORT = APP / "out" / "weighin_rebate_report.csv"
SUMMARY = APP / "out" / "weighin_rebate_summary.json"
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
    SOURCE_FILE.write_text("weighin_id,account_id,amount_cents,status,material_tier\n" + "\n".join(bill_rows) + "\n")
    ACTION_FILE.write_text("weighin_id,account_id,amount_cents,material_tier\n" + "\n".join(credit_rows) + "\n")
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

    def test_rebate_matches_and_counts_positive_amount(self):
        """PAPER credits should match completed source rows and add positive cents to matched totals."""
        write_inputs(
            [
                "RCY20260401001,CUST1001,12500,COMPLETED,METAL",
                "RCY20260401002,CUST1002,9900,COMPLETED,PAPER",
            ],
            [
                "RCY20260401001,CUST1001,12500,METAL",
                "RCY20260401002,CUST1002,9900,PAPER",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["material_tier"] == "PAPER"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 22400
        assert summary["unmatched_count"] == 0


    def test_weighin_id_match_uses_full_identifier(self):
        """A credit must not match a source row that only shares the leading source row prefix."""
        write_inputs(
            [
                "RCY777770001,CUST2001,3300,COMPLETED,METAL",
                "RCY777770002,CUST2001,3300,COMPLETED,METAL",
            ],
            [
                "RCY777770003,CUST2001,3300,METAL",
                "RCY777770002,CUST2001,3300,METAL",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["material_tier"] == ""
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300


    def test_customer_amount_status_and_material_tier_all_gate_matching(self):
        """Customer, amount, completed status, and allowed material_tier must all be satisfied."""
        write_inputs(
            [
                "RCY3001,CUST3001,1000,COMPLETED,METAL",
                "RCY3002,CUST3002,2000,COMPLETED,PAPER",
                "RCY3003,CUST3003,3000,DRAFT,GLASS",
                "RCY3004,CUST3004,4000,COMPLETED,CHECK",
                "RCY3005,CUST3005,5000,COMPLETED,GLASS",
            ],
            [
                "RCY3001,CUST9999,1000,METAL",
                "RCY3002,CUST3002,2100,PAPER",
                "RCY3003,CUST3003,3000,GLASS",
                "RCY3004,CUST3004,4000,CHECK",
                "RCY3005,CUST3005,5000,GLASS",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["material_tier"] == "GLASS"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_count"] == 4
        assert summary["unmatched_amount_cents"] == 10100


    def test_duplicate_rebates_do_not_reuse_consumed_record(self):
        """Only the earliest eligible rebate may consume a matching source row."""
        write_inputs(
            [
                "RCY5551,CUST5551,7500,COMPLETED,PAPER",
                "RCY5552,CUST5552,8800,COMPLETED,METAL",
            ],
            [
                "RCY5551,CUST5551,7500,PAPER",
                "RCY5551,CUST5551,7500,PAPER",
                "RCY5552,CUST5552,8800,METAL",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["material_tier"] == ""
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 16300
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 7500


    def test_matching_trims_fields_and_normalizes_material_tier_status_case(self):
        """Matching should tolerate surrounding spaces and case differences in material_tier/status values."""
        write_inputs(
            [
                " RCY6601 , CUST6601 , 6100 , completed , metal ",
                "RCY6602,CUST6602,7200,COMPLETED,paper",
            ],
            [
                "RCY6601,CUST6601, 6100 ,METAL",
                " RCY6602 , CUST6602 ,7200, PAPER ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["weighin_id"] for row in rows] == ["RCY6601", "RCY6602"]
        assert [row["account_id"] for row in rows] == ["CUST6601", "CUST6602"]
        assert [row["material_tier"] for row in rows] == ["METAL", "PAPER"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 13300


    def test_report_schema_and_rebate_input_order_are_stable(self):
        """The report should use the required schema and preserve rebate input order."""
        write_inputs(
            [
                "RCY9001,CUST9001,100,COMPLETED,METAL",
                "RCY9002,CUST9002,200,COMPLETED,PAPER",
                "RCY9003,CUST9003,300,COMPLETED,GLASS",
            ],
            [
                "RCY9003,CUST9003,300,GLASS",
                "RCY9001,CUST9001,100,METAL",
                "RCY9002,CUST9002,200,PAPER",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "weighin_id,account_id,material_tier,amount_cents,status"
        assert [row["weighin_id"] for row in rows] == ["RCY9003", "RCY9001", "RCY9002"]
        assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
