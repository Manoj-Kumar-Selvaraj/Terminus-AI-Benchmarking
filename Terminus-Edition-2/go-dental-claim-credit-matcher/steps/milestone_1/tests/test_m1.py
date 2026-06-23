"""Verifier tests for the claim credit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
CLAIMS = APP / "data" / "claims.csv"
CREDITS = APP / "data" / "credits.csv"
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


def write_inputs(claim_rows, credit_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    CLAIMS.write_text("claim_id,patient_id,amount_cents,status,procedure\n" + "\n".join(claim_rows) + "\n")
    CREDITS.write_text("claim_id,patient_id,amount_cents,procedure\n" + "\n".join(credit_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_restorative_credit_matches_and_counts_positive_amount():
    """RESTORATIVE credits should match approved claims and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,APPROVED,PREVENTIVE",
            "INV20260401002,CUST1002,9900,APPROVED,RESTORATIVE",
        ],
        [
            "INV20260401001,CUST1001,12500,PREVENTIVE",
            "INV20260401002,CUST1002,9900,RESTORATIVE",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["procedure"] == "RESTORATIVE"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_unmatched_report_fields_are_trimmed():
    """Unmatched report rows must not carry incidental surrounding spaces from credit input."""
    write_inputs(
        ["INV8101,CUST8101,1200,APPROVED,PREVENTIVE"],
        [" INV8102 , CUST8102 , 900 , PREVENTIVE "],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["claim_id"] == "INV8102"
    assert rows[0]["patient_id"] == "CUST8102"
    assert rows[0]["amount_cents"] == "900"
    assert rows[0]["procedure"] == ""
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 900


def test_claim_id_match_uses_full_identifier():
    """A credit must not match a claim that only shares the leading claim prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,APPROVED,PREVENTIVE",
            "INV777770002,CUST2001,3300,APPROVED,PREVENTIVE",
        ],
        [
            "INV777770003,CUST2001,3300,PREVENTIVE",
            "INV777770002,CUST2001,3300,PREVENTIVE",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["procedure"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_patient_amount_status_and_procedure_all_gate_matching():
    """Patient, amount, approved status, and allowed procedure must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,1000,APPROVED,PREVENTIVE",
            "INV3002,CUST3002,2000,APPROVED,RESTORATIVE",
            "INV3003,CUST3003,3000,DRAFT,ORTHO",
            "INV3004,CUST3004,4000,APPROVED,CHECK",
            "INV3005,CUST3005,5000,APPROVED,ORTHO",
        ],
        [
            "INV3001,CUST9999,1000,PREVENTIVE",
            "INV3002,CUST3002,2100,RESTORATIVE",
            "INV3003,CUST3003,3000,ORTHO",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,ORTHO",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["procedure"] == "ORTHO"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_credits_do_not_reuse_consumed_claim():
    """Only the earliest eligible credit may consume a matching claim."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,APPROVED,RESTORATIVE",
            "INV5552,CUST5552,8800,APPROVED,PREVENTIVE",
        ],
        [
            "INV5551,CUST5551,7500,RESTORATIVE",
            "INV5551,CUST5551,7500,RESTORATIVE",
            "INV5552,CUST5552,8800,PREVENTIVE",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["procedure"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_procedure_status_case():
    """Matching should tolerate surrounding spaces and case differences in procedure/status values."""
    write_inputs(
        [
            " INV6601 , CUST6601 , 6100 , approved , restorative ",
            "INV6602,CUST6602,7200,APPROVED,ortho",
        ],
        [
            "INV6601,CUST6601, 6100 ,RESTORATIVE",
            " INV6602 , CUST6602 ,7200, ORTHO ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["claim_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["patient_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["procedure"] for row in rows] == ["RESTORATIVE", "ORTHO"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_report_schema_and_credit_input_order_are_stable():
    """The report should use the required schema and preserve credit input order."""
    write_inputs(
        [
            "INV9001,CUST9001,100,APPROVED,PREVENTIVE",
            "INV9002,CUST9002,200,APPROVED,RESTORATIVE",
            "INV9003,CUST9003,300,APPROVED,ORTHO",
        ],
        [
            "INV9003,CUST9003,300,ORTHO",
            "INV9001,CUST9001,100,PREVENTIVE",
            "INV9002,CUST9002,200,RESTORATIVE",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "claim_id,patient_id,procedure,amount_cents,status"
    assert [row["claim_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert set(summary.keys()) == {
        "matched_count",
        "matched_amount_cents",
        "unmatched_count",
        "unmatched_amount_cents",
    }
    assert all(isinstance(summary[key], int) for key in summary)
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_empty_credits_file_produces_empty_report_and_zero_summary():
    """A credits file with only the header should produce no report rows and zero totals."""
    write_inputs(
        ["INVEMPTY1,CUSTEMPTY1,100,APPROVED,PREVENTIVE"],
        [],
    )
    rows, summary = run_program()

    assert rows == []
    assert REPORT.read_text().splitlines()[0] == "claim_id,patient_id,procedure,amount_cents,status"
    assert summary == {
        "matched_count": 0,
        "matched_amount_cents": 0,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
    assert all(isinstance(summary[key], int) for key in summary)


def test_empty_claims_file_keeps_credits_unmatched_with_positive_totals():
    """A claims file with only the header should leave credits unmatched and count positive cents."""
    write_inputs(
        [],
        [
            "INVEMPTY2,CUSTEMPTY2,250,PREVENTIVE",
            "INVEMPTY3,CUSTEMPTY3,350,RESTORATIVE",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
    assert [row["procedure"] for row in rows] == ["", ""]
    assert summary == {
        "matched_count": 0,
        "matched_amount_cents": 0,
        "unmatched_count": 2,
        "unmatched_amount_cents": 600,
    }
