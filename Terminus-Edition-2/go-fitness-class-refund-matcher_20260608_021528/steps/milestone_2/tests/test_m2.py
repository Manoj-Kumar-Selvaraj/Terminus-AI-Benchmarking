"""Verifier tests for the classpass refund reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
INVOICES = APP / "data" / "classes.csv"
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
    INVOICES.write_text("class_id,member_id,amount_cents,status,studio\n" + "\n".join(bill_rows) + "\n")
    PAYMENTS.write_text("class_id,member_id,amount_cents,studio\n" + "\n".join(refund_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_spin_refund_matches_and_counts_positive_amount():
    """SPIN refunds should match booked classpasses and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,BOOKED,YOGA",
            "INV20260401002,CUST1002,9900,BOOKED,SPIN",
        ],
        [
            "INV20260401001,CUST1001,12500,YOGA",
            "INV20260401002,CUST1002,9900,SPIN",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["studio"] == "SPIN"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_class_id_match_uses_full_identifier():
    """A refund must not match a classpass that only shares the leading classpass prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,BOOKED,YOGA",
            "INV777770002,CUST2001,3300,BOOKED,YOGA",
        ],
        [
            "INV777770003,CUST2001,3300,YOGA",
            "INV777770002,CUST2001,3300,YOGA",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["studio"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_studio_all_gate_matching():
    """Customer, amount, booked status, and allowed studio must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,1000,BOOKED,YOGA",
            "INV3002,CUST3002,2000,BOOKED,SPIN",
            "INV3003,CUST3003,3000,DRAFT,HIIT",
            "INV3004,CUST3004,4000,BOOKED,CHECK",
            "INV3005,CUST3005,5000,BOOKED,HIIT",
        ],
        [
            "INV3001,CUST9999,1000,YOGA",
            "INV3002,CUST3002,2100,SPIN",
            "INV3003,CUST3003,3000,HIIT",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,HIIT",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["studio"] == "HIIT"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_refunds_do_not_reuse_consumed_bill():
    """Only the earliest eligible refund may consume a matching classpass."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,BOOKED,SPIN",
            "INV5552,CUST5552,8800,BOOKED,YOGA",
        ],
        [
            "INV5551,CUST5551,7500,SPIN",
            "INV5551,CUST5551,7500,SPIN",
            "INV5552,CUST5552,8800,YOGA",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["studio"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_studio_status_case():
    """Matching should tolerate surrounding spaces and case differences in studio/status values."""
    write_inputs(
        [
            " INV6601 , CUST6601 , 6100 , booked , spin ",
            "INV6602,CUST6602,7200,BOOKED,hiit",
        ],
        [
            "INV6601,CUST6601, 6100 ,SPIN",
            " INV6602 , CUST6602 ,7200, HIIT ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["class_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["member_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["studio"] for row in rows] == ["SPIN", "HIIT"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_legacy_studio_aliases_match_and_emit_canonical_studios():
    """Legacy YG, SP, and HT refund studios should match and report canonical studios."""
    write_inputs(
        [
            "INV7701,CUST7701,8800,BOOKED,SPIN",
            "INV7702,CUST7702,9100,booked,hiit",
            "INV7703,CUST7703,4200,BOOKED,YOGA",
            "INV7704,CUST7704,3300,BOOKED,CHECK",
        ],
        [
            "INV7701,CUST7701,8800,sp",
            "INV7702,CUST7702,9100,HT",
            "INV7703,CUST7703,4200,YG",
            "INV7704,CUST7704,3300,chk",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["studio"] for row in rows] == ["SPIN", "HIIT", "YOGA", ""]
    assert summary["matched_count"] == 3
    assert summary["matched_amount_cents"] == 22100
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 3300


def test_yg_alias_matches_yoga_classpass_and_reports_canonical_studio():
    """A YG refund must match a BOOKED YOGA classpass and emit YOGA as the studio."""
    write_inputs(
        [
            "INV7801,CUST7801,5500,BOOKED,YOGA",
            "INV7802,CUST7802,6600,BOOKED,YOGA",
        ],
        [
            "INV7801,CUST7801,5500,YG",
            "INV7802,CUST7802,6600,yg",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["studio"] for row in rows] == ["YOGA", "YOGA"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 12100
    assert summary["unmatched_count"] == 0


def test_report_status_column_uses_only_matched_or_unmatched():
    """The report status column must only contain MATCHED or UNMATCHED, never BOOKED or the classpass status."""
    write_inputs(
        [
            "INV8801,CUST8801,1500,BOOKED,YOGA",
            "INV8802,CUST8802,2500,BOOKED,SPIN",
            "INV8803,CUST8803,3500,DRAFT,HIIT",
        ],
        [
            "INV8801,CUST8801,1500,YG",
            "INV8802,CUST8802,2500,SPIN",
            "INV8803,CUST8803,3500,HT",
        ],
    )
    rows, summary = run_program()

    statuses = [row["status"] for row in rows]
    assert set(statuses).issubset({"MATCHED", "UNMATCHED"})
    assert "BOOKED" not in statuses
    assert "DRAFT" not in statuses
    assert statuses == ["MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["studio"] for row in rows] == ["YOGA", "SPIN", ""]
    assert summary["matched_count"] == 2
    assert summary["unmatched_count"] == 1


def test_aliases_normalize_with_surrounding_spaces_and_mixed_case():
    """Legacy aliases must still resolve when surrounded by whitespace or written in mixed case."""
    write_inputs(
        [
            "INV8901,CUST8901,1100,BOOKED,YOGA",
            "INV8902,CUST8902,1200,BOOKED,SPIN",
            "INV8903,CUST8903,1300,BOOKED,HIIT",
        ],
        [
            "INV8901,CUST8901,1100, Yg ",
            "INV8902,CUST8902,1200,sP",
            "INV8903,CUST8903,1300, hT ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["studio"] for row in rows] == ["YOGA", "SPIN", "HIIT"]
    assert summary["matched_count"] == 3
    assert summary["matched_amount_cents"] == 3600


def test_report_schema_and_refund_input_order_are_stable():
    """The report should use the required schema and preserve refund input order."""
    write_inputs(
        [
            "INV9001,CUST9001,100,BOOKED,YOGA",
            "INV9002,CUST9002,200,BOOKED,SPIN",
            "INV9003,CUST9003,300,BOOKED,HIIT",
        ],
        [
            "INV9003,CUST9003,300,HIIT",
            "INV9001,CUST9001,100,YOGA",
            "INV9002,CUST9002,200,SPIN",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "class_id,member_id,studio,amount_cents,status"
    assert [row["class_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
