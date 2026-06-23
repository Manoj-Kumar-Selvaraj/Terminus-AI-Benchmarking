"""Verifier tests for the credit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
SOURCE_FILE = APP / "data" / "prints.csv"
ACTION_FILE = APP / "data" / "print_credits.csv"
REPORT = APP / "out" / "print_credit_report.csv"
SUMMARY = APP / "out" / "print_credit_summary.json"
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
    SOURCE_FILE.write_text("print_id,guest_id,amount_cents,status,pack_tier\n" + "\n".join(bill_rows) + "\n")
    ACTION_FILE.write_text("print_id,guest_id,amount_cents,pack_tier\n" + "\n".join(credit_rows) + "\n")
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
        """STANDARD credits should match completed source rows and add positive cents to matched totals."""
        write_inputs(
            [
                "PHT20260401001,CUST1001,12500,COMPLETED,MINI",
                "PHT20260401002,CUST1002,9900,COMPLETED,STANDARD",
            ],
            [
                "PHT20260401001,CUST1001,12500,MINI",
                "PHT20260401002,CUST1002,9900,STANDARD",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["pack_tier"] == "STANDARD"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 22400
        assert summary["unmatched_count"] == 0


    def test_print_id_match_uses_full_identifier(self):
        """A credit must not match a source row that only shares the leading source row prefix."""
        write_inputs(
            [
                "PHT777770001,CUST2001,3300,COMPLETED,MINI",
                "PHT777770002,CUST2001,3300,COMPLETED,MINI",
            ],
            [
                "PHT777770003,CUST2001,3300,MINI",
                "PHT777770002,CUST2001,3300,MINI",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["pack_tier"] == ""
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300


    def test_customer_amount_status_and_pack_tier_all_gate_matching(self):
        """Customer, amount, completed status, and allowed pack_tier must all be satisfied."""
        write_inputs(
            [
                "PHT3001,CUST3001,1000,COMPLETED,MINI",
                "PHT3002,CUST3002,2000,COMPLETED,STANDARD",
                "PHT3003,CUST3003,3000,DRAFT,MAX",
                "PHT3004,CUST3004,4000,COMPLETED,CHECK",
                "PHT3005,CUST3005,5000,COMPLETED,MAX",
            ],
            [
                "PHT3001,CUST9999,1000,MINI",
                "PHT3002,CUST3002,2100,STANDARD",
                "PHT3003,CUST3003,3000,MAX",
                "PHT3004,CUST3004,4000,CHECK",
                "PHT3005,CUST3005,5000,MAX",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["pack_tier"] == "MAX"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_count"] == 4
        assert summary["unmatched_amount_cents"] == 10100


    def test_duplicate_credits_do_not_reuse_consumed_record(self):
        """Only the earliest eligible credit may consume a matching source row."""
        write_inputs(
            [
                "PHT5551,CUST5551,7500,COMPLETED,STANDARD",
                "PHT5552,CUST5552,8800,COMPLETED,MINI",
            ],
            [
                "PHT5551,CUST5551,7500,STANDARD",
                "PHT5551,CUST5551,7500,STANDARD",
                "PHT5552,CUST5552,8800,MINI",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["pack_tier"] == ""
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 16300
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 7500


    def test_matching_trims_fields_and_normalizes_pack_tier_status_case(self):
        """Matching should tolerate surrounding spaces and case differences in pack_tier/status values."""
        write_inputs(
            [
                " PHT6601 , CUST6601 , 6100 , completed , mini ",
                "PHT6602,CUST6602,7200,COMPLETED,standard",
            ],
            [
                "PHT6601,CUST6601, 6100 ,MINI",
                " PHT6602 , CUST6602 ,7200, STANDARD ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["print_id"] for row in rows] == ["PHT6601", "PHT6602"]
        assert [row["guest_id"] for row in rows] == ["CUST6601", "CUST6602"]
        assert [row["pack_tier"] for row in rows] == ["MINI", "STANDARD"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 13300


    def test_legacy_pack_tier_aliases_match_and_emit_canonical_pack_tiers(self):
        """Legacy MI, SD, and MX credit pack_tiers should match and report canonical pack_tiers."""
        write_inputs(
            [
                "PHT7701,CUST7701,8800,COMPLETED,STANDARD",
                "PHT7702,CUST7702,9100,completed,max",
                "PHT7703,CUST7703,4200,COMPLETED,MINI",
                "PHT7704,CUST7704,3300,COMPLETED,CHECK",
            ],
            [
                "PHT7701,CUST7701,8800,sd",
                "PHT7702,CUST7702,9100,MX",
                "PHT7703,CUST7703,4200,MI",
                "PHT7704,CUST7704,3300,chk",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["pack_tier"] for row in rows] == ["STANDARD", "MAX", "MINI", ""]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 22100
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 3300


    def test_report_schema_and_credit_input_order_are_stable(self):
        """The report should use the required schema and preserve credit input order."""
        write_inputs(
            [
                "PHT9001,CUST9001,100,COMPLETED,MINI",
                "PHT9002,CUST9002,200,COMPLETED,STANDARD",
                "PHT9003,CUST9003,300,COMPLETED,MAX",
            ],
            [
                "PHT9003,CUST9003,300,MAX",
                "PHT9001,CUST9001,100,MINI",
                "PHT9002,CUST9002,200,STANDARD",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "print_id,guest_id,pack_tier,amount_cents,status"
        assert [row["print_id"] for row in rows] == ["PHT9003", "PHT9001", "PHT9002"]
        assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
