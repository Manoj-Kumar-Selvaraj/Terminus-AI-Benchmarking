"""Verifier tests for alias handling plus milestone 1 regression behavior.

The first five tests intentionally repeat the milestone 1 contract so alias
support cannot regress exact matching, trimming, consumption, or totals.
"""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
BILLS = APP / "data" / "bills.csv"
REFUNDS = APP / "data" / "refunds.csv"
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
    BILLS.write_text("bill_id,customer_id,amount_cents,status,channel\n" + "\n".join(bill_rows) + "\n")
    REFUNDS.write_text("bill_id,customer_id,amount_cents,channel\n" + "\n".join(refund_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_card_refund_matches_and_counts_positive_amount():
    """CARD refunds should match posted bills and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,POSTED,ACH",
            "INV20260401002,CUST1002,9900,POSTED,CARD",
        ],
        [
            "INV20260401001,CUST1001,12500,ACH",
            "INV20260401002,CUST1002,9900,CARD",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["channel"] == "CARD"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_bill_id_match_uses_full_identifier():
    """A refund must not match a bill that only shares the leading bill prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,POSTED,ACH",
            "INV777770002,CUST2001,3300,POSTED,ACH",
        ],
        [
            "INV777770003,CUST2001,3300,ACH",
            "INV777770002,CUST2001,3300,ACH",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["channel"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_channel_all_gate_matching():
    """Customer, amount, posted status, and allowed channel must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,1000,POSTED,ACH",
            "INV3002,CUST3002,2000,POSTED,CARD",
            "INV3003,CUST3003,3000,DRAFT,WIRE",
            "INV3004,CUST3004,4000,POSTED,CHECK",
            "INV3005,CUST3005,5000,POSTED,WIRE",
        ],
        [
            "INV3001,CUST9999,1000,ACH",
            "INV3002,CUST3002,2100,CARD",
            "INV3003,CUST3003,3000,WIRE",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,WIRE",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["channel"] == "WIRE"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_refunds_do_not_reuse_consumed_bill():
    """Only the earliest eligible refund may consume a matching bill."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,POSTED,CARD",
            "INV5552,CUST5552,8800,POSTED,ACH",
        ],
        [
            "INV5551,CUST5551,7500,CARD",
            "INV5551,CUST5551,7500,CARD",
            "INV5552,CUST5552,8800,ACH",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["channel"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_channel_status_case():
    """Matching should tolerate surrounding spaces and case differences in channel/status values."""
    write_inputs(
        [
            " INV6601 , CUST6601 , 6100 , posted , card ",
            "INV6602,CUST6602,7200,POSTED,wire",
        ],
        [
            "INV6601,CUST6601, 6100 ,CARD",
            " INV6602 , CUST6602 ,7200, WIRE ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["bill_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["customer_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["channel"] for row in rows] == ["CARD", "WIRE"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_legacy_channel_aliases_match_and_emit_canonical_channels():
    """Legacy CC and WIR refund channels should match as CARD and WIRE and report canonical channels."""
    write_inputs(
        [
            "INV7701,CUST7701,8800,POSTED,CARD",
            "INV7702,CUST7702,9100,posted,wire",
            "INV7703,CUST7703,4200,POSTED,ACH",
            "INV7704,CUST7704,3300,POSTED,CHECK",
        ],
        [
            "INV7701,CUST7701,8800,cc",
            "INV7702,CUST7702,9100,WIR",
            "INV7703,CUST7703,4200,ach",
            "INV7704,CUST7704,3300,chk",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["channel"] for row in rows] == ["CARD", "WIRE", "ACH", ""]
    assert summary["matched_count"] == 3
    assert summary["matched_amount_cents"] == 22100
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 3300


def test_report_schema_and_refund_input_order_are_stable():
    """The report should use the required schema and preserve refund input order."""
    write_inputs(
        [
            "INV9001,CUST9001,100,POSTED,ACH",
            "INV9002,CUST9002,200,POSTED,CARD",
            "INV9003,CUST9003,300,POSTED,WIRE",
        ],
        [
            "INV9003,CUST9003,300,WIRE",
            "INV9001,CUST9001,100,ACH",
            "INV9002,CUST9002,200,CARD",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "bill_id,customer_id,channel,amount_cents,status"
    assert [row["bill_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
