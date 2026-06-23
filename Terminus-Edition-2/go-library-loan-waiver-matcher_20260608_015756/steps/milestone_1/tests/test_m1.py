"""Verifier tests for the library loan waiver matching CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
LOANS = APP / "data" / "loans.csv"
WAIVERS = APP / "data" / "waivers.csv"
REPORT = APP / "out" / "waiver_report.csv"
SUMMARY = APP / "out" / "waiver_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go reconciliation CLI for the current source tree."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all verifier tests."""
    build_program()


def write_inputs(loan_rows, waiver_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    LOANS.write_text("loan_id,customer_id,amount_cents,status,channel\n" + "\n".join(loan_rows) + "\n")
    WAIVERS.write_text("loan_id,customer_id,amount_cents,channel\n" + "\n".join(waiver_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_card_waiver_matches_and_counts_positive_amount():
    """CARD waivers should match posted loans and add positive cents to matched totals."""
    write_inputs(
        [
            "LOAN20260401001,CUST1001,12500,POSTED,ACH",
            "LOAN20260401002,CUST1002,9900,POSTED,CARD",
        ],
        [
            "LOAN20260401001,CUST1001,12500,ACH",
            "LOAN20260401002,CUST1002,9900,CARD",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["channel"] == "CARD"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_loan_id_match_uses_full_identifier():
    """A waiver must not match a loan that only shares the leading loan prefix."""
    write_inputs(
        [
            "LOAN777770001,CUST2001,3300,POSTED,ACH",
            "LOAN777770002,CUST2001,3300,POSTED,ACH",
        ],
        [
            "LOAN777770003,CUST2001,3300,ACH",
            "LOAN777770002,CUST2001,3300,ACH",
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
            "LOAN3001,CUST3001,1000,POSTED,ACH",
            "LOAN3002,CUST3002,2000,POSTED,CARD",
            "LOAN3003,CUST3003,3000,DRAFT,WIRE",
            "LOAN3004,CUST3004,4000,POSTED,CHECK",
            "LOAN3005,CUST3005,5000,POSTED,WIRE",
        ],
        [
            "LOAN3001,CUST9999,1000,ACH",
            "LOAN3002,CUST3002,2100,CARD",
            "LOAN3003,CUST3003,3000,WIRE",
            "LOAN3004,CUST3004,4000,CHECK",
            "LOAN3005,CUST3005,5000,WIRE",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["channel"] == "WIRE"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_waivers_do_not_reuse_consumed_loan():
    """Only the earliest eligible waiver may consume a matching loan."""
    write_inputs(
        [
            "LOAN5551,CUST5551,7500,POSTED,CARD",
            "LOAN5552,CUST5552,8800,POSTED,ACH",
        ],
        [
            "LOAN5551,CUST5551,7500,CARD",
            "LOAN5551,CUST5551,7500,CARD",
            "LOAN5552,CUST5552,8800,ACH",
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
            " LOAN6601 , CUST6601 , 6100 , posted , card ",
            "LOAN6602,CUST6602,7200,POSTED,wire",
        ],
        [
            "LOAN6601,CUST6601, 6100 ,CARD",
            " LOAN6602 , CUST6602 ,7200, WIRE ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["loan_id"] for row in rows] == ["LOAN6601", "LOAN6602"]
    assert [row["customer_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["channel"] for row in rows] == ["CARD", "WIRE"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_report_schema_and_waiver_input_order_are_stable():
    """The report should use the required schema and preserve waiver input order."""
    write_inputs(
        [
            "LOAN9001,CUST9001,100,POSTED,ACH",
            "LOAN9002,CUST9002,200,POSTED,CARD",
            "LOAN9003,CUST9003,300,POSTED,WIRE",
        ],
        [
            "LOAN9003,CUST9003,300,WIRE",
            "LOAN9001,CUST9001,100,ACH",
            "LOAN9002,CUST9002,200,CARD",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "loan_id,customer_id,channel,amount_cents,status"
    assert [row["loan_id"] for row in rows] == ["LOAN9003", "LOAN9001", "LOAN9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
