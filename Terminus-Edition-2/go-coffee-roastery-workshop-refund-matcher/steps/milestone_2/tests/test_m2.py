"""Verifier tests for the workshop refund reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
WORKSHOPS = APP / "data" / "workshops.csv"
ACTIONS = APP / "data" / "refunds.csv"
REPORT = APP / "out" / "workshop_refund_report.csv"
SUMMARY = APP / "out" / "workshop_refund_summary.json"
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


def write_inputs(workshop_rows, refund_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    WORKSHOPS.write_text("workshop_id,attendee_id,amount_cents,status,workshop_type\n" + "\n".join(workshop_rows) + "\n")
    CREDITS.write_text("workshop_id,attendee_id,amount_cents,workshop_type\n" + "\n".join(refund_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_roast_refund_matches_and_counts_positive_amount():
    """ROAST refunds should match active workshops and add positive cents to matched totals."""
    write_inputs(
        [
            "INV20260401001,CUST1001,12500,ACTIVE,BREW",
            "INV20260401002,CUST1002,9900,ACTIVE,ROAST",
        ],
        [
            "INV20260401001,CUST1001,12500,BREW",
            "INV20260401002,CUST1002,9900,ROAST",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["workshop_type"] == "ROAST"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_workshop_id_match_uses_full_identifier():
    """A refund must not match a workshop that only shares the leading workshop prefix."""
    write_inputs(
        [
            "INV777770001,CUST2001,3300,ACTIVE,BREW",
            "INV777770002,CUST2001,3300,ACTIVE,BREW",
        ],
        [
            "INV777770003,CUST2001,3300,BREW",
            "INV777770002,CUST2001,3300,BREW",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["workshop_type"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_workshop_type_all_gate_matching():
    """Customer, amount, active status, and allowed workshop_type must all be satisfied."""
    write_inputs(
        [
            "INV3001,CUST3001,1000,ACTIVE,BREW",
            "INV3002,CUST3002,2000,ACTIVE,ROAST",
            "INV3003,CUST3003,3000,DRAFT,CUP",
            "INV3004,CUST3004,4000,ACTIVE,CHECK",
            "INV3005,CUST3005,5000,ACTIVE,CUP",
        ],
        [
            "INV3001,CUST9999,1000,BREW",
            "INV3002,CUST3002,2100,ROAST",
            "INV3003,CUST3003,3000,CUP",
            "INV3004,CUST3004,4000,CHECK",
            "INV3005,CUST3005,5000,CUP",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["workshop_type"] == "CUP"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_refunds_do_not_reuse_consumed_workshop():
    """Only the earliest eligible refund may consume a matching workshop."""
    write_inputs(
        [
            "INV5551,CUST5551,7500,ACTIVE,ROAST",
            "INV5552,CUST5552,8800,ACTIVE,BREW",
        ],
        [
            "INV5551,CUST5551,7500,ROAST",
            "INV5551,CUST5551,7500,ROAST",
            "INV5552,CUST5552,8800,BREW",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["workshop_type"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_workshop_type_status_case():
    """Matching should tolerate surrounding spaces and case differences in workshop_type/status values."""
    write_inputs(
        [
            " INV6601 , CUST6601 , 6100 , active , roast ",
            "INV6602,CUST6602,7200,ACTIVE,cup",
        ],
        [
            "INV6601,CUST6601, 6100 ,ROAST",
            " INV6602 , CUST6602 ,7200, CUP ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["workshop_id"] for row in rows] == ["INV6601", "INV6602"]
    assert [row["attendee_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["workshop_type"] for row in rows] == ["ROAST", "CUP"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_legacy_workshop_type_aliases_match_and_emit_canonical_workshop_types():
    """Legacy BW, RS, and CP refund workshop_types should match and report canonical workshop_types."""
    write_inputs(
        [
            "INV7701,CUST7701,8800,ACTIVE,ROAST",
            "INV7702,CUST7702,9100,active,cup",
            "INV7703,CUST7703,4200,ACTIVE,BREW",
            "INV7704,CUST7704,5500,ACTIVE,BREW",
            "INV7705,CUST7705,3300,ACTIVE,CHECK",
        ],
        [
            "INV7701,CUST7701,8800,rs",
            "INV7702,CUST7702,9100,CP",
            "INV7703,CUST7703,4200,bw",
            "INV7704,CUST7704,5500,BW",
            "INV7705,CUST7705,3300,chk",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["workshop_type"] for row in rows] == ["ROAST", "CUP", "BREW", "BREW", ""]
    assert summary["matched_count"] == 4
    assert summary["matched_amount_cents"] == 27600
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 3300


def test_bw_alias_matches_brew_workshop_and_reports_canonical_workshop_type():
    """A BW refund must match a BREW workshop and emit BREW as the workshop_type."""
    write_inputs(
        ["INV7801,CUST7801,1234,ACTIVE,BREW"],
        ["INV7801,CUST7801,1234,bw"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["workshop_type"] == "BREW"
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
            "INV9001,CUST9001,100,ACTIVE,BREW",
            "INV9002,CUST9002,200,ACTIVE,ROAST",
            "INV9003,CUST9003,300,ACTIVE,CUP",
        ],
        [
            "INV9003,CUST9003,300,CUP",
            "INV9001,CUST9001,100,BREW",
            "INV9002,CUST9002,200,ROAST",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "workshop_id,attendee_id,workshop_type,amount_cents,status"
    assert [row["workshop_id"] for row in rows] == ["INV9003", "INV9001", "INV9002"]
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
            "STATPOST1,CUSTSTAT1,1100,POSTED,BREW",
            "STATBLANK1,CUSTSTAT2,1200,,BREW",
        ],
        [
            "STATPOST1,CUSTSTAT1,1100,BREW",
            "STATBLANK1,CUSTSTAT2,1200,BREW",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
    assert [row["workshop_type"] for row in rows] == ["", ""]
    assert summary["matched_count"] == 0
    assert summary["unmatched_count"] == 2
    assert summary["unmatched_amount_cents"] == 2300

def test_unmatched_report_fields_are_trimmed():
    """Unmatched report rows should still trim incidental spaces from action fields."""
    write_inputs(
        ["TRIMSRC1,CUSTSRC1,1900,ACTIVE,BREW"],
        [" TRIMACT1 , CUSTTRIM1 , 1700 , BREW "],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["workshop_id"] == "TRIMACT1"
    assert rows[0]["attendee_id"] == "CUSTTRIM1"
    assert rows[0]["amount_cents"] == "1700"
    assert rows[0]["workshop_type"] == ""
    assert summary["unmatched_amount_cents"] == 1700
