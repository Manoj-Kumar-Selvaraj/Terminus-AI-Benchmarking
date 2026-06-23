"""Verifier tests for the credit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
SOURCE_FILE = APP / "data" / "scorecards.csv"
ACTION_FILE = APP / "data" / "credits.csv"
REPORT = APP / "out" / "scorecard_credit_report.csv"
SUMMARY = APP / "out" / "scorecard_credit_summary.json"
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
    SOURCE_FILE.write_text("scorecard_id,player_id,amount_cents,status,course_tier\n" + "\n".join(bill_rows) + "\n")
    ACTION_FILE.write_text("scorecard_id,player_id,amount_cents,course_tier\n" + "\n".join(credit_rows) + "\n")
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

    def test_credit_matches_and_counts_positive_amount(self):
        """BACK credits should match completed source rows and add positive cents to matched totals."""
        write_inputs(
            [
                "MGL20260401001,CUST1001,12500,COMPLETED,FRONT",
                "MGL20260401002,CUST1002,9900,COMPLETED,BACK",
            ],
            [
                "MGL20260401001,CUST1001,12500,FRONT",
                "MGL20260401002,CUST1002,9900,BACK",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["course_tier"] == "BACK"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 22400
        assert summary["unmatched_count"] == 0


    def test_scorecard_id_match_uses_full_identifier(self):
        """A credit must not match a source row that only shares the leading source row prefix."""
        write_inputs(
            [
                "MGL777770001,CUST2001,3300,COMPLETED,FRONT",
                "MGL777770002,CUST2001,3300,COMPLETED,FRONT",
            ],
            [
                "MGL777770003,CUST2001,3300,FRONT",
                "MGL777770002,CUST2001,3300,FRONT",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["course_tier"] == ""
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300


    def test_customer_amount_status_and_course_tier_all_gate_matching(self):
        """Customer, amount, completed status, and allowed course_tier must all be satisfied."""
        write_inputs(
            [
                "MGL3001,CUST3001,1000,COMPLETED,FRONT",
                "MGL3002,CUST3002,2000,COMPLETED,BACK",
                "MGL3003,CUST3003,3000,DRAFT,FULL",
                "MGL3004,CUST3004,4000,COMPLETED,CHECK",
                "MGL3005,CUST3005,5000,COMPLETED,FULL",
            ],
            [
                "MGL3001,CUST9999,1000,FRONT",
                "MGL3002,CUST3002,2100,BACK",
                "MGL3003,CUST3003,3000,FULL",
                "MGL3004,CUST3004,4000,CHECK",
                "MGL3005,CUST3005,5000,FULL",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["course_tier"] == "FULL"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_count"] == 4
        assert summary["unmatched_amount_cents"] == 10100


    def test_duplicate_credits_do_not_reuse_consumed_record(self):
        """Only the earliest eligible credit may consume a matching source row."""
        write_inputs(
            [
                "MGL5551,CUST5551,7500,COMPLETED,BACK",
                "MGL5552,CUST5552,8800,COMPLETED,FRONT",
            ],
            [
                "MGL5551,CUST5551,7500,BACK",
                "MGL5551,CUST5551,7500,BACK",
                "MGL5552,CUST5552,8800,FRONT",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["course_tier"] == ""
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 16300
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 7500


    def test_matching_trims_fields_and_normalizes_course_tier_status_case(self):
        """Matching should tolerate surrounding spaces and case differences in course_tier/status values."""
        write_inputs(
            [
                " MGL6601 , CUST6601 , 6100 , completed , front ",
                "MGL6602,CUST6602,7200,COMPLETED,back",
            ],
            [
                "MGL6601,CUST6601, 6100 ,FRONT",
                " MGL6602 , CUST6602 ,7200, BACK ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["scorecard_id"] for row in rows] == ["MGL6601", "MGL6602"]
        assert [row["player_id"] for row in rows] == ["CUST6601", "CUST6602"]
        assert [row["course_tier"] for row in rows] == ["FRONT", "BACK"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 13300


    def test_report_schema_and_credit_input_order_are_stable(self):
        """The report should use the required schema and preserve credit input order."""
        write_inputs(
            [
                "MGL9001,CUST9001,100,COMPLETED,FRONT",
                "MGL9002,CUST9002,200,COMPLETED,BACK",
                "MGL9003,CUST9003,300,COMPLETED,FULL",
            ],
            [
                "MGL9003,CUST9003,300,FULL",
                "MGL9001,CUST9001,100,FRONT",
                "MGL9002,CUST9002,200,BACK",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "scorecard_id,player_id,course_tier,amount_cents,status"
        assert [row["scorecard_id"] for row in rows] == ["MGL9003", "MGL9001", "MGL9002"]
        assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_unmatched_report_trims_identifier_fields(self):
        """Unmatched report rows must trim scorecard_id and player_id output fields."""
        write_inputs(
            [" MGL7701 , CUST7701 , 500 , COMPLETED , FRONT "],
            [" MGL7701 , CUST7701 , 600 , FRONT "],
        )
        rows, _ = run_program()
        assert len(rows) == 1
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["scorecard_id"] == "MGL7701"
        assert rows[0]["player_id"] == "CUST7701"
        assert rows[0]["course_tier"] == ""
