"""Verifier tests for the credit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
SOURCE_FILE = APP / "data" / "laps.csv"
ACTION_FILE = APP / "data" / "credits.csv"
REPORT = APP / "out" / "lap_credit_report.csv"
SUMMARY = APP / "out" / "lap_credit_summary.json"
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
    SOURCE_FILE.write_text("lap_id,swimmer_id,amount_cents,status,lane_tier\n" + "\n".join(bill_rows) + "\n")
    ACTION_FILE.write_text("lap_id,swimmer_id,amount_cents,lane_tier\n" + "\n".join(credit_rows) + "\n")
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
        """MED credits should match completed source rows and add positive cents to matched totals."""
        write_inputs(
            [
                "POL20260401001,CUST1001,12500,COMPLETED,SLOW",
                "POL20260401002,CUST1002,9900,COMPLETED,MED",
            ],
            [
                "POL20260401001,CUST1001,12500,SLOW",
                "POL20260401002,CUST1002,9900,MED",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["lane_tier"] == "MED"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 22400
        assert summary["unmatched_count"] == 0


    def test_lap_id_match_uses_full_identifier(self):
        """A credit must not match a source row that only shares the first eight lap_id characters."""
        write_inputs(
            [
                "POL777770001,CUST2001,3300,COMPLETED,SLOW",
                "POL777770002,CUST2001,3300,COMPLETED,SLOW",
            ],
            [
                "POL777770003,CUST2001,3300,SLOW",
                "POL777770002,CUST2001,3300,SLOW",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["lane_tier"] == ""
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300


    def test_customer_amount_status_and_lane_tier_all_gate_matching(self):
        """Customer, amount, completed status, and allowed lane_tier must all be satisfied."""
        write_inputs(
            [
                "POL3001,CUST3001,1000,COMPLETED,SLOW",
                "POL3002,CUST3002,2000,COMPLETED,MED",
                "POL3003,CUST3003,3000,DRAFT,FAST",
                "POL3004,CUST3004,4000,COMPLETED,CHECK",
                "POL3005,CUST3005,5000,COMPLETED,FAST",
            ],
            [
                "POL3001,CUST9999,1000,SLOW",
                "POL3002,CUST3002,2100,MED",
                "POL3003,CUST3003,3000,FAST",
                "POL3004,CUST3004,4000,CHECK",
                "POL3005,CUST3005,5000,FAST",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["lane_tier"] == "FAST"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_count"] == 4
        assert summary["unmatched_amount_cents"] == 10100


    def test_duplicate_credits_do_not_reuse_consumed_record(self):
        """Only the earliest eligible credit may consume a matching source row."""
        write_inputs(
            [
                "POL5551,CUST5551,7500,COMPLETED,MED",
                "POL5552,CUST5552,8800,COMPLETED,SLOW",
            ],
            [
                "POL5551,CUST5551,7500,MED",
                "POL5551,CUST5551,7500,MED",
                "POL5552,CUST5552,8800,SLOW",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["lane_tier"] == ""
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 16300
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 7500


    def test_matching_trims_fields_and_normalizes_lane_tier_status_case(self):
        """Matching should tolerate surrounding spaces and case differences in lane_tier/status values."""
        write_inputs(
            [
                " POL6601 , CUST6601 , 6100 , completed , slow ",
                "POL6602,CUST6602,7200,COMPLETED,med",
            ],
            [
                "POL6601,CUST6601, 6100 ,SLOW",
                " POL6602 , CUST6602 ,7200, MED ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["lap_id"] for row in rows] == ["POL6601", "POL6602"]
        assert [row["swimmer_id"] for row in rows] == ["CUST6601", "CUST6602"]
        assert [row["lane_tier"] for row in rows] == ["SLOW", "MED"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 13300

    def test_status_and_lane_tier_case_folding_are_match_eligible(self):
        """Lowercase source status and mixed-case lane_tier values should still satisfy the M1 gates."""
        write_inputs(
            [
                "POL6701,CUST6701,6400,completed,slow",
                "POL6702,CUST6702,7300,Completed,FaSt",
            ],
            [
                "POL6701,CUST6701,6400,SLOW",
                "POL6702,CUST6702,7300,fast",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["lane_tier"] for row in rows] == ["SLOW", "FAST"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 13700


    def test_report_schema_and_credit_input_order_are_stable(self):
        """The report should use the required schema and preserve credit input order."""
        write_inputs(
            [
                "POL9001,CUST9001,100,COMPLETED,SLOW",
                "POL9002,CUST9002,200,COMPLETED,MED",
                "POL9003,CUST9003,300,COMPLETED,FAST",
            ],
            [
                "POL9003,CUST9003,300,FAST",
                "POL9001,CUST9001,100,SLOW",
                "POL9002,CUST9002,200,MED",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "lap_id,swimmer_id,lane_tier,amount_cents,status"
        assert [row["lap_id"] for row in rows] == ["POL9003", "POL9001", "POL9002"]
        assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_unmatched_report_trims_identifier_fields(self):
        """Unmatched report rows must trim lap_id and swimmer_id output fields."""
        write_inputs(
            [" POL7701 , CUST7701 , 500 , COMPLETED , SLOW "],
            [" POL7701 , CUST7701 , 600 , SLOW "],
        )
        rows, _ = run_program()
        assert len(rows) == 1
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["lap_id"] == "POL7701"
        assert rows[0]["swimmer_id"] == "CUST7701"
        assert rows[0]["lane_tier"] == ""
