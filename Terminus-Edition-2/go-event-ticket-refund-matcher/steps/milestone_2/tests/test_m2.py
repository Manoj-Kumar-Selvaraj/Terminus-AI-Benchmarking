"""Verifier tests for the booking refund reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "bookings.csv"
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
    INVOICES.write_text("booking_id,attendee_id,amount_cents,status,tier\n" + "\n".join(bill_rows) + "\n")
    PAYMENTS.write_text("booking_id,attendee_id,amount_cents,tier\n" + "\n".join(refund_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_vip_refund_matches_and_counts_positive_amount():
    """VIP refunds should match confirmed bookings and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,CONFIRMED,GA",
            "INV20260401002,CUST1002,9900,CONFIRMED,VIP",
        ],
        [
            "INV20260401001,CUST1001,12500,GA",
            "INV20260401002,CUST1002,9900,VIP",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["tier"] == "VIP"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_booking_id_match_uses_full_identifier():
    """A refund must not match a booking that only shares the leading booking prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,CONFIRMED,GA",
            "INV777770002,CUST2001,3300,CONFIRMED,GA",
        ],
        [
            "INV777770003,CUST2001,3300,GA",
            "INV777770002,CUST2001,3300,GA",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["tier"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_tier_all_gate_matching():
    """Customer, amount, confirmed status, and allowed tier must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,1000,CONFIRMED,GA",
            "INV3002,CUST3002,2000,CONFIRMED,VIP",
            "INV3003,CUST3003,3000,DRAFT,COMP",
            "INV3004,CUST3004,4000,CONFIRMED,CHECK",
            "INV3005,CUST3005,5000,CONFIRMED,COMP",
        ],
        [
            "INV3001,CUST9999,1000,GA",
            "INV3002,CUST3002,2100,VIP",
            "INV3003,CUST3003,3000,COMP",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,COMP",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["tier"] == "COMP"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_refunds_do_not_reuse_consumed_bill():
    """Only the earliest eligible refund may consume a matching booking."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,CONFIRMED,VIP",
            "INV5552,CUST5552,8800,CONFIRMED,GA",
        ],
        [
            "INV5551,CUST5551,7500,VIP",
            "INV5551,CUST5551,7500,VIP",
            "INV5552,CUST5552,8800,GA",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["tier"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_tier_status_case():
    """Matching should tolerate surrounding spaces and case differences in tier/status values."""
    write_inputs(
        [
            " INV6601 , CUST6601 , 6100 , confirmed , vip ",
            "INV6602,CUST6602,7200,CONFIRMED,comp",
        ],
        [
            "INV6601,CUST6601, 6100 ,VIP",
            " INV6602 , CUST6602 ,7200, COMP ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["booking_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["attendee_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["tier"] for row in rows] == ["VIP", "COMP"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_legacy_tier_aliases_match_and_emit_canonical_tiers():
    """Legacy STD, PLT, and INV refund tiers should match and report canonical tiers."""
    write_inputs(
        [
            "INV7701,CUST7701,8800,CONFIRMED,VIP",
            "INV7702,CUST7702,9100,confirmed,comp",
            "INV7703,CUST7703,4200,CONFIRMED,GA",
            "INV7704,CUST7704,5500,CONFIRMED,GA",
            "INV7705,CUST7705,3300,CONFIRMED,CHECK",
        ],
        [
            "INV7701,CUST7701,8800,plt",
            "INV7702,CUST7702,9100,INV",
            "INV7703,CUST7703,4200,std",
            "INV7704,CUST7704,5500,STD",
            "INV7705,CUST7705,3300,chk",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["tier"] for row in rows] == ["VIP", "COMP", "GA", "GA", ""]
    assert summary["matched_count"] == 4
    assert summary["matched_amount_cents"] == 27600
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 3300


def test_std_alias_matches_ga_booking_and_emits_canonical_tier():
    """A STD refund must match a GA booking and emit GA as the tier."""
    write_inputs(
        ["INV7801,CUST7801,1234,CONFIRMED,GA"],
        ["INV7801,CUST7801,1234,std"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["tier"] == "GA"
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 1234,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_report_schema_and_refund_input_order_are_stable():
    """The report should use the required schema and preserve refund input order."""
    write_inputs(
        [
            "INV9001,CUST9001,100,CONFIRMED,GA",
            "INV9002,CUST9002,200,CONFIRMED,VIP",
            "INV9003,CUST9003,300,CONFIRMED,COMP",
        ],
        [
            "INV9003,CUST9003,300,COMP",
            "INV9001,CUST9001,100,GA",
            "INV9002,CUST9002,200,VIP",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "booking_id,attendee_id,tier,amount_cents,status"
    assert [row["booking_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
