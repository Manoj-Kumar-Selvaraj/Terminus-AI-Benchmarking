"""Milestone 2 verifier tests for legacy format alias normalization."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
INVOICES = APP / "data" / "sales.csv"
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
    INVOICES.write_text("sale_id,buyer_id,amount_cents,status,format\n" + "\n".join(bill_rows) + "\n")
    PAYMENTS.write_text("sale_id,buyer_id,amount_cents,format\n" + "\n".join(refund_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_milestone1_regression_full_sale_id_required():
    """Milestone 2 must still reject credits that only share a sale_id prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,SHIPPED,LP",
            "INV777770002,CUST2001,3300,SHIPPED,LP",
        ],
        [
            "INV777770003,CUST2001,3300,LP",
            "INV777770002,CUST2001,3300,LP",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert summary["matched_count"] == 1


def test_milestone1_regression_duplicate_credits_consume_once():
    """Milestone 2 must still consume each sale row at most once."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,SHIPPED,EP",
            "INV5552,CUST5552,8800,SHIPPED,LP",
        ],
        [
            "INV5551,CUST5551,7500,EP",
            "INV5551,CUST5551,7500,EP",
            "INV5552,CUST5552,8800,LP",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert summary["matched_count"] == 2


def test_legacy_format_aliases_match_and_emit_canonical_formats():
    """Legacy SING, SET, and LONG credit formats should match and report canonical formats."""
    write_inputs(
        [
            "INV7701,CUST7701,8800,SHIPPED,EP",
            "INV7702,CUST7702,9100,shipped,box",
            "INV7703,CUST7703,4200,SHIPPED,LP",
            "INV7704,CUST7704,3300,SHIPPED,CHECK",
        ],
        [
            "INV7701,CUST7701,8800,sing",
            "INV7702,CUST7702,9100,SET",
            "INV7703,CUST7703,4200,LONG",
            "INV7704,CUST7704,3300,chk",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["format"] for row in rows] == ["EP", "BOX", "LP", ""]
    assert summary["matched_count"] == 3
    assert summary["matched_amount_cents"] == 22100
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 3300


def test_unknown_alias_stays_unmatched_even_when_both_sides_share_it():
    """Shared unknown alias-like formats must not become match-eligible in milestone 2."""
    write_inputs(
        ["INV8801,CUST8801,5000,SHIPPED,BAD"],
        ["INV8801,CUST8801,5000,bad"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["format"] == ""
    assert summary["matched_count"] == 0


def test_alias_only_on_credit_side_with_canonical_sale_format():
    """Credits may use aliases while sales stay canonical and still match."""
    write_inputs(
        ["INV8901,CUST8901,6100,SHIPPED,BOX"],
        ["INV8901,CUST8901,6100,set"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["format"] == "BOX"
    assert summary["matched_amount_cents"] == 6100


def test_sale_side_alias_normalizes_before_matching():
    """Sales with legacy alias formats must normalize the same way as credits."""
    write_inputs(
        ["INV9001,CUST9001,7200,SHIPPED,sing"],
        ["INV9001,CUST9001,7200,EP"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["format"] == "EP"
    assert summary["matched_count"] == 1


def test_matching_trims_surrounding_spaces_with_legacy_aliases():
    """Surrounding spaces on sale and credit fields must still match after alias normalization."""
    write_inputs(
        [" INV9201 , CUST9201 , 5000 , shipped , long "],
        ["INV9201,CUST9201, 5000 , LONG"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["format"] == "LP"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000


def test_report_schema_and_refund_input_order_are_stable():
    """The report should use the required schema and preserve credit input order."""
    write_inputs(
        [
            "INV9101,CUST9101,100,SHIPPED,LP",
            "INV9102,CUST9102,200,SHIPPED,EP",
            "INV9103,CUST9103,300,SHIPPED,BOX",
        ],
        [
            "INV9103,CUST9103,300,BOX",
            "INV9101,CUST9101,100,long",
            "INV9102,CUST9102,200,EP",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "sale_id,buyer_id,format,amount_cents,status"
    assert [row["sale_id"] for row in rows] == ["INV9103", "INV9101", "INV9102"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
