"""Verifier tests for the insurance account reimbursement reconciliation CLI CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
ACCTOICES = APP / "data" / "accounts.csv"
PAYMENTS = APP / "data" / "reimbursements.csv"
REPORT = APP / "out" / "reimbursement_report.csv"
SUMMARY = APP / "out" / "reimbursement_summary.json"
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


def write_inputs(account_rows, reimbursement_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    ACCTOICES.write_text("account_id,customer_id,amount_cents,status,channel\n" + "\n".join(account_rows) + "\n")
    PAYMENTS.write_text("account_id,customer_id,amount_cents,channel\n" + "\n".join(reimbursement_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_card_reimbursement_matches_and_counts_positive_amount():
    """CARD reimbursements should match posted accounts and add positive cents to matched totals."""
    write_inputs(
        [
            "ACCT20260401001,CUST1001,12500,POSTED,ACH",
            "ACCT20260401002,CUST1002,9900,POSTED,CARD",
        ],
        [
            "ACCT20260401001,CUST1001,12500,ACH",
            "ACCT20260401002,CUST1002,9900,CARD",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["channel"] == "CARD"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_account_id_match_uses_full_identifier():
    """A reimbursement must not match an account that only shares the leading account prefix."""
    write_inputs(
        [
            "ACCT777770001,CUST2001,3300,POSTED,ACH",
            "ACCT777770002,CUST2001,3300,POSTED,ACH",
        ],
        [
            "ACCT777770003,CUST2001,3300,ACH",
            "ACCT777770002,CUST2001,3300,ACH",
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
            "ACCT3001,CUST3001,1000,POSTED,ACH",
            "ACCT3002,CUST3002,2000,POSTED,CARD",
            "ACCT3003,CUST3003,3000,DRAFT,WIRE",
            "ACCT3004,CUST3004,4000,POSTED,CHECK",
            "ACCT3005,CUST3005,5000,POSTED,WIRE",
        ],
        [
            "ACCT3001,CUST9999,1000,ACH",
            "ACCT3002,CUST3002,2100,CARD",
            "ACCT3003,CUST3003,3000,WIRE",
            "ACCT3004,CUST3004,4000,CHECK",
            "ACCT3005,CUST3005,5000,WIRE",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["channel"] == "WIRE"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_reimbursements_do_not_reuse_consumed_account():
    """Only the earliest eligible reimbursement may consume a matching account."""
    write_inputs(
        [
            "ACCT5551,CUST5551,7500,POSTED,CARD",
            "ACCT5552,CUST5552,8800,POSTED,ACH",
        ],
        [
            "ACCT5551,CUST5551,7500,CARD",
            "ACCT5551,CUST5551,7500,CARD",
            "ACCT5552,CUST5552,8800,ACH",
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
            " ACCT6601 , CUST6601 , 6100 , posted , card ",
            "ACCT6602,CUST6602,7200,POSTED,wire",
        ],
        [
            "ACCT6601,CUST6601, 6100 ,CARD",
            " ACCT6602 , CUST6602 ,7200, WIRE ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["account_id"] for row in rows] == ["ACCT6601", "ACCT6602"]
    assert [row["customer_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["channel"] for row in rows] == ["CARD", "WIRE"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_legacy_channel_aliases_match_and_emit_canonical_channels():
    """Legacy CC and WIR reimbursement channels should match as CARD and WIRE and report canonical channels."""
    write_inputs(
        [
            "ACCT7701,CUST7701,8800,POSTED,CARD",
            "ACCT7702,CUST7702,9100,posted,wire",
            "ACCT7703,CUST7703,4200,POSTED,ACH",
            "ACCT7704,CUST7704,3300,POSTED,CHECK",
        ],
        [
            "ACCT7701,CUST7701,8800,cc",
            "ACCT7702,CUST7702,9100,WIR",
            "ACCT7703,CUST7703,4200,ach",
            "ACCT7704,CUST7704,3300,chk",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["channel"] for row in rows] == ["CARD", "WIRE", "ACH", ""]
    assert summary["matched_count"] == 3
    assert summary["matched_amount_cents"] == 22100
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 3300


def test_report_schema_and_reimbursement_input_order_are_stable():
    """The report should use the required schema and preserve reimbursement input order."""
    write_inputs(
        [
            "ACCT9001,CUST9001,100,POSTED,ACH",
            "ACCT9002,CUST9002,200,POSTED,CARD",
            "ACCT9003,CUST9003,300,POSTED,WIRE",
        ],
        [
            "ACCT9003,CUST9003,300,WIRE",
            "ACCT9001,CUST9001,100,ACH",
            "ACCT9002,CUST9002,200,CARD",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "account_id,customer_id,channel,amount_cents,status"
    assert [row["account_id"] for row in rows] == ["ACCT9003", "ACCT9001", "ACCT9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
