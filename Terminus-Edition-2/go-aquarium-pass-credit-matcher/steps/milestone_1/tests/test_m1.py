"""Verifier tests for the pass credit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "passes.csv"
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
    INVOICES.write_text("pass_id,guest_id,amount_cents,status,program\n" + "\n".join(bill_rows) + "\n")
    PAYMENTS.write_text("pass_id,guest_id,amount_cents,program\n" + "\n".join(refund_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_tour_refund_matches_and_counts_positive_amount():
    """TOUR credits should match active passes and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,ACTIVE,GENERAL",
            "INV20260401002,CUST1002,9900,ACTIVE,TOUR",
        ],
        [
            "INV20260401001,CUST1001,12500,GENERAL",
            "INV20260401002,CUST1002,9900,TOUR",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["program"] == "TOUR"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_pass_id_match_uses_full_identifier():
    """A credit must not match a pass that only shares the leading pass prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,ACTIVE,GENERAL",
            "INV777770002,CUST2001,3300,ACTIVE,GENERAL",
        ],
        [
            "INV777770003,CUST2001,3300,GENERAL",
            "INV777770002,CUST2001,3300,GENERAL",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["program"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_program_all_gate_matching():
    """Customer, amount, active status, and allowed program must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,1000,ACTIVE,GENERAL",
            "INV3002,CUST3002,2000,ACTIVE,TOUR",
            "INV3003,CUST3003,3000,DRAFT,MEMBER",
            "INV3004,CUST3004,4000,ACTIVE,CHECK",
            "INV3005,CUST3005,5000,ACTIVE,MEMBER",
        ],
        [
            "INV3001,CUST9999,1000,GENERAL",
            "INV3002,CUST3002,2100,TOUR",
            "INV3003,CUST3003,3000,MEMBER",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,MEMBER",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["program"] == "MEMBER"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_refunds_do_not_reuse_consumed_bill():
    """Only the earliest eligible credit may consume a matching pass."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,ACTIVE,TOUR",
            "INV5552,CUST5552,8800,ACTIVE,GENERAL",
        ],
        [
            "INV5551,CUST5551,7500,TOUR",
            "INV5551,CUST5551,7500,TOUR",
            "INV5552,CUST5552,8800,GENERAL",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["program"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_program_status_case():
    """Matching should tolerate surrounding spaces and case differences in program/status values."""
    write_inputs(
        [
            " INV6601 , CUST6601 , 6100 , active , tour ",
            "INV6602,CUST6602,7200,ACTIVE,member",
        ],
        [
            "INV6601,CUST6601, 6100 ,TOUR",
            " INV6602 , CUST6602 ,7200, MEMBER ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["pass_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["guest_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["program"] for row in rows] == ["TOUR", "MEMBER"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_report_schema_and_refund_input_order_are_stable():
    """The report should use the required schema and preserve credit input order."""
    write_inputs(
        [
            "INV9001,CUST9001,100,ACTIVE,GENERAL",
            "INV9002,CUST9002,200,ACTIVE,TOUR",
            "INV9003,CUST9003,300,ACTIVE,MEMBER",
        ],
        [
            "INV9003,CUST9003,300,MEMBER",
            "INV9001,CUST9001,100,GENERAL",
            "INV9002,CUST9002,200,TOUR",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "pass_id,guest_id,program,amount_cents,status"
    assert [row["pass_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_draft_pass_status_prevents_matching():
    """Only ACTIVE pass status should allow a credit to match."""
    write_inputs(
        ["INVDRAFT1,CUSTDRAFT1,1500,DRAFT,GENERAL"],
        ["INVDRAFT1,CUSTDRAFT1,1500,GENERAL"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["program"] == ""
    assert summary["matched_count"] == 0
    assert summary["unmatched_amount_cents"] == 1500


def test_unmatched_rows_leave_program_blank():
    """Unmatched credits must leave the program column empty."""
    write_inputs(
        ["INVBLANK1,CUSTBLANK1,900,ACTIVE,TOUR"],
        ["INVBLANK1,CUSTBLANK1,900,GENERAL"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["program"] == ""
    assert summary["unmatched_count"] == 1
