"""Verifier tests for the appointment credit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
APPOINTMENTS = APP / "data" / "appointments.csv"
CREDITS = APP / "data" / "credits.csv"
REPORT = APP / "out" / "copay_credit_report.csv"
SUMMARY = APP / "out" / "copay_credit_summary.json"
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


def write_inputs(appointment_rows, credit_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    APPOINTMENTS.write_text("appointment_id,patient_id,amount_cents,status,service_type\n" + "\n".join(appointment_rows) + "\n")
    CREDITS.write_text("appointment_id,patient_id,amount_cents,service_type\n" + "\n".join(credit_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_xray_credit_matches_and_counts_positive_amount():
    """XRAY credits should match active appointments and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,ACTIVE,CLEAN",
            "INV20260401002,CUST1002,9900,ACTIVE,XRAY",
        ],
        [
            "INV20260401001,CUST1001,12500,CLEAN",
            "INV20260401002,CUST1002,9900,XRAY",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["service_type"] == "XRAY"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_appointment_id_match_uses_full_identifier():
    """A credit must not match a appointment that only shares the leading appointment prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,ACTIVE,CLEAN",
            "INV777770002,CUST2001,3300,ACTIVE,CLEAN",
        ],
        [
            "INV777770003,CUST2001,3300,CLEAN",
            "INV777770002,CUST2001,3300,CLEAN",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["service_type"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_service_type_all_gate_matching():
    """Customer, amount, active status, and allowed service_type must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,1000,ACTIVE,CLEAN",
            "INV3002,CUST3002,2000,ACTIVE,XRAY",
            "INV3003,CUST3003,3000,DRAFT,SURG",
            "INV3004,CUST3004,4000,ACTIVE,CHECK",
            "INV3005,CUST3005,5000,ACTIVE,SURG",
        ],
        [
            "INV3001,CUST9999,1000,CLEAN",
            "INV3002,CUST3002,2100,XRAY",
            "INV3003,CUST3003,3000,SURG",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,SURG",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["service_type"] == "SURG"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_credits_do_not_reuse_consumed_appointment():
    """Only the earliest eligible credit may consume a matching appointment."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,ACTIVE,XRAY",
            "INV5552,CUST5552,8800,ACTIVE,CLEAN",
        ],
        [
            "INV5551,CUST5551,7500,XRAY",
            "INV5551,CUST5551,7500,XRAY",
            "INV5552,CUST5552,8800,CLEAN",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["service_type"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_service_type_status_case():
    """Matching should tolerate surrounding spaces and case differences in service_type/status values."""
    write_inputs(
        [
            " INV6601 , CUST6601 , 6100 , active , xray ",
            "INV6602,CUST6602,7200,ACTIVE,surg",
        ],
        [
            "INV6601,CUST6601, 6100 ,XRAY",
            " INV6602 , CUST6602 ,7200, SURG ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["appointment_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["patient_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["service_type"] for row in rows] == ["XRAY", "SURG"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_legacy_service_type_aliases_match_and_emit_canonical_service_types():
    """Legacy CL, XR, and SG credit service_types should match and report canonical service_types."""
    write_inputs(
        [
            "INV7701,CUST7701,8800,ACTIVE,XRAY",
            "INV7702,CUST7702,9100,active,surg",
            "INV7703,CUST7703,4200,ACTIVE,CLEAN",
            "INV7704,CUST7704,5500,ACTIVE,CLEAN",
            "INV7705,CUST7705,3300,ACTIVE,CHECK",
        ],
        [
            "INV7701,CUST7701,8800,xr",
            "INV7702,CUST7702,9100,SG",
            "INV7703,CUST7703,4200,cl",
            "INV7704,CUST7704,5500,CL",
            "INV7705,CUST7705,3300,chk",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["service_type"] for row in rows] == ["XRAY", "SURG", "CLEAN", "CLEAN", ""]
    assert summary["matched_count"] == 4
    assert summary["matched_amount_cents"] == 27600
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 3300


def test_cl_alias_matches_clean_appointment_and_reports_canonical_service_type():
    """A CL credit must match a CLEAN appointment and emit CLEAN as the service_type."""
    write_inputs(
        ["INV7801,CUST7801,1234,ACTIVE,CLEAN"],
        ["INV7801,CUST7801,1234,cl"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["service_type"] == "CLEAN"
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
            "INV9001,CUST9001,100,ACTIVE,CLEAN",
            "INV9002,CUST9002,200,ACTIVE,XRAY",
            "INV9003,CUST9003,300,ACTIVE,SURG",
        ],
        [
            "INV9003,CUST9003,300,SURG",
            "INV9001,CUST9001,100,CLEAN",
            "INV9002,CUST9002,200,XRAY",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "appointment_id,patient_id,service_type,amount_cents,status"
    assert [row["appointment_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
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
            "STATPOST1,CUSTSTAT1,1100,POSTED,CLEAN",
            "STATBLANK1,CUSTSTAT2,1200,,CLEAN",
        ],
        [
            "STATPOST1,CUSTSTAT1,1100,CLEAN",
            "STATBLANK1,CUSTSTAT2,1200,CLEAN",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
    assert [row["service_type"] for row in rows] == ["", ""]
    assert summary["matched_count"] == 0
    assert summary["unmatched_count"] == 2
    assert summary["unmatched_amount_cents"] == 2300

def test_unmatched_report_fields_are_trimmed():
    """Unmatched report rows should still trim incidental spaces from action fields."""
    write_inputs(
        ["TRIMSRC1,CUSTSRC1,1900,ACTIVE,CLEAN"],
        [" TRIMACT1 , CUSTTRIM1 , 1700 , CLEAN "],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["appointment_id"] == "TRIMACT1"
    assert rows[0]["patient_id"] == "CUSTTRIM1"
    assert rows[0]["amount_cents"] == "1700"
    assert rows[0]["service_type"] == ""
    assert summary["unmatched_amount_cents"] == 1700
