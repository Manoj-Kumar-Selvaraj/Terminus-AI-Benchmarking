"""Verifier tests for the lease credit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "leases.csv"
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
    INVOICES.write_text("lease_id,tenant_id,amount_cents,status,unit_type\n" + "\n".join(bill_rows) + "\n")
    PAYMENTS.write_text("lease_id,tenant_id,amount_cents,unit_type\n" + "\n".join(refund_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_medium_refund_matches_and_counts_positive_amount():
    """MEDIUM credits should match active leases and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,ACTIVE,SMALL",
            "INV20260401002,CUST1002,9900,ACTIVE,MEDIUM",
        ],
        [
            "INV20260401001,CUST1001,12500,SMALL",
            "INV20260401002,CUST1002,9900,MEDIUM",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["unit_type"] == "MEDIUM"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_lease_id_match_uses_full_identifier():
    """A credit must not match a lease that only shares the leading lease prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,ACTIVE,SMALL",
            "INV777770002,CUST2001,3300,ACTIVE,SMALL",
        ],
        [
            "INV777770003,CUST2001,3300,SMALL",
            "INV777770002,CUST2001,3300,SMALL",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["unit_type"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_unit_type_all_gate_matching():
    """Customer, amount, active status, and allowed unit_type must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,1000,ACTIVE,SMALL",
            "INV3002,CUST3002,2000,ACTIVE,MEDIUM",
            "INV3003,CUST3003,3000,DRAFT,LARGE",
            "INV3004,CUST3004,4000,ACTIVE,CHECK",
            "INV3005,CUST3005,5000,ACTIVE,LARGE",
        ],
        [
            "INV3001,CUST9999,1000,SMALL",
            "INV3002,CUST3002,2100,MEDIUM",
            "INV3003,CUST3003,3000,LARGE",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,LARGE",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["unit_type"] == "LARGE"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_refunds_do_not_reuse_consumed_bill():
    """Only the earliest eligible credit may consume a matching lease."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,ACTIVE,MEDIUM",
            "INV5552,CUST5552,8800,ACTIVE,SMALL",
        ],
        [
            "INV5551,CUST5551,7500,MEDIUM",
            "INV5551,CUST5551,7500,MEDIUM",
            "INV5552,CUST5552,8800,SMALL",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["unit_type"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_unit_type_status_case():
    """Matching should tolerate surrounding spaces and case differences in unit_type/status values."""
    write_inputs(
        [
            " INV6601 , CUST6601 , 6100 , active , medium ",
            "INV6602,CUST6602,7200,ACTIVE,large",
        ],
        [
            "INV6601,CUST6601, 6100 ,MEDIUM",
            " INV6602 , CUST6602 ,7200, LARGE ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["lease_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["tenant_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["unit_type"] for row in rows] == ["MEDIUM", "LARGE"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_legacy_unit_type_aliases_match_and_emit_canonical_unit_types():
    """Legacy MED and LRG credit unit_types should match as MEDIUM and LARGE and report canonical unit_types."""
    write_inputs(
        [
            "INV7701,CUST7701,8800,ACTIVE,MEDIUM",
            "INV7702,CUST7702,9100,active,large",
            "INV7703,CUST7703,4200,ACTIVE,SMALL",
            "INV7704,CUST7704,3300,ACTIVE,CHECK",
        ],
        [
            "INV7701,CUST7701,8800,med",
            "INV7702,CUST7702,9100,LRG",
            "INV7703,CUST7703,4200,small",
            "INV7704,CUST7704,3300,chk",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["unit_type"] for row in rows] == ["MEDIUM", "LARGE", "SMALL", ""]
    assert summary["matched_count"] == 3
    assert summary["matched_amount_cents"] == 22100
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 3300


def test_report_schema_and_refund_input_order_are_stable():
    """The report should use the required schema and preserve credit input order."""
    write_inputs(
        [
            "INV9001,CUST9001,100,ACTIVE,SMALL",
            "INV9002,CUST9002,200,ACTIVE,MEDIUM",
            "INV9003,CUST9003,300,ACTIVE,LARGE",
        ],
        [
            "INV9003,CUST9003,300,LARGE",
            "INV9001,CUST9001,100,SMALL",
            "INV9002,CUST9002,200,MEDIUM",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "lease_id,tenant_id,unit_type,amount_cents,status"
    assert [row["lease_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
