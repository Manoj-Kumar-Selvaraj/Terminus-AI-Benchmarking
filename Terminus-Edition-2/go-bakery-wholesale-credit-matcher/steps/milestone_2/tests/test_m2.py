"""Verifier tests for the order credit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
ORDERS = APP / "data" / "orders.csv"
CREDITS = APP / "data" / "credits.csv"
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
    assert BIN.exists()


def write_inputs(order_rows, credit_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    ORDERS.write_text("order_id,cafe_id,amount_cents,status,route\n" + "\n".join(order_rows) + "\n")
    CREDITS.write_text("order_id,cafe_id,amount_cents,route\n" + "\n".join(credit_rows) + "\n")
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

    def test_regional_credit_matches_and_counts_positive_amount(self):
        """REGIONAL credits should match fulfilled orders and add positive cents to matched totals."""
        write_inputs(
            [
                "INV20260401001,CUST1001,12500,FULFILLED,LOCAL",
                "INV20260401002,CUST1002,9900,FULFILLED,REGIONAL",
            ],
            [
                "INV20260401001,CUST1001,12500,LOCAL",
                "INV20260401002,CUST1002,9900,REGIONAL",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["route"] == "REGIONAL"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 22400
        assert summary["unmatched_count"] == 0


    def test_order_id_match_uses_full_identifier(self):
        """A credit must not match an order that only shares the leading order prefix."""
        write_inputs(
            [
                "INV777770001,CUST2001,3300,FULFILLED,LOCAL",
                "INV777770002,CUST2001,3300,FULFILLED,LOCAL",
            ],
            [
                "INV777770003,CUST2001,3300,LOCAL",
                "INV777770002,CUST2001,3300,LOCAL",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["route"] == ""
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300


    def test_cafe_amount_status_and_route_all_gate_matching(self):
        """Cafe, amount, fulfilled status, and allowed route must all be satisfied."""
        write_inputs(
            [
                "INV3001,CUST3001,1000,FULFILLED,LOCAL",
                "INV3002,CUST3002,2000,FULFILLED,REGIONAL",
                "INV3003,CUST3003,3000,DRAFT,EXPORT",
                "INV3004,CUST3004,4000,FULFILLED,CHECK",
                "INV3005,CUST3005,5000,FULFILLED,EXPORT",
            ],
            [
                "INV3001,CUST9999,1000,LOCAL",
                "INV3002,CUST3002,2100,REGIONAL",
                "INV3003,CUST3003,3000,EXPORT",
                "INV3004,CUST3004,4000,CHECK",
                "INV3005,CUST3005,5000,EXPORT",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["route"] == "EXPORT"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_count"] == 4
        assert summary["unmatched_amount_cents"] == 10100


    def test_duplicate_credits_do_not_reuse_consumed_record(self):
        """Only the earliest eligible credit may consume a matching order."""
        write_inputs(
            [
                "INV5551,CUST5551,7500,FULFILLED,REGIONAL",
                "INV5552,CUST5552,8800,FULFILLED,LOCAL",
            ],
            [
                "INV5551,CUST5551,7500,REGIONAL",
                "INV5551,CUST5551,7500,REGIONAL",
                "INV5552,CUST5552,8800,LOCAL",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["route"] == ""
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 16300
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 7500


    def test_matching_trims_fields_and_normalizes_route_status_case(self):
        """Matching should tolerate surrounding spaces and case differences in route/status values."""
        write_inputs(
            [
                " INV6601 , CUST6601 , 6100 , fulfilled , regional ",
                "INV6602,CUST6602,7200,FULFILLED,export",
            ],
            [
                "INV6601,CUST6601, 6100 ,REGIONAL",
                " INV6602 , CUST6602 ,7200, EXPORT ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["order_id"] for row in rows] == ["INV6601", "INV6602"]
        assert [row["cafe_id"] for row in rows] == ["CUST6601", "CUST6602"]
        assert [row["route"] for row in rows] == ["REGIONAL", "EXPORT"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 13300


    def test_mismatched_routes_do_not_match_when_other_fields_align(self):
        """Order and credit routes must be equal after canonicalization, not merely allowed."""
        write_inputs(
            ["INV8801,CUST8801,5000,FULFILLED,LOCAL"],
            ["INV8801,CUST8801,5000,REGIONAL"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["route"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 5000,
        }

    def test_legacy_route_aliases_match_and_emit_canonical_routes(self):
        """Legacy LOC, REG, and EXP credit routes should match and report canonical routes."""
        write_inputs(
            [
                "INV7701,CUST7701,8800,FULFILLED,REGIONAL",
                "INV7702,CUST7702,9100,fulfilled,export",
                "INV7703,CUST7703,4200,FULFILLED,LOCAL",
                "INV7704,CUST7704,3300,FULFILLED,CHECK",
            ],
            [
                "INV7701,CUST7701,8800,reg",
                "INV7702,CUST7702,9100,EXP",
                "INV7703,CUST7703,4200,LOC",
                "INV7704,CUST7704,3300,chk",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["route"] for row in rows] == ["REGIONAL", "EXPORT", "LOCAL", ""]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 22100
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 3300


    def test_report_schema_and_credit_input_order_are_stable(self):
        """The report should use the required schema and preserve credit input order."""
        write_inputs(
            [
                "INV9001,CUST9001,100,FULFILLED,LOCAL",
                "INV9002,CUST9002,200,FULFILLED,REGIONAL",
                "INV9003,CUST9003,300,FULFILLED,EXPORT",
            ],
            [
                "INV9003,CUST9003,300,EXPORT",
                "INV9001,CUST9001,100,LOCAL",
                "INV9002,CUST9002,200,REGIONAL",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "order_id,cafe_id,route,amount_cents,status"
        assert [row["order_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
        assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
