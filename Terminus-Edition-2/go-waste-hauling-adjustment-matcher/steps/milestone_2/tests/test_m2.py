"""Tests for the haul adjustment reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "hauls.csv"
PAYMENTS = APP / "data" / "adjustments.csv"
REPORT = APP / "out" / "adjustment_report.csv"
SUMMARY = APP / "out" / "adjustment_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go reconciliation CLI for the current source tree."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all tests."""
    build_program()


def write_inputs(bill_rows, refund_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    INVOICES.write_text("haul_id,account_id,amount_cents,status,route\n" + "\n".join(bill_rows) + "\n")
    PAYMENTS.write_text("haul_id,account_id,amount_cents,route\n" + "\n".join(refund_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_comm_refund_matches_and_counts_positive_amount():
    """COMM adjustments should match completed hauls and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,COMPLETED,RESI",
            "INV20260401002,CUST1002,9900,COMPLETED,COMM",
        ],
        [
            "INV20260401001,CUST1001,12500,RESI",
            "INV20260401002,CUST1002,9900,COMM",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["route"] == "COMM"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_haul_id_match_uses_full_identifier():
    """A adjustment must not match a haul that only shares the leading haul prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,COMPLETED,RESI",
            "INV777770002,CUST2001,3300,COMPLETED,RESI",
        ],
        [
            "INV777770003,CUST2001,3300,RESI",
            "INV777770002,CUST2001,3300,RESI",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["route"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_route_all_gate_matching():
    """Customer, amount, completed status, and allowed route must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,1000,COMPLETED,RESI",
            "INV3002,CUST3002,2000,COMPLETED,COMM",
            "INV3003,CUST3003,3000,DRAFT,IND",
            "INV3004,CUST3004,4000,COMPLETED,CHECK",
            "INV3005,CUST3005,5000,COMPLETED,IND",
        ],
        [
            "INV3001,CUST9999,1000,RESI",
            "INV3002,CUST3002,2100,COMM",
            "INV3003,CUST3003,3000,IND",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,IND",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["route"] == "IND"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_refunds_do_not_reuse_consumed_bill():
    """Only the earliest eligible adjustment may consume a matching haul."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,COMPLETED,COMM",
            "INV5552,CUST5552,8800,COMPLETED,RESI",
        ],
        [
            "INV5551,CUST5551,7500,COMM",
            "INV5551,CUST5551,7500,COMM",
            "INV5552,CUST5552,8800,RESI",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["route"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_route_status_case():
    """Matching should tolerate surrounding spaces and case differences in route/status values."""
    write_inputs(
        [
            " INV6601 , CUST6601 , 6100 , completed , comm ",
            "INV6602,CUST6602,7200,COMPLETED,ind",
        ],
        [
            "INV6601,CUST6601, 6100 ,COMM",
            " INV6602 , CUST6602 ,7200, IND ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["haul_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["account_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["route"] for row in rows] == ["COMM", "IND"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_legacy_route_aliases_match_and_emit_canonical_routes():
    """Legacy COM and INDL adjustment routes should match as COMM and IND and report canonical routes."""
    write_inputs(
        [
            "INV7701,CUST7701,8800,COMPLETED,COMM",
            "INV7702,CUST7702,9100,completed,ind",
            "INV7703,CUST7703,4200,COMPLETED,RESI",
            "INV7704,CUST7704,3300,COMPLETED,CHECK",
        ],
        [
            "INV7701,CUST7701,8800,com",
            "INV7702,CUST7702,9100,INDL",
            "INV7703,CUST7703,4200,resi",
            "INV7704,CUST7704,3300,chk",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["route"] for row in rows] == ["COMM", "IND", "RESI", ""]
    assert summary["matched_count"] == 3
    assert summary["matched_amount_cents"] == 22100
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 3300



def test_res_alias_matches_resi_and_emits_canonical_route():
    """The RES legacy alias should normalize to canonical RESI."""
    write_inputs(
        ["ALIAS1001,CUSTALIAS1,1234,COMPLETED,RESI"],
        ["ALIAS1001,CUSTALIAS1,1234,res"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["route"] == "RESI"
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 1234,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }

def test_report_schema_and_refund_input_order_are_stable():
    """The report should use the required schema and preserve adjustment input order."""
    write_inputs(
        [
            "INV9001,CUST9001,100,COMPLETED,RESI",
            "INV9002,CUST9002,200,COMPLETED,COMM",
            "INV9003,CUST9003,300,COMPLETED,IND",
        ],
        [
            "INV9003,CUST9003,300,IND",
            "INV9001,CUST9001,100,RESI",
            "INV9002,CUST9002,200,COMM",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "haul_id,account_id,route,amount_cents,status"
    assert [row["haul_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
