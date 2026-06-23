"""Verifier tests for the attendance credit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
ATTENDANCES = APP / "data" / "attendances.csv"
CREDITS = APP / "data" / "credits.csv"
REPORT = APP / "out" / "attendance_credit_report.csv"
SUMMARY = APP / "out" / "attendance_credit_summary.json"
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


def write_inputs(attendance_rows, credit_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    ATTENDANCES.write_text("attendance_id,child_id,amount_cents,status,care_type\n" + "\n".join(attendance_rows) + "\n")
    CREDITS.write_text("attendance_id,child_id,amount_cents,care_type\n" + "\n".join(credit_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_full_credit_matches_and_counts_positive_amount():
    """FULL credits should match active attendances and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,ACTIVE,HALF",
            "INV20260401002,CUST1002,9900,ACTIVE,FULL",
        ],
        [
            "INV20260401001,CUST1001,12500,HALF",
            "INV20260401002,CUST1002,9900,FULL",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["care_type"] == "FULL"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_attendance_id_match_uses_full_identifier():
    """A credit must not match a attendance that only shares the leading attendance prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,ACTIVE,HALF",
            "INV777770002,CUST2001,3300,ACTIVE,HALF",
        ],
        [
            "INV777770003,CUST2001,3300,HALF",
            "INV777770002,CUST2001,3300,HALF",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["care_type"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_care_type_all_gate_matching():
    """Customer, amount, active status, and allowed care_type must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,1000,ACTIVE,HALF",
            "INV3002,CUST3002,2000,ACTIVE,FULL",
            "INV3003,CUST3003,3000,DRAFT,EXT",
            "INV3004,CUST3004,4000,ACTIVE,CHECK",
            "INV3005,CUST3005,5000,ACTIVE,EXT",
        ],
        [
            "INV3001,CUST9999,1000,HALF",
            "INV3002,CUST3002,2100,FULL",
            "INV3003,CUST3003,3000,EXT",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,EXT",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["care_type"] == "EXT"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_credits_do_not_reuse_consumed_attendance():
    """Only the earliest eligible credit may consume a matching attendance."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,ACTIVE,FULL",
            "INV5552,CUST5552,8800,ACTIVE,HALF",
        ],
        [
            "INV5551,CUST5551,7500,FULL",
            "INV5551,CUST5551,7500,FULL",
            "INV5552,CUST5552,8800,HALF",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["care_type"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_care_type_status_case():
    """Matching should tolerate surrounding spaces and case differences in care_type/status values."""
    write_inputs(
        [
            " INV6601 , CUST6601 , 6100 , active , full ",
            "INV6602,CUST6602,7200,ACTIVE,ext",
        ],
        [
            "INV6601,CUST6601, 6100 ,FULL",
            " INV6602 , CUST6602 ,7200, EXT ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["attendance_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["child_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["care_type"] for row in rows] == ["FULL", "EXT"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_legacy_care_type_aliases_match_and_emit_canonical_care_types():
    """Legacy HF, FD, and EX credit care_types should match and report canonical care_types."""
    write_inputs(
        [
            "INV7701,CUST7701,8800,ACTIVE,FULL",
            "INV7702,CUST7702,9100,active,ext",
            "INV7703,CUST7703,4200,ACTIVE,HALF",
            "INV7704,CUST7704,5500,ACTIVE,HALF",
            "INV7705,CUST7705,3300,ACTIVE,CHECK",
        ],
        [
            "INV7701,CUST7701,8800,fd",
            "INV7702,CUST7702,9100,EX",
            "INV7703,CUST7703,4200,hf",
            "INV7704,CUST7704,5500,HF",
            "INV7705,CUST7705,3300,chk",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["care_type"] for row in rows] == ["FULL", "EXT", "HALF", "HALF", ""]
    assert summary["matched_count"] == 4
    assert summary["matched_amount_cents"] == 27600
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 3300


def test_hf_alias_matches_half_attendance_and_reports_canonical_care_type():
    """A HF credit must match a HALF attendance and emit HALF as the care_type."""
    write_inputs(
        ["INV7801,CUST7801,1234,ACTIVE,HALF"],
        ["INV7801,CUST7801,1234,hf"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["care_type"] == "HALF"
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 1234,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_report_schema_and_credit_input_order_are_stable():
    """The report should use the required schema and preserve credit input order."""
    write_inputs(
        [
            "INV9001,CUST9001,100,ACTIVE,HALF",
            "INV9002,CUST9002,200,ACTIVE,FULL",
            "INV9003,CUST9003,300,ACTIVE,EXT",
        ],
        [
            "INV9003,CUST9003,300,EXT",
            "INV9001,CUST9001,100,HALF",
            "INV9002,CUST9002,200,FULL",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "attendance_id,child_id,care_type,amount_cents,status"
    assert [row["attendance_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }

def test_posted_and_blank_source_statuses_do_not_match():
    """Only ACTIVE source rows are eligible; POSTED or blank status rows must stay unmatched."""
    write_inputs(
        [
            "STATPOST1,CUSTSTAT1,1100,POSTED,HALF",
            "STATBLANK1,CUSTSTAT2,1200,,HALF",
        ],
        [
            "STATPOST1,CUSTSTAT1,1100,HALF",
            "STATBLANK1,CUSTSTAT2,1200,HALF",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
    assert [row["care_type"] for row in rows] == ["", ""]
    assert summary["matched_count"] == 0
    assert summary["unmatched_count"] == 2
    assert summary["unmatched_amount_cents"] == 2300

def test_unmatched_report_fields_are_trimmed():
    """Unmatched report rows should still trim incidental spaces from action fields."""
    write_inputs(
        ["TRIMSRC1,CUSTSRC1,1900,ACTIVE,HALF"],
        [" TRIMACT1 , CUSTTRIM1 , 1700 , HALF "],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["attendance_id"] == "TRIMACT1"
    assert rows[0]["child_id"] == "CUSTTRIM1"
    assert rows[0]["amount_cents"] == "1700"
    assert rows[0]["care_type"] == ""
    assert summary["unmatched_amount_cents"] == 1700
