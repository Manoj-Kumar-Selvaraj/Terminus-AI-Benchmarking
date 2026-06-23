"""Tests for the food-truck rally voucher reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
SOURCE_FILE = APP / "data" / "orders.csv"
ACTION_FILE = APP / "data" / "vouchers.csv"
REPORT = APP / "out" / "rally_voucher_report.csv"
SUMMARY = APP / "out" / "rally_voucher_summary.json"
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


def write_inputs(order_rows, voucher_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_FILE.write_text("order_id,vendor_id,amount_cents,status,meal_tier\n" + "\n".join(order_rows) + "\n")
    ACTION_FILE.write_text("order_id,vendor_id,amount_cents,meal_tier\n" + "\n".join(voucher_rows) + "\n")
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

    def test_voucher_matches_and_counts_positive_amount(self):
        """MEAL vouchers should match completed orders and add positive cents to matched totals."""
        write_inputs(
            [
                "RLY20260401001,CUST1001,12500,COMPLETED,SNACK",
                "RLY20260401002,CUST1002,9900,COMPLETED,MEAL",
            ],
            [
                "RLY20260401001,CUST1001,12500,SNACK",
                "RLY20260401002,CUST1002,9900,MEAL",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["meal_tier"] == "MEAL"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 22400
        assert summary["unmatched_count"] == 0

    def test_order_id_match_uses_full_identifier(self):
        """A voucher must not match an order that only shares the leading order_id prefix."""
        write_inputs(
            [
                "RLY777770001,CUST2001,3300,COMPLETED,SNACK",
                "RLY777770002,CUST2001,3300,COMPLETED,SNACK",
            ],
            [
                "RLY777770003,CUST2001,3300,SNACK",
                "RLY777770002,CUST2001,3300,SNACK",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["meal_tier"] == ""
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300

    def test_customer_amount_status_and_meal_tier_all_gate_matching(self):
        """Customer, amount, completed status, and allowed meal_tier must all be satisfied."""
        write_inputs(
            [
                "RLY3001,CUST3001,1000,COMPLETED,SNACK",
                "RLY3002,CUST3002,2000,COMPLETED,MEAL",
                "RLY3003,CUST3003,3000,DRAFT,COMBO",
                "RLY3004,CUST3004,4000,COMPLETED,CHECK",
                "RLY3005,CUST3005,5000,COMPLETED,COMBO",
            ],
            [
                "RLY3001,CUST9999,1000,SNACK",
                "RLY3002,CUST3002,2100,MEAL",
                "RLY3003,CUST3003,3000,COMBO",
                "RLY3004,CUST3004,4000,CHECK",
                "RLY3005,CUST3005,5000,COMBO",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["meal_tier"] == "COMBO"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_count"] == 4
        assert summary["unmatched_amount_cents"] == 10100

    def test_duplicate_vouchers_do_not_reuse_consumed_record(self):
        """Only the earliest eligible voucher may consume a matching source row."""
        write_inputs(
            [
                "RLY5551,CUST5551,7500,COMPLETED,MEAL",
                "RLY5552,CUST5552,8800,COMPLETED,SNACK",
            ],
            [
                "RLY5551,CUST5551,7500,MEAL",
                "RLY5551,CUST5551,7500,MEAL",
                "RLY5552,CUST5552,8800,SNACK",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["meal_tier"] == ""
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 16300
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 7500

    def test_matching_trims_fields_and_normalizes_meal_tier_status_case(self):
        """Matching should tolerate surrounding spaces and case differences in meal_tier/status values."""
        write_inputs(
            [
                " RLY6601 , CUST6601 , 6100 , completed , snack ",
                "RLY6602,CUST6602,7200,COMPLETED,combo",
            ],
            [
                "RLY6601,CUST6601, 6100 ,SNACK",
                " RLY6602 , CUST6602 ,7200, COMBO ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["order_id"] for row in rows] == ["RLY6601", "RLY6602"]
        assert [row["vendor_id"] for row in rows] == ["CUST6601", "CUST6602"]
        assert [row["meal_tier"] for row in rows] == ["SNACK", "COMBO"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 13300

    def test_report_schema_and_voucher_input_order_are_stable(self):
        """The report should use the required schema and preserve voucher input order."""
        write_inputs(
            [
                "RLY9001,CUST9001,100,COMPLETED,SNACK",
                "RLY9002,CUST9002,200,COMPLETED,MEAL",
                "RLY9003,CUST9003,300,COMPLETED,COMBO",
            ],
            [
                "RLY9003,CUST9003,300,COMBO",
                "RLY9001,CUST9001,100,SNACK",
                "RLY9002,CUST9002,200,MEAL",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "order_id,vendor_id,meal_tier,amount_cents,status"
        assert [row["order_id"] for row in rows] == ["RLY9003", "RLY9001", "RLY9002"]
        assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_unmatched_report_trims_identifier_fields(self):
        """Unmatched report rows must trim order_id and vendor_id output fields."""
        write_inputs(
            [" RLY7701 , CUST7701 , 500 , COMPLETED , SNACK "],
            [" RLY7701 , CUST7701 , 600 , SNACK "],
        )
        rows, _ = run_program()
        assert len(rows) == 1
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["order_id"] == "RLY7701"
        assert rows[0]["vendor_id"] == "CUST7701"
        assert rows[0]["meal_tier"] == ""

    def test_non_numeric_amount_makes_voucher_unmatched(self):
        """A voucher with a non-numeric amount_cents value should stay unmatched."""
        write_inputs(
            ["RLY8801,CUST8801,1200,COMPLETED,SNACK"],
            ["RLY8801,CUST8801,12O0,SNACK"],
        )
        rows, summary = run_program()

        assert len(rows) == 1
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["meal_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 0

    def test_invalid_amount_formats_are_unmatched_without_crashing(self):
        """Zero, signed, negative, decimal, and blank voucher amounts are ineligible."""
        write_inputs(
            [
                "RLYAMT1,CUSTAMT,100,COMPLETED,SNACK",
                "RLYAMT2,CUSTAMT,200,COMPLETED,MEAL",
                "RLYAMT3,CUSTAMT,300,COMPLETED,COMBO",
                "RLYAMT4,CUSTAMT,400,COMPLETED,SNACK",
                "RLYAMT5,CUSTAMT,500,COMPLETED,MEAL",
            ],
            [
                "RLYAMT1,CUSTAMT,0,SNACK",
                "RLYAMT2,CUSTAMT,-200,MEAL",
                "RLYAMT3,CUSTAMT,+300,COMBO",
                "RLYAMT4,CUSTAMT,40.0,SNACK",
                "RLYAMT5,CUSTAMT, ,MEAL",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED"] * 5
        assert [row["meal_tier"] for row in rows] == [""] * 5
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 5,
            "unmatched_amount_cents": 0,
        }
