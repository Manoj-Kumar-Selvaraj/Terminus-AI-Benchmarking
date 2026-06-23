"""Verifier tests for the device warranty claim reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "devices.csv"
PAYMENTS = APP / "data" / "warranty_claims.csv"
REPORT = APP / "out" / "warranty_report.csv"
SUMMARY = APP / "out" / "warranty_summary.json"
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


def write_inputs(device_rows, claim_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    INVOICES.write_text("device_id,owner_id,amount_cents,status,reason\n" + "\n".join(device_rows) + "\n")
    PAYMENTS.write_text("device_id,owner_id,amount_cents,reason\n" + "\n".join(claim_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())



class TestMilestone2:
    """Milestone 2 legacy reason alias behavior."""

    def test_battery_claim_matches_and_counts_positive_amount(self):
        """BATTERY claims should match posted devices and add positive cents to matched totals."""
        write_inputs(
            [
                "INV20260401001,CUST1001,12500,POSTED,SCREEN",
                "INV20260401002,CUST1002,9900,POSTED,BATTERY",
            ],
            [
                "INV20260401001,CUST1001,12500,SCREEN",
                "INV20260401002,CUST1002,9900,BATTERY",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["reason"] == "BATTERY"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 22400
        assert summary["unmatched_count"] == 0


    def test_device_id_match_uses_full_identifier(self):
        """A claim must not match a device that only shares the leading device prefix."""
        write_inputs(
            [
                "INV777770001,CUST2001,3300,POSTED,SCREEN",
                "INV777770002,CUST2001,3300,POSTED,SCREEN",
            ],
            [
                "INV777770003,CUST2001,3300,SCREEN",
                "INV777770002,CUST2001,3300,SCREEN",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["reason"] == ""
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300


    def test_owner_amount_status_and_reason_all_gate_matching(self):
        """Owner, amount, posted status, and allowed reason must all be satisfied."""
        write_inputs(
            [
                "INV3001,CUST3001,1000,POSTED,SCREEN",
                "INV3002,CUST3002,2000,POSTED,BATTERY",
                "INV3003,CUST3003,3000,DRAFT,WATER",
                "INV3004,CUST3004,4000,POSTED,CHECK",
                "INV3005,CUST3005,5000,POSTED,WATER",
            ],
            [
                "INV3001,CUST9999,1000,SCREEN",
                "INV3002,CUST3002,2100,BATTERY",
                "INV3003,CUST3003,3000,WATER",
                "INV3004,CUST3004,4000,CHECK",
                "INV3005,CUST3005,5000,WATER",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["reason"] == "WATER"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_count"] == 4
        assert summary["unmatched_amount_cents"] == 10100


    def test_duplicate_claims_do_not_reuse_consumed_device(self):
        """Only the earliest eligible claim may consume a matching device."""
        write_inputs(
            [
                "INV5551,CUST5551,7500,POSTED,BATTERY",
                "INV5552,CUST5552,8800,POSTED,SCREEN",
            ],
            [
                "INV5551,CUST5551,7500,BATTERY",
                "INV5551,CUST5551,7500,BATTERY",
                "INV5552,CUST5552,8800,SCREEN",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["reason"] == ""
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 16300
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 7500


    def test_matching_trims_fields_and_normalizes_reason_status_case(self):
        """Matching should tolerate surrounding spaces and case differences in reason/status values."""
        write_inputs(
            [
                " INV6601 , CUST6601 , 6100 , posted , battery ",
                "INV6602,CUST6602,7200,POSTED,water",
            ],
            [
                "INV6601,CUST6601, 6100 ,BATTERY",
                " INV6602 , CUST6602 ,7200, WATER ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["device_id"] for row in rows] == ["INV6601", "INV6602"]
        assert [row["owner_id"] for row in rows] == ["CUST6601", "CUST6602"]
        assert [row["reason"] for row in rows] == ["BATTERY", "WATER"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 13300


    def test_unknown_reason_alias_stays_unmatched(self):
        """Unsupported alias-like reason tokens must stay unmatched."""
        write_inputs(
            [
                "INV8801,CUST8801,1200,POSTED,BATTERY",
            ],
            [
                "INV8801,CUST8801,1200,XYZ",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["reason"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 1200

    def test_alias_case_folding_and_trim_are_required(self):
        """Alias normalization must apply after trimming and case folding."""
        write_inputs(
            [
                "INV8901,CUST8901,1500,POSTED,BATTERY",
                "INV8902,CUST8902,1600,posted,water",
            ],
            [
                "INV8901,CUST8901,1500, bat ",
                "INV8902,CUST8902,1600, WTR ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["reason"] for row in rows] == ["BATTERY", "WATER"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 3100

    def test_legacy_reason_aliases_match_and_emit_canonical_reasons(self):
        """Legacy BAT and WTR claim reasons should match as BATTERY and WATER and report canonical reasons."""
        write_inputs(
            [
                "INV7701,CUST7701,8800,POSTED,BATTERY",
                "INV7702,CUST7702,9100,posted,water",
                "INV7703,CUST7703,4200,POSTED,SCREEN",
                "INV7704,CUST7704,3300,POSTED,CHECK",
            ],
            [
                "INV7701,CUST7701,8800,bat",
                "INV7702,CUST7702,9100,WTR",
                "INV7703,CUST7703,4200,screen",
                "INV7704,CUST7704,3300,check",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["reason"] for row in rows] == ["BATTERY", "WATER", "SCREEN", ""]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 22100
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 3300


    def test_report_schema_and_claim_input_order_are_stable(self):
        """The report should use the required schema and preserve claim input order."""
        write_inputs(
            [
                "INV9001,CUST9001,100,POSTED,SCREEN",
                "INV9002,CUST9002,200,POSTED,BATTERY",
                "INV9003,CUST9003,300,POSTED,WATER",
            ],
            [
                "INV9003,CUST9003,300,WATER",
                "INV9001,CUST9001,100,SCREEN",
                "INV9002,CUST9002,200,BATTERY",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "device_id,owner_id,reason,amount_cents,status"
        assert [row["device_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
        assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
