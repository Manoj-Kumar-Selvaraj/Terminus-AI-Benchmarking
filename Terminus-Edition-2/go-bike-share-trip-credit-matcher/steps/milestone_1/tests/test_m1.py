"""Verifier tests for the trip credit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "trips.csv"
PAYMENTS = APP / "data" / "credits.csv"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"
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


def write_inputs(bill_rows, credit_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    INVOICES.write_text(
        "trip_id,rider_id,station_id,amount_cents,status,pass_type\n"
        + "\n".join(bill_rows)
        + "\n"
    )
    PAYMENTS.write_text(
        "trip_id,rider_id,station_id,amount_cents,pass_type\n"
        + "\n".join(credit_rows)
        + "\n"
    )
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone1:
    """Behavior checks for milestone 1."""

    def test_month_credit_matches_and_counts_positive_amount(self):
        """MONTH credits should match completed trips and add positive cents to matched totals."""
        write_inputs(
            [
                "INV20260401001,CUST1001,ST-01,12500,COMPLETED,DAY",
                "INV20260401002,CUST1002,ST-02,9900,COMPLETED,MONTH",
            ],
            [
                "INV20260401001,CUST1001,ST-01,12500,DAY",
                "INV20260401002,CUST1002,ST-02,9900,MONTH",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["pass_type"] == "MONTH"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 22400
        assert summary["unmatched_count"] == 0

    def test_trip_id_match_uses_full_identifier(self):
        """A credit must not match a trip that only shares the leading trip prefix."""
        write_inputs(
            [
                "INV777770001,CUST2001,ST-01,3300,COMPLETED,DAY",
                "INV777770002,CUST2001,ST-01,3300,COMPLETED,DAY",
            ],
            [
                "INV777770003,CUST2001,ST-01,3300,DAY",
                "INV777770002,CUST2001,ST-01,3300,DAY",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["pass_type"] == ""
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300

    def test_customer_station_amount_status_and_pass_type_all_gate_matching(self):
        """Customer, station, amount, completed status, and allowed pass_type must all be satisfied."""
        write_inputs(
            [
                "INV3001,CUST3001,ST-01,1000,COMPLETED,DAY",
                "INV3002,CUST3002,ST-02,2000,COMPLETED,MONTH",
                "INV3003,CUST3003,ST-03,3000,DRAFT,ANNUAL",
                "INV3004,CUST3004,ST-04,4000,COMPLETED,CHECK",
                "INV3005,CUST3005,ST-05,5000,COMPLETED,ANNUAL",
                "INV3006,CUST3006,ST-06,6000,COMPLETED,DAY",
            ],
            [
                "INV3001,CUST9999,ST-99,1000,DAY",
                "INV3002,CUST3002,ST-02,2100,MONTH",
                "INV3003,CUST3003,ST-03,3000,ANNUAL",
                "INV3004,CUST3004,ST-04,4000,CHECK",
                "INV3005,CUST3005,ST-05,5000,ANNUAL",
                "INV3006,CUST3006,ST-X,6000,DAY",
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
        assert rows[-2]["pass_type"] == "ANNUAL"
        assert rows[-1]["pass_type"] == ""
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_count"] == 5
        assert summary["unmatched_amount_cents"] == 16100

    def test_duplicate_credits_do_not_reuse_consumed_record(self):
        """Only the earliest eligible credit may consume a matching trip."""
        write_inputs(
            [
                "INV5551,CUST5551,ST-51,7500,COMPLETED,MONTH",
                "INV5552,CUST5552,ST-52,8800,COMPLETED,DAY",
            ],
            [
                "INV5551,CUST5551,ST-51,7500,MONTH",
                "INV5551,CUST5551,ST-51,7500,MONTH",
                "INV5552,CUST5552,ST-52,8800,DAY",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["pass_type"] == ""
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 16300
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 7500

    def test_matching_trims_fields_and_normalizes_pass_type_status_case(self):
        """Matching should tolerate surrounding spaces and case differences in pass_type/status values."""
        write_inputs(
            [
                " INV6601 , CUST6601 ,ST-01, 6100 , completed , month ",
                "INV6602,CUST6602,ST-02,7200,COMPLETED,annual",
            ],
            [
                "INV6601,CUST6601,ST-01, 6100 ,MONTH",
                " INV6602 , CUST6602 ,ST-02,7200, ANNUAL ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["trip_id"] for row in rows] == ["INV6601", "INV6602"]
        assert [row["rider_id"] for row in rows] == ["CUST6601", "CUST6602"]
        assert [row["pass_type"] for row in rows] == ["MONTH", "ANNUAL"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 13300

    def test_report_schema_and_credit_input_order_are_stable(self):
        """The report should use the required schema and preserve credit input order."""
        write_inputs(
            [
                "INV9001,CUST9001,ST-01,100,COMPLETED,DAY",
                "INV9002,CUST9002,ST-02,200,COMPLETED,MONTH",
                "INV9003,CUST9003,ST-03,300,COMPLETED,ANNUAL",
            ],
            [
                "INV9003,CUST9003,ST-03,300,ANNUAL",
                "INV9001,CUST9001,ST-01,100,DAY",
                "INV9002,CUST9002,ST-02,200,MONTH",
            ],
        )
        rows, summary = run_program()

        assert (
            REPORT.read_text().splitlines()[0]
            == "trip_id,rider_id,pass_type,amount_cents,status"
        )
        assert [row["trip_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
        assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
