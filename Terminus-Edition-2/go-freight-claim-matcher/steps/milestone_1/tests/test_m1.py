"""Verifier tests for the shipment claim reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
SHIPMENTS = APP / "data" / "shipments.csv"
CLAIMS = APP / "data" / "claims.csv"
REPORT = APP / "out" / "claim_report.csv"
SUMMARY = APP / "out" / "claim_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")
REPORT_FIELDS = ["shipment_id", "admgount_id", "reason", "amount_cents", "status"]
SUMMARY_FIELDS = ["matched_count", "matched_amount_cents", "unmatched_count", "unmatched_amount_cents"]


def build_program():
    """Compile the Go reconciliation CLI for the current source tree."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all verifier tests."""
    build_program()


def write_inputs(shipment_rows, claim_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SHIPMENTS.write_text("shipment_id,admgount_id,amount_cents,status,reason\n" + "\n".join(shipment_rows) + "\n")
    CLAIMS.write_text("shipment_id,admgount_id,amount_cents,reason\n" + "\n".join(claim_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == REPORT_FIELDS
        rows = list(reader)
    summary = json.loads(SUMMARY.read_text())
    assert list(summary) == SUMMARY_FIELDS
    assert all(type(summary[key]) is int for key in SUMMARY_FIELDS)
    return rows, summary


def test_lost_claim_matches_and_counts_positive_amount():
    """LOST claims should match posted shipments and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,POSTED,DAMAGED",
            "INV20260401002,CUST1002,9900,POSTED,LOST",
        ],
        [
            "INV20260401001,CUST1001,12500,DAMAGED",
            "INV20260401002,CUST1002,9900,LOST",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["reason"] == "LOST"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_shipment_id_match_uses_full_identifier():
    """A claim must not match a shipment that only shares the leading shipment prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,POSTED,DAMAGED",
            "INV777770002,CUST2001,3300,POSTED,DAMAGED",
        ],
        [
            "INV777770003,CUST2001,3300,DAMAGED",
            "INV777770002,CUST2001,3300,DAMAGED",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["reason"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_admgount_amount_status_and_reason_all_gate_matching():
    """Admgount, amount, posted status, and allowed reason must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,1000,POSTED,DAMAGED",
            "INV3002,CUST3002,2000,POSTED,LOST",
            "INV3003,CUST3003,3000,DRAFT,HAZ",
            "INV3004,CUST3004,4000,POSTED,CHECK",
            "INV3005,CUST3005,5000,POSTED,HAZ",
        ],
        [
            "INV3001,CUST9999,1000,DAMAGED",
            "INV3002,CUST3002,2100,LOST",
            "INV3003,CUST3003,3000,HAZ",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,HAZ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["reason"] == "HAZ"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_claims_do_not_reuse_consumed_shipment():
    """Only the earliest eligible claim may consume a matching shipment."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,POSTED,LOST",
            "INV5552,CUST5552,8800,POSTED,DAMAGED",
        ],
        [
            "INV5551,CUST5551,7500,LOST",
            "INV5551,CUST5551,7500,LOST",
            "INV5552,CUST5552,8800,DAMAGED",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["reason"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_allowed_reason_must_match_between_claim_and_shipment():
    """Allowed but different claim and shipment reasons must not match."""
    write_inputs(
        [
            "INV5651,CUST5651,4300,POSTED,DAMAGED",
            "INV5652,CUST5652,5200,POSTED,LOST",
        ],
        [
            "INV5651,CUST5651,4300,LOST",
            "INV5652,CUST5652,5200,LOST",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert [row["reason"] for row in rows] == ["", "LOST"]
    assert summary["matched_amount_cents"] == 5200
    assert summary["unmatched_amount_cents"] == 4300


def test_matching_trims_fields_and_normalizes_reason_status_case():
    """Matching should trim fields, fold case, and emit cleaned claim reasons."""
    write_inputs(
        [
            " INV6601 , CUST6601 , 6100 , posted , lost ",
            "INV6602,CUST6602,7200,POSTED,haz",
        ],
        [
            " INV6601 , CUST6601 , 6100 , lost ",
            " INV6602 , CUST6602 ,7200, HAZ ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["shipment_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["admgount_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["reason"] for row in rows] == ["LOST", "HAZ"]
    assert all(value == value.strip() for row in rows for value in row.values())
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_report_schema_and_claim_input_order_are_stable():
    """The report should use the required schema and preserve claim input order."""
    write_inputs(
        [
            "INV9001,CUST9001,100,POSTED,DAMAGED",
            "INV9002,CUST9002,200,POSTED,LOST",
            "INV9003,CUST9003,300,POSTED,HAZ",
        ],
        [
            "INV9003,CUST9003,300,HAZ",
            "INV9001,CUST9001,100,DAMAGED",
            "INV9002,CUST9002,200,LOST",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "shipment_id,admgount_id,reason,amount_cents,status"
    assert [row["shipment_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
