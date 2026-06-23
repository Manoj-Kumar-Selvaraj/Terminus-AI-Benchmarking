"""Milestone 4 verifier tests for method-gated clinic visit credit matching CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
VISITS = APP / "data" / "visits.csv"
CREDITS = APP / "data" / "credits.csv"
METHODS = APP / "config" / "methods.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go credit reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 4 tests."""
    build_program()


def write_inputs(visit_rows, credit_rows, method_rows, calendar_rows=None, dated=False):
    """Replace runtime inputs and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    if dated:
        VISITS.write_text(
            "visit_id,customer_id,amount_cents,status,channel,due_date\n" + "\n".join(visit_rows) + "\n"
        )
        CREDITS.write_text(
            "visit_id,customer_id,amount_cents,channel,credit_date\n" + "\n".join(credit_rows) + "\n"
        )
    else:
        VISITS.write_text(
            "visit_id,customer_id,amount_cents,status,channel\n" + "\n".join(visit_rows) + "\n"
        )
        CREDITS.write_text("visit_id,customer_id,amount_cents,channel\n" + "\n".join(credit_rows) + "\n")
    METHODS.write_text("channel,enabled\n" + "\n".join(method_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows or ["2099-12-31 closed"]) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse its CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_enabled_methods_preserve_base_matching_and_alias_outputs():
    """Enabled canonical channels should preserve prior matching, aliases, and positive totals."""
    write_inputs(
        [
            "VISIT4101,CUST4101,1100,POSTED,ACH",
            "VISIT4102,CUST4102,2200,POSTED,CARD",
            "VISIT4103,CUST4103,3300,POSTED,WIRE",
        ],
        [
            "VISIT4102,CUST4102,2200,CC",
            "VISIT4103,CUST4103,3300,WIR",
            "VISIT4101,CUST4101,1100,ACH",
        ],
        ["ACH,true", "CARD,true", "WIRE,true"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["channel"] for row in rows] == ["CARD", "WIRE", "ACH"]
    assert [row["visit_id"] for row in rows] == ["VISIT4102", "VISIT4103", "VISIT4101"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 6600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_disabled_method_blocks_otherwise_matching_credit():
    """A disabled channel in methods.csv should make an otherwise matching credit unmatched."""
    write_inputs(
        [
            "VISIT4201,CUST4201,1400,POSTED,CARD",
            "VISIT4202,CUST4202,1500,POSTED,ACH",
        ],
        [
            "VISIT4201,CUST4201,1400,CC",
            "VISIT4202,CUST4202,1500,ACH",
        ],
        ["ACH,true", "CARD,false", "WIRE,true"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert [row["channel"] for row in rows] == ["", "ACH"]
    assert summary["matched_amount_cents"] == 1500
    assert summary["unmatched_amount_cents"] == 1400


def test_method_parser_trims_and_compares_case_insensitively():
    """Whitespace and mixed case in method rows should not prevent eligibility."""
    write_inputs(
        [
            " VISIT4301 , CUST4301 , 1200 , posted , card ",
            "VISIT4302,CUST4302,1300,POSTED,wire",
        ],
        [
            "VISIT4301,CUST4301,1200,cc",
            " VISIT4302 , CUST4302 , 1300 , wir ",
        ],
        [" card , TRUE ", " wire , TrUe ", " ach , false "],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["channel"] for row in rows] == ["CARD", "WIRE"]
    assert [row["customer_id"] for row in rows] == ["CUST4301", "CUST4302"]
    assert summary["matched_amount_cents"] == 2500


def test_missing_malformed_non_true_and_alias_method_rows_are_ineligible():
    """Only canonical rows with enabled=true should enable a channel."""
    write_inputs(
        [
            "VISIT4401,CUST4401,100,POSTED,CARD",
            "VISIT4402,CUST4402,200,POSTED,WIRE",
            "VISIT4403,CUST4403,300,POSTED,ACH",
            "VISIT4404,CUST4404,400,POSTED,CARD",
        ],
        [
            "VISIT4401,CUST4401,100,CC",
            "VISIT4402,CUST4402,200,WIR",
            "VISIT4403,CUST4403,300,ACH",
            "VISIT4404,CUST4404,400,CARD",
        ],
        [
            "CC,true",
            "WIRE,yes",
            "ACH",
            "CARD, true, extra",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert [row["channel"] for row in rows] == ["", "", "", ""]
    assert summary == {
        "matched_count": 0,
        "matched_amount_cents": 0,
        "unmatched_count": 4,
        "unmatched_amount_cents": 1000,
    }


def test_methods_gate_applies_in_dated_mode_with_latest_due_date_selection():
    """Dated batches should satisfy both calendar and method gates before latest-date selection."""
    write_inputs(
        [
            "VISIT4501,CUST4501,500,POSTED,CARD,2026-04-02",
            "VISIT4501,CUST4501,500,POSTED,CARD,2026-04-06",
            "VISIT4502,CUST4502,600,POSTED,ACH,2026-04-05",
            "VISIT4503,CUST4503,700,POSTED,WIRE,2026-04-05",
        ],
        [
            "VISIT4501,CUST4501,500,CC,2026-04-04",
            "VISIT4502,CUST4502,600,ACH,2026-04-04",
            "VISIT4503,CUST4503,700,WIR,2026-04-04",
        ],
        ["ACH,true", "CARD,true", "WIRE,false"],
        ["2026-04-04 open", "2026-04-05 open", "2026-04-06 open"],
        dated=True,
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["channel"] for row in rows] == ["CARD", "ACH", ""]
    assert summary == {
        "matched_count": 2,
        "matched_amount_cents": 1100,
        "unmatched_count": 1,
        "unmatched_amount_cents": 700,
    }


def test_methods_do_not_break_row_position_consumption_for_duplicate_visit_ids():
    """Consumption must still be by physical visit row after method gating is added."""
    write_inputs(
        [
            "VISIT4601,CUST4601,800,POSTED,CARD,2026-04-05",
            "VISIT4601,CUST4601,800,POSTED,CARD,2026-04-05",
        ],
        [
            "VISIT4601,CUST4601,800,CC,2026-04-04",
            "VISIT4601,CUST4601,800,CC,2026-04-04",
            "VISIT4601,CUST4601,800,CC,2026-04-04",
        ],
        ["CARD,true"],
        ["2026-04-04 open", "2026-04-05 open"],
        dated=True,
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["channel"] for row in rows] == ["CARD", "CARD", ""]
    assert summary["matched_count"] == 2
    assert summary["unmatched_count"] == 1
