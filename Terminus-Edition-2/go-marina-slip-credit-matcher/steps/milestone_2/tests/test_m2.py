"""Milestone 2 verifier tests for legacy dock-zone aliases."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "slips.csv"
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
    INVOICES.write_text("slip_id,member_id,amount_cents,status,dock_zone\n" + "\n".join(bill_rows) + "\n")
    PAYMENTS.write_text("slip_id,member_id,amount_cents,dock_zone\n" + "\n".join(refund_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_legacy_dock_zone_aliases_match_and_emit_canonical_dock_zones():
    """NZ, SZ, and EZ credit dock_zone aliases should match and report canonical dock_zones."""
    write_inputs(
        [
            "INV7701,CUST7701,8800,DOCKED,SOUTH",
            "INV7702,CUST7702,9100,docked,east",
            "INV7703,CUST7703,4200,DOCKED,NORTH",
            "INV7704,CUST7704,3300,DOCKED,CHECK",
        ],
        [
            "INV7701,CUST7701,8800,sz",
            "INV7702,CUST7702,9100,EZ",
            "INV7703,CUST7703,4200,NZ",
            "INV7704,CUST7704,3300,chk",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["dock_zone"] for row in rows] == ["SOUTH", "EAST", "NORTH", ""]
    assert summary["matched_count"] == 3
    assert summary["matched_amount_cents"] == 22100
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 3300


def test_alias_step_preserves_schema_order_and_blank_unmatched_dock_zone():
    """The alias step should still preserve report schema, credit order, and blank unmatched dock_zone."""
    write_inputs(
        [
            "INV9001,CUST9001,100,DOCKED,NORTH",
            "INV9002,CUST9002,200,DOCKED,SOUTH",
        ],
        [
            "INV9002,CUST9002,200,SZ",
            "INV9001,CUST9001,999,NZ",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "slip_id,member_id,dock_zone,amount_cents,status"
    assert [row["slip_id"] for row in rows] == ["INV9002", "INV9001"]
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert [row["dock_zone"] for row in rows] == ["SOUTH", ""]
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 200,
        "unmatched_count": 1,
        "unmatched_amount_cents": 999,
    }


def test_alias_matching_trims_surrounding_spaces_on_compared_fields():
    """Legacy alias matching should trim surrounding spaces from slip and credit fields."""
    write_inputs(
        [
            " INV8801 , CUST8801 , 5500 , docked , south ",
            "INV8802,CUST8802,6600,DOCKED,east",
        ],
        [
            " INV8801 , CUST8801 , 5500 , sz ",
            " INV8802 , CUST8802 ,6600, EZ ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["slip_id"] for row in rows] == ["INV8801", "INV8802"]
    assert [row["member_id"] for row in rows] == ["CUST8801", "CUST8802"]
    assert [row["dock_zone"] for row in rows] == ["SOUTH", "EAST"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 12100
    assert summary["unmatched_count"] == 0


def test_duplicate_alias_credits_do_not_reuse_consumed_slip():
    """Only the earliest eligible alias credit should consume a matching slip."""
    write_inputs(
        [
            "INV8803,CUST8803,7700,DOCKED,SOUTH",
            "INV8804,CUST8804,8800,DOCKED,NORTH",
        ],
        [
            "INV8803,CUST8803,7700,SZ",
            "INV8803,CUST8803,7700,SZ",
            "INV8804,CUST8804,8800,NZ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["dock_zone"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16500
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7700


def test_full_slip_id_comparison_rejects_prefix_only_match():
    """Alias matching must compare full slip_id values, not shared prefixes."""
    write_inputs(
        ["INV20260401001,CUST01,500,DOCKED,NORTH"],
        ["INV20260401002,CUST01,500,NZ"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["dock_zone"] == ""
    assert summary["matched_count"] == 0
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 500
