"""Verifier tests for the telecom service credit matching CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
SERVICES = APP / "data" / "services.csv"
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


def write_inputs(service_rows, credit_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SERVICES.write_text("service_id,customer_id,amount_cents,status,channel\n" + "\n".join(service_rows) + "\n")
    PAYMENTS.write_text("service_id,customer_id,amount_cents,channel\n" + "\n".join(credit_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_card_credit_matches_and_counts_positive_amount():
    """CARD credits should match posted services and add positive cents to matched totals."""
    write_inputs(
        [
            "SVC20260401001,CUST1001,12500,POSTED,ACH",
            "SVC20260401002,CUST1002,9900,POSTED,CARD",
        ],
        [
            "SVC20260401001,CUST1001,12500,ACH",
            "SVC20260401002,CUST1002,9900,CARD",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["channel"] == "CARD"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_service_id_match_uses_full_identifier():
    """A credit must not match a service that only shares the leading service prefix."""
    write_inputs(
        [
            "SVC777770001,CUST2001,3300,POSTED,ACH",
            "SVC777770002,CUST2001,3300,POSTED,ACH",
        ],
        [
            "SVC777770003,CUST2001,3300,ACH",
            "SVC777770002,CUST2001,3300,ACH",
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
            "SVC3001,CUST3001,1000,POSTED,ACH",
            "SVC3002,CUST3002,2000,POSTED,CARD",
            "SVC3003,CUST3003,3000,DRAFT,WIRE",
            "SVC3004,CUST3004,4000,POSTED,CHECK",
            "SVC3005,CUST3005,5000,POSTED,WIRE",
        ],
        [
            "SVC3001,CUST9999,1000,ACH",
            "SVC3002,CUST3002,2100,CARD",
            "SVC3003,CUST3003,3000,WIRE",
            "SVC3004,CUST3004,4000,CHECK",
            "SVC3005,CUST3005,5000,WIRE",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["channel"] == "WIRE"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_credits_do_not_reuse_consumed_service():
    """Only the earliest eligible credit may consume a matching service."""
    write_inputs(
        [
            "SVC5551,CUST5551,7500,POSTED,CARD",
            "SVC5552,CUST5552,8800,POSTED,ACH",
        ],
        [
            "SVC5551,CUST5551,7500,CARD",
            "SVC5551,CUST5551,7500,CARD",
            "SVC5552,CUST5552,8800,ACH",
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
            " SVC6601 , CUST6601 , 6100 , posted , card ",
            "SVC6602,CUST6602,7200,POSTED,wire",
        ],
        [
            "SVC6601,CUST6601, 6100 ,CARD",
            " SVC6602 , CUST6602 ,7200, WIRE ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["service_id"] for row in rows] == ["SVC6601", "SVC6602"]
    assert [row["customer_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["channel"] for row in rows] == ["CARD", "WIRE"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_report_schema_and_credit_input_order_are_stable():
    """The report should use the required schema and preserve credit input order."""
    write_inputs(
        [
            "SVC9001,CUST9001,100,POSTED,ACH",
            "SVC9002,CUST9002,200,POSTED,CARD",
            "SVC9003,CUST9003,300,POSTED,WIRE",
        ],
        [
            "SVC9003,CUST9003,300,WIRE",
            "SVC9001,CUST9001,100,ACH",
            "SVC9002,CUST9002,200,CARD",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "service_id,customer_id,channel,amount_cents,status"
    assert [row["service_id"] for row in rows] == ["SVC9003", "SVC9001", "SVC9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
