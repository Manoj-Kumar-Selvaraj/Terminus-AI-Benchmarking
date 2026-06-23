"""Verifier tests for the tour refund reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
TOURS = APP / "data" / "tours.csv"
ACTIONS = APP / "data" / "refunds.csv"
REPORT = APP / "out" / "tour_refund_report.csv"
SUMMARY = APP / "out" / "tour_refund_summary.json"
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


def write_inputs(tour_rows, refund_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    TOURS.write_text("tour_id,guest_id,amount_cents,status,tour_type\n" + "\n".join(tour_rows) + "\n")
    CREDITS.write_text("tour_id,guest_id,amount_cents,tour_type\n" + "\n".join(refund_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_shark_refund_matches_and_counts_positive_amount():
    """SHARK refunds should match active tours and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,ACTIVE,REEF",
            "INV20260401002,CUST1002,9900,ACTIVE,SHARK",
        ],
        [
            "INV20260401001,CUST1001,12500,REEF",
            "INV20260401002,CUST1002,9900,SHARK",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["tour_type"] == "SHARK"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_tour_id_match_uses_full_identifier():
    """A refund must not match a tour that only shares the leading tour prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,ACTIVE,REEF",
            "INV777770002,CUST2001,3300,ACTIVE,REEF",
        ],
        [
            "INV777770003,CUST2001,3300,REEF",
            "INV777770002,CUST2001,3300,REEF",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["tour_type"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_tour_type_all_gate_matching():
    """Customer, amount, active status, and allowed tour_type must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,1000,ACTIVE,REEF",
            "INV3002,CUST3002,2000,ACTIVE,SHARK",
            "INV3003,CUST3003,3000,DRAFT,VIP",
            "INV3004,CUST3004,4000,ACTIVE,CHECK",
            "INV3005,CUST3005,5000,ACTIVE,VIP",
        ],
        [
            "INV3001,CUST9999,1000,REEF",
            "INV3002,CUST3002,2100,SHARK",
            "INV3003,CUST3003,3000,VIP",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,VIP",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["tour_type"] == "VIP"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_refunds_do_not_reuse_consumed_tour():
    """Only the earliest eligible refund may consume a matching tour."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,ACTIVE,SHARK",
            "INV5552,CUST5552,8800,ACTIVE,REEF",
        ],
        [
            "INV5551,CUST5551,7500,SHARK",
            "INV5551,CUST5551,7500,SHARK",
            "INV5552,CUST5552,8800,REEF",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["tour_type"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_tour_type_status_case():
    """Matching should tolerate surrounding spaces and case differences in tour_type/status values."""
    write_inputs(
        [
            " INV6601 , CUST6601 , 6100 , active , shark ",
            "INV6602,CUST6602,7200,ACTIVE,vip",
        ],
        [
            "INV6601,CUST6601, 6100 ,SHARK",
            " INV6602 , CUST6602 ,7200, VIP ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["tour_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["guest_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["tour_type"] for row in rows] == ["SHARK", "VIP"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_legacy_tour_type_aliases_match_and_emit_canonical_tour_types():
    """Legacy RF, SH, and VP refund tour_types should match and report canonical tour_types."""
    write_inputs(
        [
            "INV7701,CUST7701,8800,ACTIVE,SHARK",
            "INV7702,CUST7702,9100,active,vip",
            "INV7703,CUST7703,4200,ACTIVE,REEF",
            "INV7704,CUST7704,5500,ACTIVE,REEF",
            "INV7705,CUST7705,3300,ACTIVE,CHECK",
        ],
        [
            "INV7701,CUST7701,8800,sh",
            "INV7702,CUST7702,9100,VP",
            "INV7703,CUST7703,4200,rf",
            "INV7704,CUST7704,5500,RF",
            "INV7705,CUST7705,3300,chk",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["tour_type"] for row in rows] == ["SHARK", "VIP", "REEF", "REEF", ""]
    assert summary["matched_count"] == 4
    assert summary["matched_amount_cents"] == 27600
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 3300


def test_rf_alias_matches_reef_tour_and_reports_canonical_tour_type():
    """A RF refund must match a REEF tour and emit REEF as the tour_type."""
    write_inputs(
        ["INV7801,CUST7801,1234,ACTIVE,REEF"],
        ["INV7801,CUST7801,1234,rf"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["tour_type"] == "REEF"
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 1234,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_report_schema_and_refund_input_order_are_stable():
    """The report should use the required schema and preserve refund input order."""
    write_inputs(
        [
            "INV9001,CUST9001,100,ACTIVE,REEF",
            "INV9002,CUST9002,200,ACTIVE,SHARK",
            "INV9003,CUST9003,300,ACTIVE,VIP",
        ],
        [
            "INV9003,CUST9003,300,VIP",
            "INV9001,CUST9001,100,REEF",
            "INV9002,CUST9002,200,SHARK",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "tour_id,guest_id,tour_type,amount_cents,status"
    assert [row["tour_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }

def test_posted_and_blank_source_statuses_do_not_match():
    """Only ACTIVE source rows are eligible; POSTED or blank status rows must stay unmatched."""
    write_inputs(
        [
            "STATPOST1,CUSTSTAT1,1100,POSTED,REEF",
            "STATBLANK1,CUSTSTAT2,1200,,REEF",
        ],
        [
            "STATPOST1,CUSTSTAT1,1100,REEF",
            "STATBLANK1,CUSTSTAT2,1200,REEF",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
    assert [row["tour_type"] for row in rows] == ["", ""]
    assert summary["matched_count"] == 0
    assert summary["unmatched_count"] == 2
    assert summary["unmatched_amount_cents"] == 2300

def test_unmatched_report_fields_are_trimmed():
    """Unmatched report rows should still trim incidental spaces from action fields."""
    write_inputs(
        ["TRIMSRC1,CUSTSRC1,1900,ACTIVE,REEF"],
        [" TRIMACT1 , CUSTTRIM1 , 1700 , REEF "],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["tour_id"] == "TRIMACT1"
    assert rows[0]["guest_id"] == "CUSTTRIM1"
    assert rows[0]["amount_cents"] == "1700"
    assert rows[0]["tour_type"] == ""
    assert summary["unmatched_amount_cents"] == 1700
