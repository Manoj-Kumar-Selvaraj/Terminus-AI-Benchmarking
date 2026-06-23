"""Verifier tests for the session rebate reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
SESSIONS = APP / "data" / "sessions.csv"
ACTIONS = APP / "data" / "rebates.csv"
REPORT = APP / "out" / "session_rebate_report.csv"
SUMMARY = APP / "out" / "session_rebate_summary.json"
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


def write_inputs(session_rows, rebate_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SESSIONS.write_text("session_id,client_id,amount_cents,status,training_type\n" + "\n".join(session_rows) + "\n")
    CREDITS.write_text("session_id,client_id,amount_cents,training_type\n" + "\n".join(rebate_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_duo_rebate_matches_and_counts_positive_amount():
    """DUO rebates should match active sessions and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,ACTIVE,SOLO",
            "INV20260401002,CUST1002,9900,ACTIVE,DUO",
        ],
        [
            "INV20260401001,CUST1001,12500,SOLO",
            "INV20260401002,CUST1002,9900,DUO",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["training_type"] == "DUO"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_session_id_match_uses_full_identifier():
    """A rebate must not match a session that only shares the leading session prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,ACTIVE,SOLO",
            "INV777770002,CUST2001,3300,ACTIVE,SOLO",
        ],
        [
            "INV777770003,CUST2001,3300,SOLO",
            "INV777770002,CUST2001,3300,SOLO",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["training_type"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_training_type_all_gate_matching():
    """Customer, amount, active status, and allowed training_type must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,1000,ACTIVE,SOLO",
            "INV3002,CUST3002,2000,ACTIVE,DUO",
            "INV3003,CUST3003,3000,DRAFT,TEAM",
            "INV3004,CUST3004,4000,ACTIVE,CHECK",
            "INV3005,CUST3005,5000,ACTIVE,TEAM",
        ],
        [
            "INV3001,CUST9999,1000,SOLO",
            "INV3002,CUST3002,2100,DUO",
            "INV3003,CUST3003,3000,TEAM",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,TEAM",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["training_type"] == "TEAM"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_rebates_do_not_reuse_consumed_session():
    """Only the earliest eligible rebate may consume a matching session."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,ACTIVE,DUO",
            "INV5552,CUST5552,8800,ACTIVE,SOLO",
        ],
        [
            "INV5551,CUST5551,7500,DUO",
            "INV5551,CUST5551,7500,DUO",
            "INV5552,CUST5552,8800,SOLO",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["training_type"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_training_type_status_case():
    """Matching should tolerate surrounding spaces and case differences in training_type/status values."""
    write_inputs(
        [
            " INV6601 , CUST6601 , 6100 , active , duo ",
            "INV6602,CUST6602,7200,ACTIVE,team",
        ],
        [
            "INV6601,CUST6601, 6100 ,DUO",
            " INV6602 , CUST6602 ,7200, TEAM ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["session_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["client_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["training_type"] for row in rows] == ["DUO", "TEAM"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_report_schema_and_rebate_input_order_are_stable():
    """The report should use the required schema and preserve rebate input order."""
    write_inputs(
        [
            "INV9001,CUST9001,100,ACTIVE,SOLO",
            "INV9002,CUST9002,200,ACTIVE,DUO",
            "INV9003,CUST9003,300,ACTIVE,TEAM",
        ],
        [
            "INV9003,CUST9003,300,TEAM",
            "INV9001,CUST9001,100,SOLO",
            "INV9002,CUST9002,200,DUO",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "session_id,client_id,training_type,amount_cents,status"
    assert [row["session_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
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
            "STATPOST1,CUSTSTAT1,1100,POSTED,SOLO",
            "STATBLANK1,CUSTSTAT2,1200,,SOLO",
        ],
        [
            "STATPOST1,CUSTSTAT1,1100,SOLO",
            "STATBLANK1,CUSTSTAT2,1200,SOLO",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
    assert [row["training_type"] for row in rows] == ["", ""]
    assert summary["matched_count"] == 0
    assert summary["unmatched_count"] == 2
    assert summary["unmatched_amount_cents"] == 2300

def test_unmatched_report_fields_are_trimmed():
    """Unmatched report rows should still trim incidental spaces from action fields."""
    write_inputs(
        ["TRIMSRC1,CUSTSRC1,1900,ACTIVE,SOLO"],
        [" TRIMACT1 , CUSTTRIM1 , 1700 , SOLO "],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["session_id"] == "TRIMACT1"
    assert rows[0]["client_id"] == "CUSTTRIM1"
    assert rows[0]["amount_cents"] == "1700"
    assert rows[0]["training_type"] == ""
    assert summary["unmatched_amount_cents"] == 1700
