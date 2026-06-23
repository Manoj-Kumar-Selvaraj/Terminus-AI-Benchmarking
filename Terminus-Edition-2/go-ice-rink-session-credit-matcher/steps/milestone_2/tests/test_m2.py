"""Verifier tests for the credit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
SOURCE_FILE = APP / "data" / "sessions.csv"
ACTION_FILE = APP / "data" / "session_credits.csv"
REPORT = APP / "out" / "rink_credit_report.csv"
SUMMARY = APP / "out" / "rink_credit_summary.json"
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
    SOURCE_FILE.write_text("session_id,skater_id,amount_cents,status,rink_pass\n" + "\n".join(bill_rows) + "\n")
    ACTION_FILE.write_text("session_id,skater_id,amount_cents,rink_pass\n" + "\n".join(credit_rows) + "\n")
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

    def test_credit_matches_and_counts_positive_amount(self):
        """GAME credits should match completed source rows and add positive cents to matched totals."""
        write_inputs(
            [
                "ICE20260401001,CUST1001,12500,COMPLETED,PRAC",
                "ICE20260401002,CUST1002,9900,COMPLETED,GAME",
            ],
            [
                "ICE20260401001,CUST1001,12500,PRAC",
                "ICE20260401002,CUST1002,9900,GAME",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["rink_pass"] == "GAME"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 22400
        assert summary["unmatched_count"] == 0


    def test_session_id_match_uses_full_identifier(self):
        """A credit must not match a source row that only shares the leading source row prefix."""
        write_inputs(
            [
                "ICE777770001,CUST2001,3300,COMPLETED,PRAC",
                "ICE777770002,CUST2001,3300,COMPLETED,PRAC",
            ],
            [
                "ICE777770003,CUST2001,3300,PRAC",
                "ICE777770002,CUST2001,3300,PRAC",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["rink_pass"] == ""
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300


    def test_customer_amount_status_and_rink_pass_all_gate_matching(self):
        """Customer, amount, completed status, and allowed rink_pass must all be satisfied."""
        write_inputs(
            [
                "ICE3001,CUST3001,1000,COMPLETED,PRAC",
                "ICE3002,CUST3002,2000,COMPLETED,GAME",
                "ICE3003,CUST3003,3000,DRAFT,LEAG",
                "ICE3004,CUST3004,4000,COMPLETED,CHECK",
                "ICE3005,CUST3005,5000,COMPLETED,LEAG",
            ],
            [
                "ICE3001,CUST9999,1000,PRAC",
                "ICE3002,CUST3002,2100,GAME",
                "ICE3003,CUST3003,3000,LEAG",
                "ICE3004,CUST3004,4000,CHECK",
                "ICE3005,CUST3005,5000,LG",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["rink_pass"] == "LEAG"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_count"] == 4
        assert summary["unmatched_amount_cents"] == 10100


    def test_duplicate_credits_do_not_reuse_consumed_record(self):
        """Only the earliest eligible credit may consume a matching source row."""
        write_inputs(
            [
                "ICE5551,CUST5551,7500,COMPLETED,GAME",
                "ICE5552,CUST5552,8800,COMPLETED,PRAC",
            ],
            [
                "ICE5551,CUST5551,7500,GAME",
                "ICE5551,CUST5551,7500,GAME",
                "ICE5552,CUST5552,8800,PRAC",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["rink_pass"] == ""
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 16300
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 7500


    def test_matching_trims_fields_and_normalizes_rink_pass_status_case(self):
        """Matching should tolerate surrounding spaces and case differences in rink_pass/status values."""
        write_inputs(
            [
                " ICE6601 , CUST6601 , 6100 , completed , prac ",
                "ICE6602,CUST6602,7200,COMPLETED,game",
            ],
            [
                "ICE6601,CUST6601, 6100 ,PRAC",
                " ICE6602 , CUST6602 ,7200, GAME ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["session_id"] for row in rows] == ["ICE6601", "ICE6602"]
        assert [row["skater_id"] for row in rows] == ["CUST6601", "CUST6602"]
        assert [row["rink_pass"] for row in rows] == ["PRAC", "GAME"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 13300


    def test_legacy_rink_pass_aliases_match_and_emit_canonical_rink_passs(self):
        """Legacy PR, GM, and LG credit rink_passs should match and report canonical rink_passs."""
        write_inputs(
            [
                "ICE7701,CUST7701,8800,COMPLETED,GAME",
                "ICE7702,CUST7702,9100,completed,leag",
                "ICE7703,CUST7703,4200,COMPLETED,PRAC",
                "ICE7704,CUST7704,3300,COMPLETED,CHECK",
            ],
            [
                "ICE7701,CUST7701,8800,gm",
                "ICE7702,CUST7702,9100,LG",
                "ICE7703,CUST7703,4200,PR",
                "ICE7704,CUST7704,3300,chk",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["rink_pass"] for row in rows] == ["GAME", "LEAG", "PRAC", ""]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 22100
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 3300


    def test_report_schema_and_credit_input_order_are_stable(self):
        """The report should use the required schema and preserve credit input order."""
        write_inputs(
            [
                "ICE9001,CUST9001,100,COMPLETED,PRAC",
                "ICE9002,CUST9002,200,COMPLETED,GAME",
                "ICE9003,CUST9003,300,COMPLETED,LEAG",
            ],
            [
                "ICE9003,CUST9003,300,LEAG",
                "ICE9001,CUST9001,100,PRAC",
                "ICE9002,CUST9002,200,GAME",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "session_id,skater_id,rink_pass,amount_cents,status"
        assert [row["session_id"] for row in rows] == ["ICE9003", "ICE9001", "ICE9002"]
        assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
