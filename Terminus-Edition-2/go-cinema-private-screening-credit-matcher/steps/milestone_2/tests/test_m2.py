"""Verifier tests for the screening credit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
SCREENINGS = APP / "data" / "screenings.csv"
CREDITS = APP / "data" / "credits.csv"
REPORT = APP / "out" / "screening_credit_report.csv"
SUMMARY = APP / "out" / "screening_credit_summary.json"
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


def write_inputs(screening_rows, credit_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SCREENINGS.write_text("screening_id,host_id,amount_cents,status,screen_type\n" + "\n".join(screening_rows) + "\n")
    CREDITS.write_text("screening_id,host_id,amount_cents,screen_type\n" + "\n".join(credit_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_prem_credit_matches_and_counts_positive_amount():
    """PREM credits should match active screenings and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,ACTIVE,SMALL",
            "INV20260401002,CUST1002,9900,ACTIVE,PREM",
        ],
        [
            "INV20260401001,CUST1001,12500,SMALL",
            "INV20260401002,CUST1002,9900,PREM",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["screen_type"] == "PREM"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_screening_id_match_uses_full_identifier():
    """A credit must not match a screening that only shares the leading screening prefix."""
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
    assert rows[0]["screen_type"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_screen_type_all_gate_matching():
    """Customer, amount, active status, and allowed screen_type must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,1000,ACTIVE,SMALL",
            "INV3002,CUST3002,2000,ACTIVE,PREM",
            "INV3003,CUST3003,3000,DRAFT,IMAX",
            "INV3004,CUST3004,4000,ACTIVE,CHECK",
            "INV3005,CUST3005,5000,ACTIVE,IMAX",
        ],
        [
            "INV3001,CUST9999,1000,SMALL",
            "INV3002,CUST3002,2100,PREM",
            "INV3003,CUST3003,3000,IMAX",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,IMAX",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["screen_type"] == "IMAX"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_credits_do_not_reuse_consumed_screening():
    """Only the earliest eligible credit may consume a matching screening."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,ACTIVE,PREM",
            "INV5552,CUST5552,8800,ACTIVE,SMALL",
        ],
        [
            "INV5551,CUST5551,7500,PREM",
            "INV5551,CUST5551,7500,PREM",
            "INV5552,CUST5552,8800,SMALL",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["screen_type"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_screen_type_status_case():
    """Matching should tolerate surrounding spaces and case differences in screen_type/status values."""
    write_inputs(
        [
            " INV6601 , CUST6601 , 6100 , active , prem ",
            "INV6602,CUST6602,7200,ACTIVE,imax",
        ],
        [
            "INV6601,CUST6601, 6100 ,PREM",
            " INV6602 , CUST6602 ,7200, IMAX ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["screening_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["host_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["screen_type"] for row in rows] == ["PREM", "IMAX"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_legacy_screen_type_aliases_match_and_emit_canonical_screen_types():
    """Legacy SM, PM, and IX credit screen_types should match and report canonical screen_types."""
    write_inputs(
        [
            "INV7701,CUST7701,8800,ACTIVE,PREM",
            "INV7702,CUST7702,9100,active,imax",
            "INV7703,CUST7703,4200,ACTIVE,SMALL",
            "INV7704,CUST7704,5500,ACTIVE,SMALL",
            "INV7705,CUST7705,3300,ACTIVE,CHECK",
        ],
        [
            "INV7701,CUST7701,8800,pm",
            "INV7702,CUST7702,9100,IX",
            "INV7703,CUST7703,4200,sm",
            "INV7704,CUST7704,5500,SM",
            "INV7705,CUST7705,3300,chk",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["screen_type"] for row in rows] == ["PREM", "IMAX", "SMALL", "SMALL", ""]
    assert summary["matched_count"] == 4
    assert summary["matched_amount_cents"] == 27600
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 3300


def test_sm_alias_matches_small_screening_and_reports_canonical_screen_type():
    """A SM credit must match a SMALL screening and emit SMALL as the screen_type."""
    write_inputs(
        ["INV7801,CUST7801,1234,ACTIVE,SMALL"],
        ["INV7801,CUST7801,1234,sm"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["screen_type"] == "SMALL"
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
            "INV9001,CUST9001,100,ACTIVE,SMALL",
            "INV9002,CUST9002,200,ACTIVE,PREM",
            "INV9003,CUST9003,300,ACTIVE,IMAX",
        ],
        [
            "INV9003,CUST9003,300,IMAX",
            "INV9001,CUST9001,100,SMALL",
            "INV9002,CUST9002,200,PREM",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "screening_id,host_id,screen_type,amount_cents,status"
    assert [row["screening_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
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
            "STATPOST1,CUSTSTAT1,1100,POSTED,SMALL",
            "STATBLANK1,CUSTSTAT2,1200,,SMALL",
        ],
        [
            "STATPOST1,CUSTSTAT1,1100,SMALL",
            "STATBLANK1,CUSTSTAT2,1200,SMALL",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
    assert [row["screen_type"] for row in rows] == ["", ""]
    assert summary["matched_count"] == 0
    assert summary["unmatched_count"] == 2
    assert summary["unmatched_amount_cents"] == 2300

def test_unmatched_report_fields_are_trimmed():
    """Unmatched report rows should still trim incidental spaces from action fields."""
    write_inputs(
        ["TRIMSRC1,CUSTSRC1,1900,ACTIVE,SMALL"],
        [" TRIMACT1 , CUSTTRIM1 , 1700 , SMALL "],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["screening_id"] == "TRIMACT1"
    assert rows[0]["host_id"] == "CUSTTRIM1"
    assert rows[0]["amount_cents"] == "1700"
    assert rows[0]["screen_type"] == ""
    assert summary["unmatched_amount_cents"] == 1700
