"""Verifier tests for the retail order voucher matching CLI CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
ORDROICES = APP / "data" / "orders.csv"
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


def write_inputs(order_rows, voucher_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    ORDROICES.write_text("order_id,customer_id,amount_cents,status,channel\n" + "\n".join(order_rows) + "\n")
    PAYMENTS.write_text("order_id,customer_id,amount_cents,channel\n" + "\n".join(voucher_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_card_voucher_matches_and_counts_positive_amount():
    """CARD vouchers should match posted orders and add positive cents to matched totals."""
    write_inputs(
        [
            "ORDR20260401001,CUST1001,12500,POSTED,ACH",
            "ORDR20260401002,CUST1002,9900,POSTED,CARD",
        ],
        [
            "ORDR20260401001,CUST1001,12500,ACH",
            "ORDR20260401002,CUST1002,9900,CARD",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["channel"] == "CARD"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_order_id_match_uses_full_identifier():
    """A voucher must not match an order that only shares the leading order prefix."""
    write_inputs(
        [
            "ORDR777770001,CUST2001,3300,POSTED,ACH",
            "ORDR777770002,CUST2001,3300,POSTED,ACH",
        ],
        [
            "ORDR777770003,CUST2001,3300,ACH",
            "ORDR777770002,CUST2001,3300,ACH",
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
            "ORDR3001,CUST3001,1000,POSTED,ACH",
            "ORDR3002,CUST3002,2000,POSTED,CARD",
            "ORDR3003,CUST3003,3000,DRAFT,WIRE",
            "ORDR3004,CUST3004,4000,POSTED,CHECK",
            "ORDR3005,CUST3005,5000,POSTED,WIRE",
        ],
        [
            "ORDR3001,CUST9999,1000,ACH",
            "ORDR3002,CUST3002,2100,CARD",
            "ORDR3003,CUST3003,3000,WIRE",
            "ORDR3004,CUST3004,4000,CHECK",
            "ORDR3005,CUST3005,5000,WIRE",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["channel"] == "WIRE"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_vouchers_do_not_reuse_consumed_order():
    """Only the earliest eligible voucher may consume a matching order."""
    write_inputs(
        [
            "ORDR5551,CUST5551,7500,POSTED,CARD",
            "ORDR5552,CUST5552,8800,POSTED,ACH",
        ],
        [
            "ORDR5551,CUST5551,7500,CARD",
            "ORDR5551,CUST5551,7500,CARD",
            "ORDR5552,CUST5552,8800,ACH",
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
            " ORDR6601 , CUST6601 , 6100 , posted , card ",
            "ORDR6602,CUST6602,7200,POSTED,wire",
        ],
        [
            "ORDR6601,CUST6601, 6100 ,CARD",
            " ORDR6602 , CUST6602 ,7200, WIRE ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["order_id"] for row in rows] == ["ORDR6601", "ORDR6602"]
    assert [row["customer_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["channel"] for row in rows] == ["CARD", "WIRE"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_legacy_channel_aliases_match_and_emit_canonical_channels():
    """Legacy CC and WIR voucher channels should match as CARD and WIRE and report canonical channels."""
    write_inputs(
        [
            "ORDR7701,CUST7701,8800,POSTED,CARD",
            "ORDR7702,CUST7702,9100,posted,wire",
            "ORDR7703,CUST7703,4200,POSTED,ACH",
            "ORDR7704,CUST7704,3300,POSTED,CHECK",
        ],
        [
            "ORDR7701,CUST7701,8800,cc",
            "ORDR7702,CUST7702,9100,WIR",
            "ORDR7703,CUST7703,4200,ach",
            "ORDR7704,CUST7704,3300,chk",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["channel"] for row in rows] == ["CARD", "WIRE", "ACH", ""]
    assert summary["matched_count"] == 3
    assert summary["matched_amount_cents"] == 22100
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 3300


def test_report_schema_and_voucher_input_order_are_stable():
    """The report should use the required schema and preserve voucher input order."""
    write_inputs(
        [
            "ORDR9001,CUST9001,100,POSTED,ACH",
            "ORDR9002,CUST9002,200,POSTED,CARD",
            "ORDR9003,CUST9003,300,POSTED,WIRE",
        ],
        [
            "ORDR9003,CUST9003,300,WIRE",
            "ORDR9001,CUST9001,100,ACH",
            "ORDR9002,CUST9002,200,CARD",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "order_id,customer_id,channel,amount_cents,status"
    assert [row["order_id"] for row in rows] == ["ORDR9003", "ORDR9001", "ORDR9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
