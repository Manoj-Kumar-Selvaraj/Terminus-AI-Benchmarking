"""Verifier tests for the pass refund reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "passes.csv"
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
    INVOICES.write_text("pass_id,guest_id,amount_cents,status,access_type\n" + "\n".join(bill_rows) + "\n")
    PAYMENTS.write_text("pass_id,guest_id,amount_cents,access_type\n" + "\n".join(refund_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_season_refund_matches_and_counts_positive_amount():
    """SEASON refunds should match active passes and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,ACTIVE,DAY",
            "INV20260401002,CUST1002,9900,ACTIVE,SEASON",
        ],
        [
            "INV20260401001,CUST1001,12500,DAY",
            "INV20260401002,CUST1002,9900,SEASON",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["access_type"] == "SEASON"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_pass_id_match_uses_full_identifier():
    """A refund must not match a pass that only shares the leading pass prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,ACTIVE,DAY",
            "INV777770002,CUST2001,3300,ACTIVE,DAY",
        ],
        [
            "INV777770003,CUST2001,3300,DAY",
            "INV777770002,CUST2001,3300,DAY",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["access_type"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_access_type_all_gate_matching():
    """Customer, amount, active status, and allowed access_type must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,1000,ACTIVE,DAY",
            "INV3002,CUST3002,2000,ACTIVE,SEASON",
            "INV3003,CUST3003,3000,DRAFT,VIP",
            "INV3004,CUST3004,4000,ACTIVE,CHECK",
            "INV3005,CUST3005,5000,ACTIVE,VIP",
        ],
        [
            "INV3001,CUST9999,1000,DAY",
            "INV3002,CUST3002,2100,SEASON",
            "INV3003,CUST3003,3000,VIP",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,VIP",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["access_type"] == "VIP"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_refunds_do_not_reuse_consumed_bill():
    """Only the earliest eligible refund may consume a matching pass."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,ACTIVE,SEASON",
            "INV5552,CUST5552,8800,ACTIVE,DAY",
        ],
        [
            "INV5551,CUST5551,7500,SEASON",
            "INV5551,CUST5551,7500,SEASON",
            "INV5552,CUST5552,8800,DAY",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["access_type"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_access_type_status_case():
    """Matching should tolerate surrounding spaces and case differences in access_type/status values."""
    write_inputs(
        [
            " INV6601 , CUST6601 , 6100 , active , season ",
            "INV6602,CUST6602,7200,ACTIVE,vip",
        ],
        [
            "INV6601,CUST6601, 6100 ,SEASON",
            " INV6602 , CUST6602 ,7200, VIP ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["pass_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["guest_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["access_type"] for row in rows] == ["SEASON", "VIP"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_legacy_access_type_aliases_match_and_emit_canonical_access_types():
    """Legacy DY, SEA, and V refund access_types should match and report canonical access_types."""
    write_inputs(
        [
            "INV7701,CUST7701,8800,ACTIVE,SEASON",
            "INV7702,CUST7702,9100,active,vip",
            "INV7703,CUST7703,4200,ACTIVE,DAY",
            "INV7704,CUST7704,5500,ACTIVE,DAY",
            "INV7705,CUST7705,3300,ACTIVE,CHECK",
        ],
        [
            "INV7701,CUST7701,8800,sea",
            "INV7702,CUST7702,9100,V",
            "INV7703,CUST7703,4200,dy",
            "INV7704,CUST7704,5500,DY",
            "INV7705,CUST7705,3300,chk",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["access_type"] for row in rows] == ["SEASON", "VIP", "DAY", "DAY", ""]
    assert summary["matched_count"] == 4
    assert summary["matched_amount_cents"] == 27600
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 3300


def test_dy_alias_matches_day_pass_and_reports_canonical_access_type():
    """A DY refund must match a DAY pass and emit DAY as the access_type."""
    write_inputs(
        ["INV7801,CUST7801,1234,ACTIVE,DAY"],
        ["INV7801,CUST7801,1234,dy"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["access_type"] == "DAY"
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 1234,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_report_schema_and_refund_input_order_are_stable():
    """The report should use the required schema and preserve refund input order."""
    write_inputs(
        [
            "INV9001,CUST9001,100,ACTIVE,DAY",
            "INV9002,CUST9002,200,ACTIVE,SEASON",
            "INV9003,CUST9003,300,ACTIVE,VIP",
        ],
        [
            "INV9003,CUST9003,300,VIP",
            "INV9001,CUST9001,100,DAY",
            "INV9002,CUST9002,200,SEASON",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "pass_id,guest_id,access_type,amount_cents,status"
    assert [row["pass_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
