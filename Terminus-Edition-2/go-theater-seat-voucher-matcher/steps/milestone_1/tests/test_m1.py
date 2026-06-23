"""Verifier tests for the ticket voucher reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "tickets.csv"
PAYMENTS = APP / "data" / "vouchers.csv"
REPORT = APP / "out" / "voucher_report.csv"
SUMMARY = APP / "out" / "voucher_summary.json"
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
    INVOICES.write_text("ticket_id,patron_id,amount_cents,status,seat_zone\n" + "\n".join(bill_rows) + "\n")
    PAYMENTS.write_text("ticket_id,patron_id,amount_cents,seat_zone\n" + "\n".join(refund_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_mezz_refund_matches_and_counts_positive_amount():
    """MEZZ vouchers should match issued tickets and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,ISSUED,ORCH",
            "INV20260401002,CUST1002,9900,ISSUED,MEZZ",
        ],
        [
            "INV20260401001,CUST1001,12500,ORCH",
            "INV20260401002,CUST1002,9900,MEZZ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["seat_zone"] == "MEZZ"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_ticket_id_match_uses_full_identifier():
    """A voucher must not match a ticket that only shares the leading ticket prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,ISSUED,ORCH",
            "INV777770002,CUST2001,3300,ISSUED,ORCH",
        ],
        [
            "INV777770003,CUST2001,3300,ORCH",
            "INV777770002,CUST2001,3300,ORCH",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["seat_zone"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_seat_zone_all_gate_matching():
    """Customer, amount, issued status, and allowed seat_zone must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,1000,ISSUED,ORCH",
            "INV3002,CUST3002,2000,ISSUED,MEZZ",
            "INV3003,CUST3003,3000,DRAFT,BALC",
            "INV3004,CUST3004,4000,ISSUED,CHECK",
            "INV3005,CUST3005,5000,ISSUED,BALC",
        ],
        [
            "INV3001,CUST9999,1000,ORCH",
            "INV3002,CUST3002,2100,MEZZ",
            "INV3003,CUST3003,3000,BALC",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,BALC",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["seat_zone"] == "BALC"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_refunds_do_not_reuse_consumed_bill():
    """Only the earliest eligible voucher may consume a matching ticket."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,ISSUED,MEZZ",
            "INV5552,CUST5552,8800,ISSUED,ORCH",
        ],
        [
            "INV5551,CUST5551,7500,MEZZ",
            "INV5551,CUST5551,7500,MEZZ",
            "INV5552,CUST5552,8800,ORCH",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["seat_zone"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_seat_zone_status_case():
    """Matching should tolerate surrounding spaces and case differences in seat_zone/status values."""
    write_inputs(
        [
            " INV6601 , CUST6601 , 6100 , issued , mezz ",
            "INV6602,CUST6602,7200,ISSUED,balc",
        ],
        [
            "INV6601,CUST6601, 6100 ,MEZZ",
            " INV6602 , CUST6602 ,7200, BALC ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["ticket_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["patron_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["seat_zone"] for row in rows] == ["MEZZ", "BALC"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_report_schema_and_refund_input_order_are_stable():
    """The report should use the required schema and preserve voucher input order."""
    write_inputs(
        [
            "INV9001,CUST9001,100,ISSUED,ORCH",
            "INV9002,CUST9002,200,ISSUED,MEZZ",
            "INV9003,CUST9003,300,ISSUED,BALC",
        ],
        [
            "INV9003,CUST9003,300,BALC",
            "INV9001,CUST9001,100,ORCH",
            "INV9002,CUST9002,200,MEZZ",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "ticket_id,patron_id,seat_zone,amount_cents,status"
    assert [row["ticket_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
