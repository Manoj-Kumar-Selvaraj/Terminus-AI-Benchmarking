"""Verifier tests for the fill reversal reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "fills.csv"
PAYMENTS = APP / "data" / "reversals.csv"
REPORT = APP / "out" / "reversal_report.csv"
SUMMARY = APP / "out" / "reversal_summary.json"
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


def write_inputs(fill_rows, reversal_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    INVOICES.write_text("fill_id,member_id,amount_cents,status,reason\n" + "\n".join(fill_rows) + "\n")
    PAYMENTS.write_text("fill_id,member_id,amount_cents,reason\n" + "\n".join(reversal_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())



class TestMilestone1:
    """Milestone 1 verifier scenarios for pharmacy fill reversals."""

    def test_copay_reversal_matches_and_counts_positive_amount(self):
        """COPAY reversals should match posted fills and add positive cents to matched totals."""
        write_inputs(
            [
                "INV20260401001,CUST1001,12500,POSTED,RX",
                "INV20260401002,CUST1002,9900,POSTED,COPAY",
            ],
            [
                "INV20260401001,CUST1001,12500,RX",
                "INV20260401002,CUST1002,9900,COPAY",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["reason"] == "COPAY"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 22400
        assert summary["unmatched_count"] == 0


    def test_fill_id_match_uses_full_identifier(self):
        """A reversal must not match an fill that only shares the leading fill prefix."""
        write_inputs(
            [
                "INV777770001,CUST2001,3300,POSTED,RX",
                "INV777770002,CUST2001,3300,POSTED,RX",
            ],
            [
                "INV777770003,CUST2001,3300,RX",
                "INV777770002,CUST2001,3300,RX",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["reason"] == ""
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300


    def test_member_amount_status_and_reason_all_gate_matching(self):
        """Member, amount, posted status, and allowed reason must all be satisfied."""
        write_inputs(
            [
                "INV3001,CUST3001,1000,POSTED,RX",
                "INV3002,CUST3002,2000,POSTED,COPAY",
                "INV3003,CUST3003,3000,DRAFT,COB",
                "INV3004,CUST3004,4000,POSTED,CHECK",
                "INV3005,CUST3005,5000,POSTED,COB",
            ],
            [
                "INV3001,CUST9999,1000,RX",
                "INV3002,CUST3002,2100,COPAY",
                "INV3003,CUST3003,3000,COB",
                "INV3004,CUST3004,4000,CHECK",
                "INV3005,CUST3005,5000,COB",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["reason"] == "COB"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_count"] == 4
        assert summary["unmatched_amount_cents"] == 10100


    def test_duplicate_reversals_do_not_reuse_consumed_fill(self):
        """Only the earliest eligible reversal may consume a matching fill."""
        write_inputs(
            [
                "INV5551,CUST5551,7500,POSTED,COPAY",
                "INV5552,CUST5552,8800,POSTED,RX",
            ],
            [
                "INV5551,CUST5551,7500,COPAY",
                "INV5551,CUST5551,7500,COPAY",
                "INV5552,CUST5552,8800,RX",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["reason"] == ""
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 16300
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 7500


    def test_matching_trims_fields_and_normalizes_reason_status_case(self):
        """Matching should tolerate surrounding spaces and case differences in reason/status values."""
        write_inputs(
            [
                " INV6601 , CUST6601 , 6100 , posted , copay ",
                "INV6602,CUST6602,7200,POSTED,cob",
            ],
            [
                "INV6601,CUST6601, 6100 ,COPAY",
                " INV6602 , CUST6602 ,7200, COB ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["fill_id"] for row in rows] == ["INV6601", "INV6602"]
        assert [row["member_id"] for row in rows] == ["CUST6601", "CUST6602"]
        assert [row["reason"] for row in rows] == ["COPAY", "COB"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 13300


    def test_report_schema_and_reversal_input_order_are_stable(self):
        """The report should use the required schema and preserve reversal input order."""
        write_inputs(
            [
                "INV9001,CUST9001,100,POSTED,RX",
                "INV9002,CUST9002,200,POSTED,COPAY",
                "INV9003,CUST9003,300,POSTED,COB",
            ],
            [
                "INV9003,CUST9003,300,COB",
                "INV9001,CUST9001,100,RX",
                "INV9002,CUST9002,200,COPAY",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "fill_id,member_id,reason,amount_cents,status"
        assert [row["fill_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
        assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
