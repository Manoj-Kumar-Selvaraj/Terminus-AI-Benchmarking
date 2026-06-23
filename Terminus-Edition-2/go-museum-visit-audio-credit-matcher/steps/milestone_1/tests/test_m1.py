"""Verifier tests for the credit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
SOURCE_FILE = APP / "data" / "visits.csv"
ACTION_FILE = APP / "data" / "audio_credits.csv"
REPORT = APP / "out" / "museum_credit_report.csv"
SUMMARY = APP / "out" / "museum_credit_summary.json"
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
    SOURCE_FILE.write_text("visit_id,patron_id,amount_cents,status,gallery_tier\n" + "\n".join(bill_rows) + "\n")
    ACTION_FILE.write_text("visit_id,patron_id,amount_cents,gallery_tier\n" + "\n".join(credit_rows) + "\n")
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
        """SPECIAL credits should match completed source rows and add positive cents to matched totals."""
        write_inputs(
            [
                "MUS20260401001,CUST1001,12500,COMPLETED,GENERAL",
                "MUS20260401002,CUST1002,9900,COMPLETED,SPECIAL",
            ],
            [
                "MUS20260401001,CUST1001,12500,GENERAL",
                "MUS20260401002,CUST1002,9900,SPECIAL",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["gallery_tier"] == "SPECIAL"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 22400
        assert summary["unmatched_count"] == 0


    def test_visit_id_match_uses_full_identifier(self):
        """A credit must not match a source row that only shares the leading source row prefix."""
        write_inputs(
            [
                "MUS777770001,CUST2001,3300,COMPLETED,GENERAL",
                "MUS777770002,CUST2001,3300,COMPLETED,GENERAL",
            ],
            [
                "MUS777770003,CUST2001,3300,GENERAL",
                "MUS777770002,CUST2001,3300,GENERAL",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["gallery_tier"] == ""
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300


    def test_customer_amount_status_and_gallery_tier_all_gate_matching(self):
        """Customer, amount, completed status, and allowed gallery_tier must all be satisfied."""
        write_inputs(
            [
                "MUS3001,CUST3001,1000,COMPLETED,GENERAL",
                "MUS3002,CUST3002,2000,COMPLETED,SPECIAL",
                "MUS3003,CUST3003,3000,DRAFT,MEMBER",
                "MUS3004,CUST3004,4000,COMPLETED,CHECK",
                "MUS3005,CUST3005,5000,COMPLETED,MEMBER",
            ],
            [
                "MUS3001,CUST9999,1000,GENERAL",
                "MUS3002,CUST3002,2100,SPECIAL",
                "MUS3003,CUST3003,3000,MEMBER",
                "MUS3004,CUST3004,4000,CHECK",
                "MUS3005,CUST3005,5000,MEMBER",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["gallery_tier"] == "MEMBER"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_count"] == 4
        assert summary["unmatched_amount_cents"] == 10100


    def test_duplicate_credits_do_not_reuse_consumed_record(self):
        """Only the earliest eligible credit may consume a matching source row."""
        write_inputs(
            [
                "MUS5551,CUST5551,7500,COMPLETED,SPECIAL",
                "MUS5552,CUST5552,8800,COMPLETED,GENERAL",
            ],
            [
                "MUS5551,CUST5551,7500,SPECIAL",
                "MUS5551,CUST5551,7500,SPECIAL",
                "MUS5552,CUST5552,8800,GENERAL",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["gallery_tier"] == ""
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 16300
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 7500


    def test_matching_trims_fields_and_normalizes_gallery_tier_status_case(self):
        """Matching should tolerate surrounding spaces and case differences in gallery_tier/status values."""
        write_inputs(
            [
                " MUS6601 , CUST6601 , 6100 , completed , general ",
                "MUS6602,CUST6602,7200,COMPLETED,special",
            ],
            [
                "MUS6601,CUST6601, 6100 ,GENERAL",
                " MUS6602 , CUST6602 ,7200, SPECIAL ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["visit_id"] for row in rows] == ["MUS6601", "MUS6602"]
        assert [row["patron_id"] for row in rows] == ["CUST6601", "CUST6602"]
        assert [row["gallery_tier"] for row in rows] == ["GENERAL", "SPECIAL"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 13300


    def test_report_schema_and_credit_input_order_are_stable(self):
        """The report should use the required schema and preserve credit input order."""
        write_inputs(
            [
                "MUS9001,CUST9001,100,COMPLETED,GENERAL",
                "MUS9002,CUST9002,200,COMPLETED,SPECIAL",
                "MUS9003,CUST9003,300,COMPLETED,MEMBER",
            ],
            [
                "MUS9003,CUST9003,300,MEMBER",
                "MUS9001,CUST9001,100,GENERAL",
                "MUS9002,CUST9002,200,SPECIAL",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "visit_id,patron_id,gallery_tier,amount_cents,status"
        assert [row["visit_id"] for row in rows] == ["MUS9003", "MUS9001", "MUS9002"]
        assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_unmatched_report_trims_identifier_fields(self):
        """Unmatched report rows must trim visit_id and patron_id output fields."""
        write_inputs(
            [" MUS7701 , CUST7701 , 500 , COMPLETED , GENERAL "],
            [" MUS7701 , CUST7701 , 600 , GENERAL "],
        )
        rows, _ = run_program()
        assert len(rows) == 1
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["visit_id"] == "MUS7701"
        assert rows[0]["patron_id"] == "CUST7701"
        assert rows[0]["gallery_tier"] == ""
