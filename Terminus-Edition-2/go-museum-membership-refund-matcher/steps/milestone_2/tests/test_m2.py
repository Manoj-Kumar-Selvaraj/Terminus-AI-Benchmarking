"""Verifier tests for the membership refund reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "memberships.csv"
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
    INVOICES.write_text("membership_id,patron_id,amount_cents,status,program\n" + "\n".join(bill_rows) + "\n")
    PAYMENTS.write_text("membership_id,patron_id,amount_cents,program\n" + "\n".join(refund_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_family_refund_matches_and_counts_positive_amount():
    """FAMILY refunds should match active memberships and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,ACTIVE,ADULT",
            "INV20260401002,CUST1002,9900,ACTIVE,FAMILY",
        ],
        [
            "INV20260401001,CUST1001,12500,ADULT",
            "INV20260401002,CUST1002,9900,FAMILY",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["program"] == "FAMILY"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_membership_id_match_uses_full_identifier():
    """A refund must not match a membership that only shares the leading membership prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,ACTIVE,ADULT",
            "INV777770002,CUST2001,3300,ACTIVE,ADULT",
        ],
        [
            "INV777770003,CUST2001,3300,ADULT",
            "INV777770002,CUST2001,3300,ADULT",
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
            "INV3001,CUST3001,1000,ACTIVE,ADULT",
            "INV3002,CUST3002,2000,ACTIVE,FAMILY",
            "INV3003,CUST3003,3000,DRAFT,PATRON",
            "INV3004,CUST3004,4000,ACTIVE,CHECK",
            "INV3005,CUST3005,5000,ACTIVE,PATRON",
        ],
        [
            "INV3001,CUST9999,1000,ADULT",
            "INV3002,CUST3002,2100,FAMILY",
            "INV3003,CUST3003,3000,PATRON",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,PATRON",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["program"] == "PATRON"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_refunds_do_not_reuse_consumed_bill():
    """Only the earliest eligible refund may consume a matching membership."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,ACTIVE,FAMILY",
            "INV5552,CUST5552,8800,ACTIVE,ADULT",
        ],
        [
            "INV5551,CUST5551,7500,FAMILY",
            "INV5551,CUST5551,7500,FAMILY",
            "INV5552,CUST5552,8800,ADULT",
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
            " INV6601 , CUST6601 , 6100 , active , family ",
            "INV6602,CUST6602,7200,ACTIVE,patron",
        ],
        [
            "INV6601,CUST6601, 6100 ,FAMILY",
            " INV6602 , CUST6602 ,7200, PATRON ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["membership_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["patron_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["program"] for row in rows] == ["FAMILY", "PATRON"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_legacy_program_aliases_match_and_emit_canonical_programs():
    """Legacy FAM and PTR refund programs should match as FAMILY and PATRON and report canonical programs."""
    write_inputs(
        [
            "INV7701,CUST7701,8800,ACTIVE,FAMILY",
            "INV7702,CUST7702,9100,active,patron",
            "INV7703,CUST7703,4200,ACTIVE,ADULT",
            "INV7704,CUST7704,3300,ACTIVE,CHECK",
        ],
        [
            "INV7701,CUST7701,8800,fam",
            "INV7702,CUST7702,9100,PTR",
            "INV7703,CUST7703,4200,adult",
            "INV7704,CUST7704,3300,chk",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["program"] for row in rows] == ["FAMILY", "PATRON", "ADULT", ""]
    assert summary["matched_count"] == 3
    assert summary["matched_amount_cents"] == 22100
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 3300


def test_report_schema_and_refund_input_order_are_stable():
    """The report should use the required schema and preserve refund input order."""
    write_inputs(
        [
            "INV9001,CUST9001,100,ACTIVE,ADULT",
            "INV9002,CUST9002,200,ACTIVE,FAMILY",
            "INV9003,CUST9003,300,ACTIVE,PATRON",
        ],
        [
            "INV9003,CUST9003,300,PATRON",
            "INV9001,CUST9001,100,ADULT",
            "INV9002,CUST9002,200,FAMILY",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "membership_id,patron_id,program,amount_cents,status"
    assert [row["membership_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
