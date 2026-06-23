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
    """Compile the Go reconciliation CLI once for all milestone 2 tests."""
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


class TestMilestone2:
    """Behavior checks for milestone 2."""

    def test_voucher_matches_and_counts_positive_amount(self):
        """(Regression) MEAL vouchers should still match completed orders after alias normalization."""
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
        """(Regression) A voucher must not match an order that only shares the leading order_id prefix."""
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
        """(Regression) Customer, amount, completed status, and allowed meal_tier must all be satisfied."""
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
        """(Regression) Only the earliest eligible voucher may consume a matching source row."""
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
        """(Regression) Matching should tolerate surrounding spaces and case differences in meal_tier/status values."""
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

    def test_legacy_meal_tier_aliases_match_and_emit_canonical_meal_tiers(self):
        """Legacy SN, ML, and CB voucher meal_tiers should match and report canonical meal_tiers."""
        write_inputs(
            [
                "RLY7701,CUST7701,8800,COMPLETED,MEAL",
                "RLY7702,CUST7702,9100,completed,combo",
                "RLY7703,CUST7703,4200,COMPLETED,SNACK",
                "RLY7704,CUST7704,3300,COMPLETED,CHECK",
            ],
            [
                "RLY7701,CUST7701,8800,ml",
                "RLY7702,CUST7702,9100,CB",
                "RLY7703,CUST7703,4200,SN",
                "RLY7704,CUST7704,3300,chk",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["meal_tier"] for row in rows] == ["MEAL", "COMBO", "SNACK", ""]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 22100
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 3300

    def test_report_schema_and_voucher_input_order_are_stable(self):
        """(Regression) The report should use the required schema and preserve voucher input order."""
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

    def test_ineligible_voucher_contributes_only_valid_positive_amounts(self):
        """Alias work must preserve unmatched amount handling for invalid voucher amounts."""
        write_inputs(
            [
                "RLY9101,CUST9101,1200,COMPLETED,SNACK",
                "RLY9102,CUST9102,900,COMPLETED,MEAL",
                "RLY9103,CUST9103,700,COMPLETED,COMBO",
            ],
            [
                "RLY9101,CUST9101,1200,HOT",
                "RLY9102,CUST9102,12O0,ML",
                "RLY9103,CUST9103,-700,CB",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert [row["meal_tier"] for row in rows] == ["", "", ""]
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 3,
            "unmatched_amount_cents": 1200,
        }
