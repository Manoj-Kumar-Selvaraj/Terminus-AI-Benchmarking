"""Verifier tests for the tasting refund reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
SOURCE_FILE = APP / "data" / "tastings.csv"
ACTION_FILE = APP / "data" / "tasting_refunds.csv"
REPORT = APP / "out" / "winery_refund_report.csv"
SUMMARY = APP / "out" / "winery_refund_summary.json"
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
    SOURCE_FILE.write_text("tasting_id,guest_id,amount_cents,status,flight_tier\n" + "\n".join(bill_rows) + "\n")
    ACTION_FILE.write_text("tasting_id,guest_id,amount_cents,flight_tier\n" + "\n".join(credit_rows) + "\n")
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

    def test_tasting_refund_matches_and_counts_positive_amount(self):
        """WHITE credits should match completed source rows and add positive cents to matched totals."""
        write_inputs(
            [
                "WIN20260401001,CUST1001,12500,COMPLETED,RED",
                "WIN20260401002,CUST1002,9900,COMPLETED,WHITE",
            ],
            [
                "WIN20260401001,CUST1001,12500,RED",
                "WIN20260401002,CUST1002,9900,WHITE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["flight_tier"] == "WHITE"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 22400
        assert summary["unmatched_count"] == 0


    def test_tasting_id_match_uses_full_identifier(self):
        """A credit must not match a source row that only shares the leading source row prefix."""
        write_inputs(
            [
                "WIN777770001,CUST2001,3300,COMPLETED,RED",
                "WIN777770002,CUST2001,3300,COMPLETED,RED",
            ],
            [
                "WIN777770003,CUST2001,3300,RED",
                "WIN777770002,CUST2001,3300,RED",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["flight_tier"] == ""
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300


    def test_customer_amount_status_and_flight_tier_all_gate_matching(self):
        """Customer, amount, completed status, and allowed flight_tier must all be satisfied."""
        write_inputs(
            [
                "WIN3001,CUST3001,1000,COMPLETED,RED",
                "WIN3002,CUST3002,2000,COMPLETED,WHITE",
                "WIN3003,CUST3003,3000,DRAFT,MIXED",
                "WIN3004,CUST3004,4000,COMPLETED,CHECK",
                "WIN3005,CUST3005,5000,COMPLETED,MIXED",
            ],
            [
                "WIN3001,CUST9999,1000,RED",
                "WIN3002,CUST3002,2100,WHITE",
                "WIN3003,CUST3003,3000,MIXED",
                "WIN3004,CUST3004,4000,CHECK",
                "WIN3005,CUST3005,5000,MIXED",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["flight_tier"] == "MIXED"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_count"] == 4
        assert summary["unmatched_amount_cents"] == 10100


    def test_duplicate_tasting_refunds_do_not_reuse_consumed_record(self):
        """Only the earliest eligible tasting refund may consume a matching source row."""
        write_inputs(
            [
                "WIN5551,CUST5551,7500,COMPLETED,WHITE",
                "WIN5552,CUST5552,8800,COMPLETED,RED",
            ],
            [
                "WIN5551,CUST5551,7500,WHITE",
                "WIN5551,CUST5551,7500,WHITE",
                "WIN5552,CUST5552,8800,RED",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["flight_tier"] == ""
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 16300
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 7500


    def test_matching_trims_fields_and_normalizes_flight_tier_status_case(self):
        """Matching should tolerate surrounding spaces and case differences in flight_tier/status values."""
        write_inputs(
            [
                " WIN6601 , CUST6601 , 6100 , completed , red ",
                "WIN6602,CUST6602,7200,COMPLETED,mixed",
            ],
            [
                "WIN6601,CUST6601, 6100 ,RED",
                " WIN6602 , CUST6602 ,7200, MIXED ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["tasting_id"] for row in rows] == ["WIN6601", "WIN6602"]
        assert [row["guest_id"] for row in rows] == ["CUST6601", "CUST6602"]
        assert [row["flight_tier"] for row in rows] == ["RED", "MIXED"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 13300


    def test_legacy_flight_tier_aliases_match_and_emit_canonical_flight_tiers(self):
        """Legacy RD, WH, and MX credit flight_tiers should match and report canonical flight_tiers."""
        write_inputs(
            [
                "WIN7701,CUST7701,8800,COMPLETED,WHITE",
                "WIN7702,CUST7702,9100,completed,mixed",
                "WIN7703,CUST7703,4200,COMPLETED,RED",
                "WIN7704,CUST7704,3300,COMPLETED,CHECK",
            ],
            [
                "WIN7701,CUST7701,8800,wh",
                "WIN7702,CUST7702,9100,MX",
                "WIN7703,CUST7703,4200,RD",
                "WIN7704,CUST7704,3300,chk",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["flight_tier"] for row in rows] == ["WHITE", "MIXED", "RED", ""]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 22100
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 3300


    def test_report_schema_and_tasting_refund_input_order_are_stable(self):
        """The report should use the required schema and preserve tasting refund input order."""
        write_inputs(
            [
                "WIN9001,CUST9001,100,COMPLETED,RED",
                "WIN9002,CUST9002,200,COMPLETED,WHITE",
                "WIN9003,CUST9003,300,COMPLETED,MIXED",
            ],
            [
                "WIN9003,CUST9003,300,MIXED",
                "WIN9001,CUST9001,100,RED",
                "WIN9002,CUST9002,200,WHITE",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "tasting_id,guest_id,flight_tier,amount_cents,status"
        assert [row["tasting_id"] for row in rows] == ["WIN9003", "WIN9001", "WIN9002"]
        assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
