"""Verifier tests for the subscription refund reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "subscriptions.csv"
PAYMENTS = APP / "data" / "refunds.csv"
REPORT = APP / "out" / "refund_report.csv"
SUMMARY = APP / "out" / "refund_summary.json"
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


def write_inputs(bill_rows, refund_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    INVOICES.write_text("subscription_id,subscriber_id,amount_cents,status,plan\n" + "\n".join(bill_rows) + "\n")
    PAYMENTS.write_text("subscription_id,subscriber_id,amount_cents,plan\n" + "\n".join(refund_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_family_refund_matches_and_counts_positive_amount():
    """FAMILY refunds should match active subscriptions and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,ACTIVE,BASIC",
            "INV20260401002,CUST1002,9900,ACTIVE,FAMILY",
        ],
        [
            "INV20260401001,CUST1001,12500,BASIC",
            "INV20260401002,CUST1002,9900,FAMILY",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["plan"] == "FAMILY"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_subscription_id_match_uses_full_identifier():
    """A refund must not match a subscription that only shares the leading subscription prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,ACTIVE,BASIC",
            "INV777770002,CUST2001,3300,ACTIVE,BASIC",
        ],
        [
            "INV777770003,CUST2001,3300,BASIC",
            "INV777770002,CUST2001,3300,BASIC",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["plan"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_plan_all_gate_matching():
    """Customer, amount, active status, and allowed plan must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,1000,ACTIVE,BASIC",
            "INV3002,CUST3002,2000,ACTIVE,FAMILY",
            "INV3003,CUST3003,3000,DRAFT,PREMIUM",
            "INV3004,CUST3004,4000,ACTIVE,CHECK",
            "INV3005,CUST3005,5000,ACTIVE,PREMIUM",
        ],
        [
            "INV3001,CUST9999,1000,BASIC",
            "INV3002,CUST3002,2100,FAMILY",
            "INV3003,CUST3003,3000,PREMIUM",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,PREMIUM",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["plan"] == "PREMIUM"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_refunds_do_not_reuse_consumed_bill():
    """Only the earliest eligible refund may consume a matching subscription."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,ACTIVE,FAMILY",
            "INV5552,CUST5552,8800,ACTIVE,BASIC",
        ],
        [
            "INV5551,CUST5551,7500,FAMILY",
            "INV5551,CUST5551,7500,FAMILY",
            "INV5552,CUST5552,8800,BASIC",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["plan"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_plan_status_case():
    """Matching should tolerate surrounding spaces and case differences in plan/status values."""
    write_inputs(
        [
            " INV6601 , CUST6601 , 6100 , active , family ",
            "INV6602,CUST6602,7200,ACTIVE,premium",
        ],
        [
            "INV6601,CUST6601, 6100 ,FAMILY",
            " INV6602 , CUST6602 ,7200, PREMIUM ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["subscription_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["subscriber_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["plan"] for row in rows] == ["FAMILY", "PREMIUM"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_legacy_plan_aliases_match_and_emit_canonical_plans():
    """Legacy BSC, FAM, and PRM refund plans should match and report canonical plans."""
    write_inputs(
        [
            "INV7701,CUST7701,8800,ACTIVE,FAMILY",
            "INV7702,CUST7702,9100,active,premium",
            "INV7703,CUST7703,4200,ACTIVE,BASIC",
            "INV7704,CUST7704,3300,ACTIVE,CHECK",
        ],
        [
            "INV7701,CUST7701,8800,fam",
            "INV7702,CUST7702,9100,PRM",
            "INV7703,CUST7703,4200,BSC",
            "INV7704,CUST7704,3300,chk",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["plan"] for row in rows] == ["FAMILY", "PREMIUM", "BASIC", ""]
    assert summary["matched_count"] == 3
    assert summary["matched_amount_cents"] == 22100
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 3300


def test_report_schema_and_refund_input_order_are_stable():
    """The report should use the required schema and preserve refund input order."""
    write_inputs(
        [
            "INV9001,CUST9001,100,ACTIVE,BASIC",
            "INV9002,CUST9002,200,ACTIVE,FAMILY",
            "INV9003,CUST9003,300,ACTIVE,PREMIUM",
        ],
        [
            "INV9003,CUST9003,300,PREMIUM",
            "INV9001,CUST9001,100,BASIC",
            "INV9002,CUST9002,200,FAMILY",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "subscription_id,subscriber_id,plan,amount_cents,status"
    assert [row["subscription_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
