"""Verifier tests for the hotel reservation credit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
RSVS = APP / "data" / "reservations.csv"
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


def write_inputs(reservation_rows, credit_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    RSVS.write_text("reservation_id,customer_id,amount_cents,status,channel\n" + "\n".join(reservation_rows) + "\n")
    PAYMENTS.write_text("reservation_id,customer_id,amount_cents,channel\n" + "\n".join(credit_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_card_credit_matches_and_counts_positive_amount():
    """CARD credits should match posted reservations and add positive cents to matched totals."""
    write_inputs(
        [
            "RSV20260401001,CUST1001,12500,POSTED,ACH",
            "RSV20260401002,CUST1002,9900,POSTED,CARD",
        ],
        [
            "RSV20260401001,CUST1001,12500,ACH",
            "RSV20260401002,CUST1002,9900,CARD",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["channel"] == "CARD"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_reservation_id_match_uses_full_identifier():
    """A credit must not match a reservation that only shares the leading reservation prefix."""
    write_inputs(
        [
            "RSV777770001,CUST2001,3300,POSTED,ACH",
            "RSV777770002,CUST2001,3300,POSTED,ACH",
        ],
        [
            "RSV777770003,CUST2001,3300,ACH",
            "RSV777770002,CUST2001,3300,ACH",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["channel"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_channel_all_gate_matching():
    """Customer, amount, posted status, and allowed channel must all be satisfied."""
    write_inputs(
        [
            "RSV3001,CUST3001,1000,POSTED,ACH",
            "RSV3002,CUST3002,2000,POSTED,CARD",
            "RSV3003,CUST3003,3000,DRAFT,WIRE",
            "RSV3004,CUST3004,4000,POSTED,CHECK",
            "RSV3005,CUST3005,5000,POSTED,WIRE",
        ],
        [
            "RSV3001,CUST9999,1000,ACH",
            "RSV3002,CUST3002,2100,CARD",
            "RSV3003,CUST3003,3000,WIRE",
            "RSV3004,CUST3004,4000,CHECK",
            "RSV3005,CUST3005,5000,WIRE",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["channel"] == "WIRE"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_credits_do_not_reuse_consumed_reservation():
    """Only the earliest eligible credit may consume a matching reservation."""
    write_inputs(
        [
            "RSV5551,CUST5551,7500,POSTED,CARD",
            "RSV5552,CUST5552,8800,POSTED,ACH",
        ],
        [
            "RSV5551,CUST5551,7500,CARD",
            "RSV5551,CUST5551,7500,CARD",
            "RSV5552,CUST5552,8800,ACH",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["channel"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_channel_status_case():
    """Matching should tolerate surrounding spaces and case differences in channel/status values."""
    write_inputs(
        [
            " RSV6601 , CUST6601 , 6100 , posted , card ",
            "RSV6602,CUST6602,7200,POSTED,wire",
        ],
        [
            "RSV6601,CUST6601, 6100 ,CARD",
            " RSV6602 , CUST6602 ,7200, WIRE ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["reservation_id"] for row in rows] == ["RSV6601", "RSV6602"]
    assert [row["customer_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["channel"] for row in rows] == ["CARD", "WIRE"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_report_schema_and_credit_input_order_are_stable():
    """The report should use the required schema and preserve credit input order."""
    write_inputs(
        [
            "RSV9001,CUST9001,100,POSTED,ACH",
            "RSV9002,CUST9002,200,POSTED,CARD",
            "RSV9003,CUST9003,300,POSTED,WIRE",
        ],
        [
            "RSV9003,CUST9003,300,WIRE",
            "RSV9001,CUST9001,100,ACH",
            "RSV9002,CUST9002,200,CARD",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "reservation_id,customer_id,channel,amount_cents,status"
    assert [row["reservation_id"] for row in rows] == ["RSV9003", "RSV9001", "RSV9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_wire_credit_matches_and_summary_adds_positive_cents():
    """WIRE credits should match posted reservations and add positive cents to matched totals."""
    write_inputs(
        ["RSV8801,CUST8801,4400,POSTED,WIRE"],
        ["RSV8801,CUST8801,4400,WIRE"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["channel"] == "WIRE"
    assert summary["matched_amount_cents"] == 4400
    assert summary["unmatched_count"] == 0


def test_multiple_credits_targeting_same_reservation_only_first_matches():
    """Three credits targeting the same reservation: only the first consumes it."""
    write_inputs(
        ["RSV8901,CUST8901,1800,POSTED,ACH"],
        [
            "RSV8901,CUST8901,1800,ACH",
            "RSV8901,CUST8901,1800,ACH",
            "RSV8901,CUST8901,1800,ACH",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 1800
    assert summary["unmatched_count"] == 2
    assert summary["unmatched_amount_cents"] == 3600


def test_unmatched_credit_for_nonexistent_reservation_id():
    """A credit whose reservation id exists nowhere in reservations must be UNMATCHED."""
    write_inputs(
        ["RSV9991,CUST9991,500,POSTED,ACH"],
        ["RSV9999,CUST9991,500,ACH"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["channel"] == ""
    assert summary == {
        "matched_count": 0,
        "matched_amount_cents": 0,
        "unmatched_count": 1,
        "unmatched_amount_cents": 500,
    }
