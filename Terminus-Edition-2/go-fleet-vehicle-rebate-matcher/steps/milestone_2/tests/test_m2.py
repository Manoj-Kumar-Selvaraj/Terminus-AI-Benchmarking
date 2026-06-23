"""Verifier tests for the fleet vehicle rebate matching CLI CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
VEHOICES = APP / "data" / "vehicles.csv"
PAYMENTS = APP / "data" / "rebates.csv"
REPORT = APP / "out" / "rebate_report.csv"
SUMMARY = APP / "out" / "rebate_summary.json"
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


def write_inputs(vehicle_rows, rebate_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    VEHOICES.write_text("vehicle_id,customer_id,amount_cents,status,channel\n" + "\n".join(vehicle_rows) + "\n")
    PAYMENTS.write_text("vehicle_id,customer_id,amount_cents,channel\n" + "\n".join(rebate_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_card_rebate_matches_and_counts_positive_amount():
    """CARD rebates should match posted vehicles and add positive cents to matched totals."""
    write_inputs(
        [
            "VEH20260401001,CUST1001,12500,POSTED,ACH",
            "VEH20260401002,CUST1002,9900,POSTED,CARD",
        ],
        [
            "VEH20260401001,CUST1001,12500,ACH",
            "VEH20260401002,CUST1002,9900,CARD",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["channel"] == "CARD"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_vehicle_id_match_uses_full_identifier():
    """A rebate must not match a vehicle that only shares the leading vehicle prefix."""
    write_inputs(
        [
            "VEH777770001,CUST2001,3300,POSTED,ACH",
            "VEH777770002,CUST2001,3300,POSTED,ACH",
        ],
        [
            "VEH777770003,CUST2001,3300,ACH",
            "VEH777770002,CUST2001,3300,ACH",
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
            "VEH3001,CUST3001,1000,POSTED,ACH",
            "VEH3002,CUST3002,2000,POSTED,CARD",
            "VEH3003,CUST3003,3000,DRAFT,WIRE",
            "VEH3004,CUST3004,4000,POSTED,CHECK",
            "VEH3005,CUST3005,5000,POSTED,WIRE",
        ],
        [
            "VEH3001,CUST9999,1000,ACH",
            "VEH3002,CUST3002,2100,CARD",
            "VEH3003,CUST3003,3000,WIRE",
            "VEH3004,CUST3004,4000,CHECK",
            "VEH3005,CUST3005,5000,WIRE",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["channel"] == "WIRE"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_rebates_do_not_reuse_consumed_vehicle():
    """Only the earliest eligible rebate may consume a matching vehicle."""
    write_inputs(
        [
            "VEH5551,CUST5551,7500,POSTED,CARD",
            "VEH5552,CUST5552,8800,POSTED,ACH",
        ],
        [
            "VEH5551,CUST5551,7500,CARD",
            "VEH5551,CUST5551,7500,CARD",
            "VEH5552,CUST5552,8800,ACH",
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
            " VEH6601 , CUST6601 , 6100 , posted , card ",
            "VEH6602,CUST6602,7200,POSTED,wire",
        ],
        [
            "VEH6601,CUST6601, 6100 ,CARD",
            " VEH6602 , CUST6602 ,7200, WIRE ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["vehicle_id"] for row in rows] == ["VEH6601", "VEH6602"]
    assert [row["customer_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["channel"] for row in rows] == ["CARD", "WIRE"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_legacy_channel_aliases_match_and_emit_canonical_channels():
    """Legacy CC and WIR rebate channels should match as CARD and WIRE and report canonical channels."""
    write_inputs(
        [
            "VEH7701,CUST7701,8800,POSTED,CARD",
            "VEH7702,CUST7702,9100,posted,wire",
            "VEH7703,CUST7703,4200,POSTED,ACH",
            "VEH7704,CUST7704,3300,POSTED,CHECK",
        ],
        [
            "VEH7701,CUST7701,8800,cc",
            "VEH7702,CUST7702,9100,WIR",
            "VEH7703,CUST7703,4200,ach",
            "VEH7704,CUST7704,3300,chk",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["channel"] for row in rows] == ["CARD", "WIRE", "ACH", ""]
    assert summary["matched_count"] == 3
    assert summary["matched_amount_cents"] == 22100
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 3300


def test_report_schema_and_rebate_input_order_are_stable():
    """The report should use the required schema and preserve rebate input order."""
    write_inputs(
        [
            "VEH9001,CUST9001,100,POSTED,ACH",
            "VEH9002,CUST9002,200,POSTED,CARD",
            "VEH9003,CUST9003,300,POSTED,WIRE",
        ],
        [
            "VEH9003,CUST9003,300,WIRE",
            "VEH9001,CUST9001,100,ACH",
            "VEH9002,CUST9002,200,CARD",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "vehicle_id,customer_id,channel,amount_cents,status"
    assert [row["vehicle_id"] for row in rows] == ["VEH9003", "VEH9001", "VEH9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
