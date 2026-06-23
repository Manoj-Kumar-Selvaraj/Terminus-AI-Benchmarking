"""Verifier tests for the deposit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
SOURCE_FILE = APP / "data" / "tours.csv"
ACTION_FILE = APP / "data" / "deposits.csv"
REPORT = APP / "out" / "tour_deposit_report.csv"
SUMMARY = APP / "out" / "tour_deposit_summary.json"
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


def write_inputs(bill_rows, credit_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_FILE.write_text("tour_id,passenger_id,amount_cents,status,cabin_tier\n" + "\n".join(bill_rows) + "\n")
    ACTION_FILE.write_text("tour_id,passenger_id,amount_cents,cabin_tier\n" + "\n".join(credit_rows) + "\n")
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

    def test_deposit_matches_and_counts_positive_amount(self):
        """PREM credits should match completed source rows and add positive cents to matched totals."""
        write_inputs(
            [
                "HEL20260401001,CUST1001,12500,COMPLETED,STD",
                "HEL20260401002,CUST1002,9900,COMPLETED,PREM",
            ],
            [
                "HEL20260401001,CUST1001,12500,STD",
                "HEL20260401002,CUST1002,9900,PREM",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["cabin_tier"] == "PREM"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 22400
        assert summary["unmatched_count"] == 0


    def test_tour_id_match_uses_full_identifier(self):
        """A credit must not match a source row that only shares the leading source row prefix."""
        write_inputs(
            [
                "HEL777770001,CUST2001,3300,COMPLETED,STD",
                "HEL777770002,CUST2001,3300,COMPLETED,STD",
            ],
            [
                "HEL777770003,CUST2001,3300,STD",
                "HEL777770002,CUST2001,3300,STD",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["cabin_tier"] == ""
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300


    def test_customer_amount_status_and_cabin_tier_all_gate_matching(self):
        """Customer, amount, completed status, and allowed cabin_tier must all be satisfied."""
        write_inputs(
            [
                "HEL3001,CUST3001,1000,COMPLETED,STD",
                "HEL3002,CUST3002,2000,COMPLETED,PREM",
                "HEL3003,CUST3003,3000,DRAFT,LUX",
                "HEL3004,CUST3004,4000,COMPLETED,CHECK",
                "HEL3005,CUST3005,5000,COMPLETED,LUX",
            ],
            [
                "HEL3001,CUST9999,1000,STD",
                "HEL3002,CUST3002,2100,PREM",
                "HEL3003,CUST3003,3000,LUX",
                "HEL3004,CUST3004,4000,CHECK",
                "HEL3005,CUST3005,5000,LUX",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["cabin_tier"] == "LUX"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_count"] == 4
        assert summary["unmatched_amount_cents"] == 10100


    def test_duplicate_deposits_do_not_reuse_consumed_record(self):
        """Only the earliest eligible deposit may consume a matching source row."""
        write_inputs(
            [
                "HEL5551,CUST5551,7500,COMPLETED,PREM",
                "HEL5552,CUST5552,8800,COMPLETED,STD",
            ],
            [
                "HEL5551,CUST5551,7500,PREM",
                "HEL5551,CUST5551,7500,PREM",
                "HEL5552,CUST5552,8800,STD",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["cabin_tier"] == ""
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 16300
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 7500


    def test_matching_trims_fields_and_normalizes_cabin_tier_status_case(self):
        """Matching should tolerate surrounding spaces and case differences in cabin_tier/status values."""
        write_inputs(
            [
                " HEL6601 , CUST6601 , 6100 , completed , std ",
                "HEL6602,CUST6602,7200,COMPLETED,prem",
            ],
            [
                "HEL6601,CUST6601, 6100 ,STD",
                " HEL6602 , CUST6602 ,7200, PREM ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["tour_id"] for row in rows] == ["HEL6601", "HEL6602"]
        assert [row["passenger_id"] for row in rows] == ["CUST6601", "CUST6602"]
        assert [row["cabin_tier"] for row in rows] == ["STD", "PREM"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 13300


    def test_legacy_cabin_tier_aliases_match_and_emit_canonical_cabin_tiers(self):
        """Legacy ST, PM, and LX credit cabin_tiers should match and report canonical cabin_tiers."""
        write_inputs(
            [
                "HEL7701,CUST7701,8800,COMPLETED,PREM",
                "HEL7702,CUST7702,9100,completed,lux",
                "HEL7703,CUST7703,4200,COMPLETED,STD",
                "HEL7704,CUST7704,3300,COMPLETED,CHECK",
            ],
            [
                "HEL7701,CUST7701,8800,pm",
                "HEL7702,CUST7702,9100,LX",
                "HEL7703,CUST7703,4200,ST",
                "HEL7704,CUST7704,3300,chk",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["cabin_tier"] for row in rows] == ["PREM", "LUX", "STD", ""]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 22100
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 3300


    def test_report_schema_and_deposit_input_order_are_stable(self):
        """The report should use the required schema and preserve deposit input order."""
        write_inputs(
            [
                "HEL9001,CUST9001,100,COMPLETED,STD",
                "HEL9002,CUST9002,200,COMPLETED,PREM",
                "HEL9003,CUST9003,300,COMPLETED,LUX",
            ],
            [
                "HEL9003,CUST9003,300,LUX",
                "HEL9001,CUST9001,100,STD",
                "HEL9002,CUST9002,200,PREM",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "tour_id,passenger_id,cabin_tier,amount_cents,status"
        assert [row["tour_id"] for row in rows] == ["HEL9003", "HEL9001", "HEL9002"]
        assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_alias_matching_trims_surrounding_spaces_on_compared_fields(self):
        """Legacy alias matching should trim surrounding spaces from tour and deposit fields."""
        write_inputs(
            [
                " HEL8801 , CUST8801 , 5500 , COMPLETED , std ",
                "HEL8802,CUST8802,6600,COMPLETED,lux",
            ],
            [
                " HEL8801 , CUST8801 , 5500 , st ",
                " HEL8802 , CUST8802 ,6600, LX ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["cabin_tier"] for row in rows] == ["STD", "LUX"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 12100

    def test_duplicate_alias_deposits_do_not_reuse_consumed_tour(self):
        """Only the earliest eligible alias deposit should consume a matching tour row."""
        write_inputs(
            [
                "HEL8803,CUST8803,7700,COMPLETED,PREM",
                "HEL8804,CUST8804,8800,COMPLETED,STD",
            ],
            [
                "HEL8803,CUST8803,7700,PM",
                "HEL8803,CUST8803,7700,PM",
                "HEL8804,CUST8804,8800,ST",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["cabin_tier"] == ""
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 16500
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 7700

    def test_full_tour_id_comparison_rejects_prefix_only_match(self):
        """Alias matching must compare full tour_id values, not shared prefixes."""
        write_inputs(
            ["HEL20260401001,CUST01,500,COMPLETED,STD"],
            ["HEL20260401002,CUST01,500,ST"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["cabin_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500
