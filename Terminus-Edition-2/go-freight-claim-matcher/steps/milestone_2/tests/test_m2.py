"""Milestone 2 verifier tests for legacy reason alias matching."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
SHIPMENTS = APP / "data" / "shipments.csv"
CLAIMS = APP / "data" / "claims.csv"
REPORT = APP / "out" / "claim_report.csv"
SUMMARY = APP / "out" / "claim_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")
REPORT_FIELDS = ["shipment_id", "admgount_id", "reason", "amount_cents", "status"]
SUMMARY_FIELDS = ["matched_count", "matched_amount_cents", "unmatched_count", "unmatched_amount_cents"]


def build_program():
    """Compile the Go reconciliation CLI for the current source tree."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all verifier tests."""
    build_program()


def write_inputs(shipment_rows, claim_rows):
    """Replace input CSV files with a milestone 2 alias scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SHIPMENTS.write_text("shipment_id,admgount_id,amount_cents,status,reason\n" + "\n".join(shipment_rows) + "\n")
    CLAIMS.write_text("shipment_id,admgount_id,amount_cents,reason\n" + "\n".join(claim_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == REPORT_FIELDS
        rows = list(reader)
    summary = json.loads(SUMMARY.read_text())
    assert list(summary) == SUMMARY_FIELDS
    assert all(type(summary[key]) is int for key in SUMMARY_FIELDS)
    return rows, summary


def test_legacy_reason_aliases_match_and_emit_canonical_reasons():
    """DMG and HZD claim aliases should match and emit LOST/HAZ canonical reasons."""
    write_inputs(
        [
            "INV7701,CUST7701,8800,POSTED,LOST",
            "INV7702,CUST7702,9100,posted,haz",
            "INV7703,CUST7703,4200,POSTED,DAMAGED",
            "INV7704,CUST7704,3300,POSTED,CHECK",
        ],
        [
            "INV7701,CUST7701,8800,dmg",
            "INV7702,CUST7702,9100,HZD",
            "INV7703,CUST7703,4200,damaged",
            "INV7704,CUST7704,3300,chk",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["reason"] for row in rows] == ["LOST", "HAZ", "DAMAGED", ""]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 22100,
        "unmatched_count": 1,
        "unmatched_amount_cents": 3300,
    }


def test_alias_normalization_does_not_bypass_identity_or_reason_gates():
    """Aliases should still require full identifiers, amount, status, and canonical reason equality."""
    write_inputs(
        [
            "INV88010001,CUST8801,1000,POSTED,LOST",
            "INV88010002,CUST8802,2000,POSTED,HAZ",
            "INV88010003,CUST8803,3000,DRAFT,LOST",
            "INV88010004,CUST8804,4000,POSTED,DAMAGED",
        ],
        [
            "INV88010009,CUST8801,1000,DMG",
            "INV88010002,CUST8802,2001,HZD",
            "INV88010003,CUST8803,3000,DMG",
            "INV88010004,CUST8804,4000,HZD",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert [row["reason"] for row in rows] == ["", "", "", ""]
    assert summary["matched_count"] == 0
    assert summary["unmatched_amount_cents"] == 10001


def test_alias_matching_preserves_consumption_order_and_clean_report_fields():
    """Alias-aware matching should consume each shipment once and emit trimmed canonical fields."""
    write_inputs(
        [
            " INV9901 , CUST9901 , 5100 , POSTED , LOST ",
            "INV9902,CUST9902,6200,POSTED,HAZ",
        ],
        [
            " INV9901 , CUST9901 , 5100 , dmg ",
            "INV9901,CUST9901,5100,DMG",
            " INV9902 , CUST9902 , 6200 , hzd ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert [row["shipment_id"] for row in rows] == ["INV9901", "INV9901", "INV9902"]
    assert [row["admgount_id"] for row in rows] == ["CUST9901", "CUST9901", "CUST9902"]
    assert [row["reason"] for row in rows] == ["LOST", "", "HAZ"]
    assert all(value == value.strip() for row in rows for value in row.values())
    assert summary == {
        "matched_count": 2,
        "matched_amount_cents": 11300,
        "unmatched_count": 1,
        "unmatched_amount_cents": 5100,
    }
