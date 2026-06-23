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




class TestMilestone2:
    """Verify milestone 2 preserves base matching while adding BS/PL/PR alias normalization, canonical output, cross-tier rejection, and one-time row consumption."""

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


    def test_legacy_plan_tier_aliases_match_and_emit_canonical_plan_tiers(self):
        """Legacy BS, PL, and PR credit plan_tiers should match and report canonical plan_tiers."""
        write_inputs(
            [
                "WSH7701,CUST7701,8800,COMPLETED,PLUS",
                "WSH7702,CUST7702,9100,completed,pro",
                "WSH7703,CUST7703,4200,COMPLETED,BASIC",
                "WSH7704,CUST7704,3300,COMPLETED,CHECK",
            ],
            [
                "WSH7701,CUST7701,8800,pl",
                "WSH7702,CUST7702,9100,PR",
                "WSH7703,CUST7703,4200,BS",
                "WSH7704,CUST7704,3300,chk",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["plan_tier"] for row in rows] == ["PLUS", "PRO", "BASIC", ""]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 22100
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 3300


    def test_matched_report_uses_credit_plan_tier_not_wash_raw_tier(self):
        """Matched rows should report the rebate row's canonical plan_tier, not the wash row's raw casing."""
        write_inputs(
            [
                "WSH6751,CUST6751,8100,COMPLETED,basic",
                "WSH6752,CUST6752,8200,COMPLETED,plus",
                "WSH6753,CUST6753,8300,COMPLETED,pro",
            ],
            [
                "WSH6751,CUST6751,8100,BASIC",
                "WSH6752,CUST6752,8200,PL",
                "WSH6753,CUST6753,8300,PR",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["plan_tier"] for row in rows] == ["BASIC", "PLUS", "PRO"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 24600


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

    def test_alias_must_match_equivalent_canonical_tier_not_any_allowed_tier(self):
        """A legacy alias is not a wildcard and must equal the wash tier after normalization."""
        write_inputs(
            [
                "WSHALIAS1,CUSTAL1,7100,COMPLETED,BASIC",
                "WSHALIAS2,CUSTAL2,7200,COMPLETED,PRO",
            ],
            [
                "WSHALIAS1,CUSTAL1,7100,PL",
                "WSHALIAS2,CUSTAL2,7200,BS",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert [row["plan_tier"] for row in rows] == ["", ""]
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 14300

    def test_mixed_canonical_and_alias_credits_share_consumption_correctly(self):
        """Canonical and alias rebates in one batch should consume distinct physical rows only once."""
        write_inputs(
            [
                "WSHMIX01,CUSTMIX,1500,COMPLETED,PLUS",
                "WSHMIX01,CUSTMIX,1500,COMPLETED,PLUS",
                "WSHMIX02,CUSTMIX,2000,COMPLETED,BASIC",
            ],
            [
                "WSHMIX01,CUSTMIX,1500,PL",
                "WSHMIX01,CUSTMIX,1500,PLUS",
                "WSHMIX01,CUSTMIX,1500,pl",
                "WSHMIX02,CUSTMIX,2000,BS",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["plan_tier"] for row in rows] == ["PLUS", "PLUS", "", "BASIC"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_amount_cents"] == 1500

