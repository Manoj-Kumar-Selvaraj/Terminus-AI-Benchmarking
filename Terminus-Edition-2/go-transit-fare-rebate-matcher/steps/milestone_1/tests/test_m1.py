"""Verifier tests for the trip rebate reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "trips.csv"
PAYMENTS = APP / "data" / "rebates.csv"
REPORT = APP / "out" / "rebate_report.csv"
SUMMARY = APP / "out" / "rebate_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go reconciliation CLI for the current source tree."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run(
        [go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"],
        check=True,
        cwd=APP,
        timeout=60,
    )


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all verifier tests."""
    build_program()


def write_inputs(bill_rows, refund_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    INVOICES.write_text(
        "trip_id,rider_id,route_id,amount_cents,status,mode\n"
        + "\n".join(bill_rows)
        + "\n"
    )
    PAYMENTS.write_text(
        "trip_id,rider_id,route_id,amount_cents,mode\n" + "\n".join(refund_rows) + "\n"
    )
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_rail_refund_matches_and_counts_positive_amount():
    """RAIL rebates should match tapped trips and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,RT-01,12500,TAPPED,BUS",
            "INV20260401002,CUST1002,RT-02,9900,TAPPED,RAIL",
        ],
        [
            "INV20260401001,CUST1001,RT-01,12500,BUS",
            "INV20260401002,CUST1002,RT-02,9900,RAIL",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["mode"] == "RAIL"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_trip_id_match_uses_full_identifier():
    """A rebate must not match a trip that only shares the leading trip prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,RT-01,3300,TAPPED,BUS",
            "INV777770002,CUST2001,RT-01,3300,TAPPED,BUS",
        ],
        [
            "INV777770003,CUST2001,RT-01,3300,BUS",
            "INV777770002,CUST2001,RT-01,3300,BUS",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["mode"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_route_amount_status_and_mode_all_gate_matching():
    """Customer, route, amount, tapped status, and allowed mode must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,RT-01,1000,TAPPED,BUS",
            "INV3002,CUST3002,RT-02,2000,TAPPED,RAIL",
            "INV3003,CUST3003,RT-03,3000,DRAFT,FERRY",
            "INV3004,CUST3004,RT-04,4000,TAPPED,CHECK",
            "INV3005,CUST3005,RT-05,5000,TAPPED,FERRY",
            "INV3006,CUST3006,RT-06,6000,TAPPED,BUS",
        ],
        [
            "INV3001,CUST9999,RT-99,1000,BUS",
            "INV3002,CUST3002,RT-02,2100,RAIL",
            "INV3003,CUST3003,RT-03,3000,FERRY",
            "INV3004,CUST3004,RT-04,4000,CHECK",
            "INV3005,CUST3005,RT-05,5000,FERRY",
            "INV3006,CUST3006,RT-X,6000,BUS",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == [
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "MATCHED",
        "UNMATCHED",
    ]
    assert rows[4]["mode"] == "FERRY"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 5
    assert summary["unmatched_amount_cents"] == 16100


def test_duplicate_refunds_do_not_reuse_consumed_bill():
    """Only the earliest eligible rebate may consume a matching trip."""
    write_inputs(
        [
            "INV5551,CUST5551,RT-51,7500,TAPPED,RAIL",
            "INV5552,CUST5552,RT-52,8800,TAPPED,BUS",
        ],
        [
            "INV5551,CUST5551,RT-51,7500,RAIL",
            "INV5551,CUST5551,RT-51,7500,RAIL",
            "INV5552,CUST5552,RT-52,8800,BUS",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["mode"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_mode_status_case():
    """Matching should tolerate surrounding spaces and case differences in mode/status values."""
    write_inputs(
        [
            " INV6601 , CUST6601 ,RT-01, 6100 , tapped , rail ",
            "INV6602,CUST6602,RT-02,7200,TAPPED,ferry",
        ],
        [
            "INV6601,CUST6601,RT-01, 6100 ,RAIL",
            " INV6602 , CUST6602 ,RT-02,7200, FERRY ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["trip_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["rider_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["mode"] for row in rows] == ["RAIL", "FERRY"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_report_schema_and_refund_input_order_are_stable():
    """The report should use the required schema and preserve rebate input order."""
    write_inputs(
        [
            "INV9001,CUST9001,RT-01,100,TAPPED,BUS",
            "INV9002,CUST9002,RT-02,200,TAPPED,RAIL",
            "INV9003,CUST9003,RT-03,300,TAPPED,FERRY",
        ],
        [
            "INV9003,CUST9003,RT-03,300,FERRY",
            "INV9001,CUST9001,RT-01,100,BUS",
            "INV9002,CUST9002,RT-02,200,RAIL",
        ],
    )
    rows, summary = run_program()

    assert (
        REPORT.read_text().splitlines()[0]
        == "trip_id,rider_id,mode,amount_cents,status"
    )
    assert [row["trip_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
