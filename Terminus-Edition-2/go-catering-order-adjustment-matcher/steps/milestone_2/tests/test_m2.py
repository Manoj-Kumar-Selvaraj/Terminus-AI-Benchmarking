"""Milestone 2 verifier tests for legacy service alias normalization."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
INVOICES = APP / "data" / "orders.csv"
PAYMENTS = APP / "data" / "adjustments.csv"
REPORT = APP / "out" / "adjustment_report.csv"
SUMMARY = APP / "out" / "adjustment_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go reconciliation CLI for the current source tree."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all verifier tests."""
    build_program()


def write_inputs(bill_rows, refund_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    INVOICES.write_text("order_id,venue_id,amount_cents,status,service\n" + "\n".join(bill_rows) + "\n")
    PAYMENTS.write_text("order_id,venue_id,amount_cents,service\n" + "\n".join(refund_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_legacy_service_aliases_match_and_emit_canonical_services():
    """Legacy PU, DEL, and OS adjustment services should match and report canonical services."""
    write_inputs(
        [
            "INV7701,CUST7701,8800,FULFILLED,PICKUP",
            "INV7702,CUST7702,9100,FULFILLED,DELIVERY",
            "INV7703,CUST7703,4200,fulfilled,onsite",
            "INV7704,CUST7704,3300,FULFILLED,CHECK",
        ],
        [
            "INV7701,CUST7701,8800,pu",
            "INV7702,CUST7702,9100,del",
            "INV7703,CUST7703,4200,OS",
            "INV7704,CUST7704,3300,chk",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["service"] for row in rows] == ["PICKUP", "DELIVERY", "ONSITE", ""]
    assert summary["matched_count"] == 3
    assert summary["matched_amount_cents"] == 22100
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 3300


def test_mixed_canonical_and_alias_services_in_same_batch():
    """Canonical services and legacy aliases should normalize together in one batch."""
    write_inputs(
        [
            "INV7801,CUST7801,1100,FULFILLED,PICKUP",
            "INV7802,CUST7802,2200,FULFILLED,DELIVERY",
            "INV7803,CUST7803,3300,FULFILLED,ONSITE",
            "INV7804,CUST7804,4400,FULFILLED,delivery",
        ],
        [
            "INV7801,CUST7801,1100,PICKUP",
            "INV7802,CUST7802,2200,del",
            "INV7803,CUST7803,3300,OS",
            "INV7804,CUST7804,4400,DELIVERY",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "MATCHED"]
    assert [row["service"] for row in rows] == ["PICKUP", "DELIVERY", "ONSITE", "DELIVERY"]
    assert summary == {
        "matched_count": 4,
        "matched_amount_cents": 11000,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_alias_selects_equivalent_canonical_order_not_first_allowed_order():
    """An alias should match only the equivalent canonical service, not any allowed service."""
    write_inputs(
        [
            "INV7851,CUST7851,4400,FULFILLED,DELIVERY",
            "INV7851,CUST7851,4400,FULFILLED,PICKUP",
            "INV7852,CUST7852,5500,FULFILLED,ONSITE",
        ],
        [
            "INV7851,CUST7851,4400,PU",
            "INV7851,CUST7851,4400,DEL",
            "INV7852,CUST7852,5500,os",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["service"] for row in rows] == ["PICKUP", "DELIVERY", "ONSITE"]
    assert summary["matched_count"] == 3
    assert summary["matched_amount_cents"] == 14300
    assert summary["unmatched_count"] == 0


def test_surrounding_spaces_are_trimmed():
    """Surrounding whitespace on order and adjustment fields must be trimmed before matching."""
    write_inputs(
        [" INV9001 , VEN9001 , 5500 , FULFILLED , PICKUP "],
        [" INV9001 , VEN9001 , 5500 , PU "],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["service"] == "PICKUP"
    assert summary["matched_count"] == 1
    assert summary["unmatched_count"] == 0


def test_earliest_adjustment_wins_when_multiple_eligible():
    """When duplicate adjustments target the same order, only the earliest eligible one may match."""
    write_inputs(
        ["INV9901,VEN9901,7700,FULFILLED,PICKUP"],
        [
            "INV9901,VEN9901,7700,PU",
            "INV9901,VEN9901,7700,PICKUP",
        ],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[1]["status"] == "UNMATCHED"
    assert summary["matched_count"] == 1
    assert summary["unmatched_count"] == 1
