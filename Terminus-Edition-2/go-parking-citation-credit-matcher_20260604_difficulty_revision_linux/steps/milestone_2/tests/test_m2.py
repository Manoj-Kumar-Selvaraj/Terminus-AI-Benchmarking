"""Verifier tests for the citation credit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "citations.csv"
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


def write_inputs(bill_rows, refund_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    INVOICES.write_text("citation_id,plate_id,amount_cents,status,zone\n" + "\n".join(bill_rows) + "\n")
    PAYMENTS.write_text("citation_id,plate_id,amount_cents,zone\n" + "\n".join(refund_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone2:
    """Behavior checks for milestone 2."""

    def test_garage_refund_matches_and_counts_positive_amount(self):
        """GARAGE credits should match paid citations and add positive cents to matched totals."""
        write_inputs(
            [
                "INV20260401001,CUST1001,12500,PAID,STREET",
                "INV20260401002,CUST1002,9900,PAID,GARAGE",
            ],
            [
                "INV20260401001,CUST1001,12500,STREET",
                "INV20260401002,CUST1002,9900,GARAGE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["zone"] == "GARAGE"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 22400
        assert summary["unmatched_count"] == 0

    def test_citation_id_match_uses_full_identifier(self):
        """A credit must not match a citation that only shares the leading citation prefix."""
        write_inputs(
            [
                "INV777770001,CUST2001,3300,PAID,STREET",
                "INV777770002,CUST2001,3300,PAID,STREET",
            ],
            [
                "INV777770003,CUST2001,3300,STREET",
                "INV777770002,CUST2001,3300,STREET",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["zone"] == ""
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300

    def test_customer_amount_status_and_zone_all_gate_matching(self):
        """Customer, amount, paid status, and allowed zone must all be satisfied."""
        write_inputs(
            [
                "INV3001,CUST3001,1000,PAID,STREET",
                "INV3002,CUST3002,2000,PAID,GARAGE",
                "INV3003,CUST3003,3000,DRAFT,LOT",
                "INV3004,CUST3004,4000,PAID,CHECK",
                "INV3005,CUST3005,5000,PAID,LOT",
            ],
            [
                "INV3001,CUST9999,1000,STREET",
                "INV3002,CUST3002,2100,GARAGE",
                "INV3003,CUST3003,3000,LOT",
                "INV3004,CUST3004,4000,CHECK",
                "INV3005,CUST3005,5000,LOT",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["zone"] == "LOT"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_count"] == 4
        assert summary["unmatched_amount_cents"] == 10100

    def test_posted_status_does_not_match_even_with_alias(self):
        """POSTED citations must remain ineligible under alias-aware matching."""
        write_inputs(
            ["INV8001,CUST8001,5000,POSTED,STREET"],
            ["INV8001,CUST8001,5000,ST"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["zone"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 5000,
        }

    def test_duplicate_refunds_do_not_reuse_consumed_bill(self):
        """Only the earliest eligible credit may consume a matching citation."""
        write_inputs(
            [
                "INV5551,CUST5551,7500,PAID,GARAGE",
                "INV5552,CUST5552,8800,PAID,STREET",
            ],
            [
                "INV5551,CUST5551,7500,GARAGE",
                "INV5551,CUST5551,7500,GARAGE",
                "INV5552,CUST5552,8800,STREET",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["zone"] == ""
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 16300
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 7500

    def test_matching_trims_fields_and_normalizes_zone_status_case(self):
        """Matching should tolerate surrounding spaces and case differences in zone/status values."""
        write_inputs(
            [
                " INV6601 , CUST6601 , 6100 , paid , garage ",
                "INV6602,CUST6602,7200,PAID,lot",
            ],
            [
                "INV6601,CUST6601, 6100 ,GARAGE",
                " INV6602 , CUST6602 ,7200, LOT ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["citation_id"] for row in rows] == ["INV6601", "INV6602"]
        assert [row["plate_id"] for row in rows] == ["CUST6601", "CUST6602"]
        assert [row["zone"] for row in rows] == ["GARAGE", "LOT"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 13300

    def test_mismatched_zones_do_not_match_when_other_fields_align(self):
        """Citation and credit zones must be equal after canonicalization, not merely allowed."""
        write_inputs(
            ["INV8801,CUST8801,5000,PAID,STREET"],
            ["INV8801,CUST8801,5000,GARAGE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["zone"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 5000,
        }

    def test_legacy_zone_aliases_match_and_emit_canonical_zones(self):
        """Legacy ST, GRG, and LT credit zones should match and report canonical zones."""
        write_inputs(
            [
                "INV7701,CUST7701,8800,PAID,GARAGE",
                "INV7702,CUST7702,9100,paid,lot",
                "INV7703,CUST7703,4200,PAID,STREET",
                "INV7704,CUST7704,3300,PAID,CHECK",
            ],
            [
                "INV7701,CUST7701,8800,grg",
                "INV7702,CUST7702,9100,LT",
                "INV7703,CUST7703,4200,st",
                "INV7704,CUST7704,3300,chk",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["zone"] for row in rows] == ["GARAGE", "LOT", "STREET", ""]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 22100
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 3300

    def test_report_schema_and_refund_input_order_are_stable(self):
        """The report should use the required schema and preserve credit input order."""
        write_inputs(
            [
                "INV9001,CUST9001,100,PAID,STREET",
                "INV9002,CUST9002,200,PAID,GARAGE",
                "INV9003,CUST9003,300,PAID,LOT",
            ],
            [
                "INV9003,CUST9003,300,LOT",
                "INV9001,CUST9001,100,STREET",
                "INV9002,CUST9002,200,GARAGE",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "citation_id,plate_id,zone,amount_cents,status"
        assert [row["citation_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
        assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
