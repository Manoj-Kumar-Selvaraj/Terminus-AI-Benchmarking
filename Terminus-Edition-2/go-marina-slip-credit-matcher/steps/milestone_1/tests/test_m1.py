"""Verifier tests for the slip credit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "slips.csv"
PAYMENTS = APP / "data" / "credits.csv"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"
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
    INVOICES.write_text("slip_id,member_id,amount_cents,status,dock_zone\n" + "\n".join(bill_rows) + "\n")
    PAYMENTS.write_text("slip_id,member_id,amount_cents,dock_zone\n" + "\n".join(refund_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_south_refund_matches_and_counts_positive_amount():
    """SOUTH credits should match docked slips and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,DOCKED,NORTH",
            "INV20260401002,CUST1002,9900,DOCKED,SOUTH",
        ],
        [
            "INV20260401001,CUST1001,12500,NORTH",
            "INV20260401002,CUST1002,9900,SOUTH",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["dock_zone"] == "SOUTH"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_slip_id_match_uses_full_identifier():
    """A credit must not match a slip that only shares the leading slip prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,DOCKED,NORTH",
            "INV777770002,CUST2001,3300,DOCKED,NORTH",
        ],
        [
            "INV777770003,CUST2001,3300,NORTH",
            "INV777770002,CUST2001,3300,NORTH",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["dock_zone"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_dock_zone_all_gate_matching():
    """Customer, amount, docked status, and allowed dock_zone must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,1000,DOCKED,NORTH",
            "INV3002,CUST3002,2000,DOCKED,SOUTH",
            "INV3003,CUST3003,3000,DRAFT,EAST",
            "INV3004,CUST3004,4000,DOCKED,CHECK",
            "INV3005,CUST3005,5000,DOCKED,EAST",
        ],
        [
            "INV3001,CUST9999,1000,NORTH",
            "INV3002,CUST3002,2100,SOUTH",
            "INV3003,CUST3003,3000,EAST",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,EAST",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["dock_zone"] == "EAST"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_refunds_do_not_reuse_consumed_bill():
    """Only the earliest eligible credit may consume a matching slip."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,DOCKED,SOUTH",
            "INV5552,CUST5552,8800,DOCKED,NORTH",
        ],
        [
            "INV5551,CUST5551,7500,SOUTH",
            "INV5551,CUST5551,7500,SOUTH",
            "INV5552,CUST5552,8800,NORTH",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["dock_zone"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_dock_zone_status_case():
    """Matching should tolerate surrounding spaces and case differences in dock_zone/status values."""
    write_inputs(
        [
            " INV6601 , CUST6601 , 6100 , docked , south ",
            "INV6602,CUST6602,7200,DOCKED,east",
        ],
        [
            "INV6601,CUST6601, 6100 ,South",
            " INV6602 , CUST6602 ,7200, EAST ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["slip_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["member_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["dock_zone"] for row in rows] == ["South", "EAST"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_report_schema_and_refund_input_order_are_stable():
    """The report should use the required schema and preserve credit input order."""
    write_inputs(
        [
            "INV9001,CUST9001,100,DOCKED,NORTH",
            "INV9002,CUST9002,200,DOCKED,SOUTH",
            "INV9003,CUST9003,300,DOCKED,EAST",
        ],
        [
            "INV9003,CUST9003,300,EAST",
            "INV9001,CUST9001,100,NORTH",
            "INV9002,CUST9002,200,SOUTH",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "slip_id,member_id,dock_zone,amount_cents,status"
    assert [row["slip_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
