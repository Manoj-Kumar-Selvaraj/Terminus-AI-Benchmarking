"""Verifier tests for the rebate reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "washes.csv"
PAYMENTS = APP / "data" / "rebates.csv"
REPORT = APP / "out" / "wash_rebate_report.csv"
SUMMARY = APP / "out" / "wash_rebate_summary.json"
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
    INVOICES.write_text("wash_id,customer_id,amount_cents,status,plan_tier\n" + "\n".join(bill_rows) + "\n")
    PAYMENTS.write_text("wash_id,customer_id,amount_cents,plan_tier\n" + "\n".join(credit_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())




class TestMilestone1:
    """Verify full wash_id and customer matching, positive rebate totals, whitespace trimming, case-insensitive status/tier handling, report schema, and single-consumption semantics."""

    def test_month_credit_matches_and_counts_positive_amount(self):
        """PLUS credits should match completed trips and add positive cents to matched totals."""
        write_inputs(
            [
                "WSH20260401001,CUST1001,12500,COMPLETED,BASIC",
                "WSH20260401002,CUST1002,9900,COMPLETED,PLUS",
            ],
            [
                "WSH20260401001,CUST1001,12500,BASIC",
                "WSH20260401002,CUST1002,9900,PLUS",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["plan_tier"] == "PLUS"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 22400
        assert summary["unmatched_count"] == 0


    def test_wash_id_match_uses_full_identifier(self):
        """A credit must not match a trip that only shares the leading trip prefix."""
        write_inputs(
            [
                "WSH777770001,CUST2001,3300,COMPLETED,BASIC",
                "WSH777770002,CUST2001,3300,COMPLETED,BASIC",
            ],
            [
                "WSH777770003,CUST2001,3300,BASIC",
                "WSH777770002,CUST2001,3300,BASIC",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["plan_tier"] == ""
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300


    def test_customer_amount_status_and_plan_tier_all_gate_matching(self):
        """Customer, amount, completed status, and allowed plan_tier must all be satisfied."""
        write_inputs(
            [
                "WSH3001,CUST3001,1000,COMPLETED,BASIC",
                "WSH3002,CUST3002,2000,COMPLETED,PLUS",
                "WSH3003,CUST3003,3000,DRAFT,PRO",
                "WSH3004,CUST3004,4000,COMPLETED,CHECK",
                "WSH3005,CUST3005,5000,COMPLETED,PRO",
            ],
            [
                "WSH3001,CUST9999,1000,BASIC",
                "WSH3002,CUST3002,2100,PLUS",
                "WSH3003,CUST3003,3000,PRO",
                "WSH3004,CUST3004,4000,CHECK",
                "WSH3005,CUST3005,5000,PRO",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["plan_tier"] == "PRO"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_count"] == 4
        assert summary["unmatched_amount_cents"] == 10100


    def test_duplicate_credits_do_not_reuse_consumed_record(self):
        """Only the earliest eligible credit may consume a matching trip."""
        write_inputs(
            [
                "WSH5551,CUST5551,7500,COMPLETED,PLUS",
                "WSH5552,CUST5552,8800,COMPLETED,BASIC",
            ],
            [
                "WSH5551,CUST5551,7500,PLUS",
                "WSH5551,CUST5551,7500,PLUS",
                "WSH5552,CUST5552,8800,BASIC",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["plan_tier"] == ""
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 16300
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 7500


    def test_matching_trims_fields_and_normalizes_plan_tier_status_case(self):
        """Matching should tolerate surrounding spaces and case differences in plan_tier/status values."""
        write_inputs(
            [
                " WSH6601 , CUST6601 , 6100 , completed , basic ",
                "WSH6602,CUST6602,7200,COMPLETED,pro",
            ],
            [
                "WSH6601,CUST6601, 6100 ,BASIC",
                " WSH6602 , CUST6602 ,7200, PRO ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["wash_id"] for row in rows] == ["WSH6601", "WSH6602"]
        assert [row["customer_id"] for row in rows] == ["CUST6601", "CUST6602"]
        assert [row["plan_tier"] for row in rows] == ["BASIC", "PRO"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 13300


    def test_matched_report_uses_credit_plan_tier_not_wash_raw_tier(self):
        """Matched rows should report the rebate row's canonical plan_tier, not the wash row's raw casing."""
        write_inputs(
            [
                "WSH6751,CUST6751,8100,COMPLETED,basic",
                "WSH6752,CUST6752,8200,COMPLETED,plus",
            ],
            [
                "WSH6751,CUST6751,8100,BASIC",
                "WSH6752,CUST6752,8200,PLUS",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["plan_tier"] for row in rows] == ["BASIC", "PLUS"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 16300


    def test_report_schema_and_credit_input_order_are_stable(self):
        """The report should use the required schema and preserve credit input order."""
        write_inputs(
            [
                "WSH9001,CUST9001,100,COMPLETED,BASIC",
                "WSH9002,CUST9002,200,COMPLETED,PLUS",
                "WSH9003,CUST9003,300,COMPLETED,PRO",
            ],
            [
                "WSH9003,CUST9003,300,PRO",
                "WSH9001,CUST9001,100,BASIC",
                "WSH9002,CUST9002,200,PLUS",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "wash_id,customer_id,plan_tier,amount_cents,status"
        assert [row["wash_id"] for row in rows] == ["WSH9003", "WSH9001", "WSH9002"]
        assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_customer_id_match_uses_full_identifier(self):
        """A rebate must not match a customer id that only shares a prefix."""
        write_inputs(
            [
                "WSHCUST01,CUST7777A,4500,COMPLETED,BASIC",
                "WSHCUST02,CUST7777,4500,COMPLETED,BASIC",
            ],
            [
                "WSHCUST01,CUST7777,4500,BASIC",
                "WSHCUST02,CUST7777,4500,BASIC",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["plan_tier"] == ""
        assert summary["matched_amount_cents"] == 4500
        assert summary["unmatched_amount_cents"] == 4500

    def test_unsupported_rebate_tier_stays_unmatched_even_when_wash_is_allowed(self):
        """An unsupported rebate tier must not match an otherwise eligible wash."""
        write_inputs(
            ["WSHUNSUP1,CUSTUS1,3100,COMPLETED,BASIC"],
            ["WSHUNSUP1,CUSTUS1,3100,VIP"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["plan_tier"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 3100,
        }

