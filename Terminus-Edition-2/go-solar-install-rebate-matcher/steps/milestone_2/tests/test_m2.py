"""Verifier tests for the rebate reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
SOURCE_FILE = APP / "data" / "installs.csv"
ACTION_FILE = APP / "data" / "rebates.csv"
REPORT = APP / "out" / "solar_rebate_report.csv"
SUMMARY = APP / "out" / "solar_rebate_summary.json"
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
    SOURCE_FILE.write_text("install_id,site_id,amount_cents,status,system_tier\n" + "\n".join(bill_rows) + "\n")
    ACTION_FILE.write_text("install_id,site_id,amount_cents,system_tier\n" + "\n".join(credit_rows) + "\n")
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

    def test_rebate_matches_and_counts_positive_amount(self):
        """BIZ credits should match completed source rows and add positive cents to matched totals."""
        write_inputs(
            [
                "SOL20260401001,CUST1001,12500,COMPLETED,HOME",
                "SOL20260401002,CUST1002,9900,COMPLETED,BIZ",
            ],
            [
                "SOL20260401001,CUST1001,12500,HOME",
                "SOL20260401002,CUST1002,9900,BIZ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["system_tier"] == "BIZ"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 22400
        assert summary["unmatched_count"] == 0


    def test_install_id_match_uses_full_identifier(self):
        """A credit must not match a source row that only shares the leading source row prefix."""
        write_inputs(
            [
                "SOL777770001,CUST2001,3300,COMPLETED,HOME",
                "SOL777770002,CUST2001,3300,COMPLETED,HOME",
            ],
            [
                "SOL777770003,CUST2001,3300,HOME",
                "SOL777770002,CUST2001,3300,HOME",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["system_tier"] == ""
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300


    def test_customer_amount_status_and_system_tier_all_gate_matching(self):
        """Customer, amount, completed status, and allowed system_tier must all be satisfied."""
        write_inputs(
            [
                "SOL3001,CUST3001,1000,COMPLETED,HOME",
                "SOL3002,CUST3002,2000,COMPLETED,BIZ",
                "SOL3003,CUST3003,3000,DRAFT,IND",
                "SOL3004,CUST3004,4000,COMPLETED,CHECK",
                "SOL3005,CUST3005,5000,COMPLETED,IND",
            ],
            [
                "SOL3001,CUST9999,1000,HOME",
                "SOL3002,CUST3002,2100,BIZ",
                "SOL3003,CUST3003,3000,IND",
                "SOL3004,CUST3004,4000,CHECK",
                "SOL3005,CUST3005,5000,IND",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["system_tier"] == "IND"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_count"] == 4
        assert summary["unmatched_amount_cents"] == 10100


    def test_duplicate_rebates_do_not_reuse_consumed_record(self):
        """Only the earliest eligible rebate may consume a matching source row."""
        write_inputs(
            [
                "SOL5551,CUST5551,7500,COMPLETED,BIZ",
                "SOL5552,CUST5552,8800,COMPLETED,HOME",
            ],
            [
                "SOL5551,CUST5551,7500,BIZ",
                "SOL5551,CUST5551,7500,BIZ",
                "SOL5552,CUST5552,8800,HOME",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["system_tier"] == ""
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 16300
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 7500


    def test_matching_trims_fields_and_normalizes_system_tier_status_case(self):
        """Matching should tolerate surrounding spaces and case differences in system_tier/status values."""
        write_inputs(
            [
                " SOL6601 , CUST6601 , 6100 , completed , home ",
                "SOL6602,CUST6602,7200,COMPLETED,ind",
            ],
            [
                "SOL6601,CUST6601, 6100 ,HOME",
                " SOL6602 , CUST6602 ,7200, IND ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["install_id"] for row in rows] == ["SOL6601", "SOL6602"]
        assert [row["site_id"] for row in rows] == ["CUST6601", "CUST6602"]
        assert [row["system_tier"] for row in rows] == ["HOME", "IND"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 13300


    def test_legacy_system_tier_aliases_match_and_emit_canonical_system_tiers(self):
        """Legacy HO, BZ, and IN credit system_tiers should match and report canonical system_tiers."""
        write_inputs(
            [
                "SOL7701,CUST7701,8800,COMPLETED,BIZ",
                "SOL7702,CUST7702,9100,completed,ind",
                "SOL7703,CUST7703,4200,COMPLETED,HOME",
                "SOL7704,CUST7704,3300,COMPLETED,CHECK",
            ],
            [
                "SOL7701,CUST7701,8800,bz",
                "SOL7702,CUST7702,9100,IN",
                "SOL7703,CUST7703,4200,HO",
                "SOL7704,CUST7704,3300,chk",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["system_tier"] for row in rows] == ["BIZ", "IND", "HOME", ""]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 22100
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 3300


    def test_report_schema_and_rebate_input_order_are_stable(self):
        """The report should use the required schema and preserve rebate input order."""
        write_inputs(
            [
                "SOL9001,CUST9001,100,COMPLETED,HOME",
                "SOL9002,CUST9002,200,COMPLETED,BIZ",
                "SOL9003,CUST9003,300,COMPLETED,IND",
            ],
            [
                "SOL9003,CUST9003,300,IND",
                "SOL9001,CUST9001,100,HOME",
                "SOL9002,CUST9002,200,BIZ",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "install_id,site_id,system_tier,amount_cents,status"
        assert [row["install_id"] for row in rows] == ["SOL9003", "SOL9001", "SOL9002"]
        assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
