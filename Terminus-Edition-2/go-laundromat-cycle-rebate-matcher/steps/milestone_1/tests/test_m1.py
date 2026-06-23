"""Verifier tests for the rebate reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
SOURCE_FILE = APP / "data" / "cycles.csv"
ACTION_FILE = APP / "data" / "rebates.csv"
REPORT = APP / "out" / "cycle_rebate_report.csv"
SUMMARY = APP / "out" / "cycle_rebate_summary.json"
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
    SOURCE_FILE.write_text("cycle_id,customer_id,amount_cents,status,machine_tier\n" + "\n".join(bill_rows) + "\n")
    ACTION_FILE.write_text("cycle_id,customer_id,amount_cents,machine_tier\n" + "\n".join(credit_rows) + "\n")
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
        """DRY credits should match completed source rows and add positive cents to matched totals."""
        write_inputs(
            [
                "LDM20260401001,CUST1001,12500,COMPLETED,WASH",
                "LDM20260401002,CUST1002,9900,COMPLETED,DRY",
            ],
            [
                "LDM20260401001,CUST1001,12500,WASH",
                "LDM20260401002,CUST1002,9900,DRY",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["machine_tier"] == "DRY"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 22400
        assert summary["unmatched_count"] == 0


    def test_cycle_id_match_uses_full_identifier(self):
        """A credit must not match a source row that only shares the leading source row prefix."""
        write_inputs(
            [
                "LDM777770001,CUST2001,3300,COMPLETED,WASH",
                "LDM777770002,CUST2001,3300,COMPLETED,WASH",
            ],
            [
                "LDM777770003,CUST2001,3300,WASH",
                "LDM777770002,CUST2001,3300,WASH",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["machine_tier"] == ""
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300


    def test_customer_amount_status_and_machine_tier_all_gate_matching(self):
        """Customer, amount, completed status, and allowed machine_tier must all be satisfied."""
        write_inputs(
            [
                "LDM3001,CUST3001,1000,COMPLETED,WASH",
                "LDM3002,CUST3002,2000,COMPLETED,DRY",
                "LDM3003,CUST3003,3000,DRAFT,COMBO",
                "LDM3004,CUST3004,4000,COMPLETED,CHECK",
                "LDM3005,CUST3005,5000,COMPLETED,COMBO",
            ],
            [
                "LDM3001,CUST9999,1000,WASH",
                "LDM3002,CUST3002,2100,DRY",
                "LDM3003,CUST3003,3000,COMBO",
                "LDM3004,CUST3004,4000,CHECK",
                "LDM3005,CUST3005,5000,COMBO",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["machine_tier"] == "COMBO"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_count"] == 4
        assert summary["unmatched_amount_cents"] == 10100


    def test_duplicate_rebates_do_not_reuse_consumed_record(self):
        """Only the earliest eligible rebate may consume a matching source row."""
        write_inputs(
            [
                "LDM5551,CUST5551,7500,COMPLETED,DRY",
                "LDM5552,CUST5552,8800,COMPLETED,WASH",
            ],
            [
                "LDM5551,CUST5551,7500,DRY",
                "LDM5551,CUST5551,7500,DRY",
                "LDM5552,CUST5552,8800,WASH",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["machine_tier"] == ""
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 16300
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 7500


    def test_matching_trims_fields_and_normalizes_machine_tier_status_case(self):
        """Matching should tolerate surrounding spaces and case differences in machine_tier/status values."""
        write_inputs(
            [
                " LDM6601 , CUST6601 , 6100 , completed , wash ",
                "LDM6602,CUST6602,7200,COMPLETED,dry",
            ],
            [
                "LDM6601,CUST6601, 6100 ,WASH",
                " LDM6602 , CUST6602 ,7200, DRY ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["cycle_id"] for row in rows] == ["LDM6601", "LDM6602"]
        assert [row["customer_id"] for row in rows] == ["CUST6601", "CUST6602"]
        assert [row["machine_tier"] for row in rows] == ["WASH", "DRY"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 13300


    def test_report_schema_and_rebate_input_order_are_stable(self):
        """The report should use the required schema and preserve rebate input order."""
        write_inputs(
            [
                "LDM9001,CUST9001,100,COMPLETED,WASH",
                "LDM9002,CUST9002,200,COMPLETED,DRY",
                "LDM9003,CUST9003,300,COMPLETED,COMBO",
            ],
            [
                "LDM9003,CUST9003,300,COMBO",
                "LDM9001,CUST9001,100,WASH",
                "LDM9002,CUST9002,200,DRY",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "cycle_id,customer_id,machine_tier,amount_cents,status"
        assert [row["cycle_id"] for row in rows] == ["LDM9003", "LDM9001", "LDM9002"]
        assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_unmatched_report_trims_identifier_fields(self):
        """Unmatched report rows must trim cycle_id and customer_id output fields."""
        write_inputs(
            [" LDM7701 , CUST7701 , 500 , COMPLETED , WASH "],
            [" LDM7701 , CUST7701 , 600 , WASH "],
        )
        rows, _ = run_program()
        assert len(rows) == 1
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["cycle_id"] == "LDM7701"
        assert rows[0]["customer_id"] == "CUST7701"
        assert rows[0]["machine_tier"] == ""
