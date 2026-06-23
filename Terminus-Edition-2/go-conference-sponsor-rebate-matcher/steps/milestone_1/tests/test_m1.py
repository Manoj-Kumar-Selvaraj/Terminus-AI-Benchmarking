"""Tests for the sponsorship rebate reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "sponsorships.csv"
PAYMENTS = APP / "data" / "rebates.csv"
REPORT = APP / "out" / "rebate_report.csv"
SUMMARY = APP / "out" / "rebate_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go reconciliation CLI for the current source tree."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all tests."""
    build_program()


def write_inputs(bill_rows, refund_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    INVOICES.write_text("sponsorship_id,sponsor_id,amount_cents,status,level\n" + "\n".join(bill_rows) + "\n")
    PAYMENTS.write_text("sponsorship_id,sponsor_id,amount_cents,level\n" + "\n".join(refund_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_gold_refund_matches_and_counts_positive_amount():
    """GOLD rebates should match signed sponsorships and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,SIGNED,BRONZE",
            "INV20260401002,CUST1002,9900,SIGNED,GOLD",
        ],
        [
            "INV20260401001,CUST1001,12500,BRONZE",
            "INV20260401002,CUST1002,9900,GOLD",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["level"] == "GOLD"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_sponsorship_id_match_uses_full_identifier():
    """A rebate must not match a sponsorship that only shares the leading sponsorship prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,SIGNED,BRONZE",
            "INV777770002,CUST2001,3300,SIGNED,BRONZE",
        ],
        [
            "INV777770003,CUST2001,3300,BRONZE",
            "INV777770002,CUST2001,3300,BRONZE",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["level"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_level_all_gate_matching():
    """Customer, amount, signed status, and allowed level must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,1000,SIGNED,BRONZE",
            "INV3002,CUST3002,2000,SIGNED,GOLD",
            "INV3003,CUST3003,3000,DRAFT,PLATINUM",
            "INV3004,CUST3004,4000,SIGNED,CHECK",
            "INV3005,CUST3005,5000,SIGNED,PLATINUM",
        ],
        [
            "INV3001,CUST9999,1000,BRONZE",
            "INV3002,CUST3002,2100,GOLD",
            "INV3003,CUST3003,3000,PLATINUM",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,PLATINUM",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["level"] == "PLATINUM"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_refunds_do_not_reuse_consumed_bill():
    """Only the earliest eligible rebate may consume a matching sponsorship."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,SIGNED,GOLD",
            "INV5552,CUST5552,8800,SIGNED,BRONZE",
        ],
        [
            "INV5551,CUST5551,7500,GOLD",
            "INV5551,CUST5551,7500,GOLD",
            "INV5552,CUST5552,8800,BRONZE",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["level"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_level_status_case():
    """Matching should tolerate surrounding spaces and case differences in level/status values."""
    write_inputs(
        [
            " INV6601 , CUST6601 , 6100 , signed , gold ",
            "INV6602,CUST6602,7200,SIGNED,platinum",
        ],
        [
            "INV6601,CUST6601, 6100 ,GOLD",
            " INV6602 , CUST6602 ,7200, PLATINUM ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["sponsorship_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["sponsor_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["level"] for row in rows] == ["GOLD", "PLATINUM"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_report_schema_and_refund_input_order_are_stable():
    """The report should use the required schema and preserve rebate input order."""
    write_inputs(
        [
            "INV9001,CUST9001,100,SIGNED,BRONZE",
            "INV9002,CUST9002,200,SIGNED,GOLD",
            "INV9003,CUST9003,300,SIGNED,PLATINUM",
        ],
        [
            "INV9003,CUST9003,300,PLATINUM",
            "INV9001,CUST9001,100,BRONZE",
            "INV9002,CUST9002,200,GOLD",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "sponsorship_id,sponsor_id,level,amount_cents,status"
    assert [row["sponsorship_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
