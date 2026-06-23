"""Milestone 4 verifier tests for method-gated parking citation credits."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
CITATIONS = APP / "data" / "citations.csv"
CREDITS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
METHODS = APP / "config" / "methods.csv"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go citation credit reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 4 tests."""
    build_program()


def write_inputs(citation_rows, credit_rows, calendar_rows, method_rows):
    """Replace CSV inputs, calendar, and method policy with a focused scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    CITATIONS.write_text(
        "citation_id,plate_id,amount_cents,status,zone,due_date\n" + "\n".join(citation_rows) + "\n"
    )
    CREDITS.write_text(
        "citation_id,plate_id,amount_cents,zone,credit_date,credit_method\n" + "\n".join(credit_rows) + "\n"
    )
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    METHODS.write_text("method,enabled\n" + "\n".join(method_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse its CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone4:
    """Credit method policy gates composed with earlier status, alias, and date rules."""

    def test_enabled_methods_match_with_aliases_and_dates(self):
        """Enabled methods should allow otherwise eligible dated alias credits to match."""
        write_inputs(
            [
                "CIT4101,PLT4101,1000,PAID,STREET,2026-04-06",
                "CIT4102,PLT4102,2000,PAID,LOT,2026-04-07",
            ],
            [
                "CIT4101,PLT4101,1000,ST,2026-04-05,ach",
                "CIT4102,PLT4102,2000,LT,2026-04-05, CARD ",
            ],
            ["2026-04-05 open"],
            [" ACH , true ", "card,TRUE"],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "citation_id,plate_id,zone,amount_cents,status"
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["zone"] for row in rows] == ["STREET", "LOT"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 3000,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_disabled_missing_blank_and_malformed_methods_are_ineligible(self):
        """Disabled, absent, blank, and non-true method policy values should reject credits."""
        write_inputs(
            [
                "CIT4201,PLT4201,100,PAID,STREET,2026-04-06",
                "CIT4202,PLT4202,200,PAID,GARAGE,2026-04-06",
                "CIT4203,PLT4203,300,PAID,LOT,2026-04-06",
                "CIT4204,PLT4204,400,PAID,STREET,2026-04-06",
            ],
            [
                "CIT4201,PLT4201,100,ST,2026-04-05,CHECK",
                "CIT4202,PLT4202,200,GRG,2026-04-05,CASH",
                "CIT4203,PLT4203,300,LT,2026-04-05,",
                "CIT4204,PLT4204,400,STREET,2026-04-05,WIRE",
            ],
            ["2026-04-05 open"],
            ["CHECK,false", "WIRE,yes", ",true", "BROKEN"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert [row["zone"] for row in rows] == ["", "", "", ""]
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 4,
            "unmatched_amount_cents": 1000,
        }

    def test_enabled_method_does_not_bypass_prior_matching_gates(self):
        """An enabled method alone must not bypass date, identity, amount, or status gates."""
        write_inputs(
            [
                "CIT4301,PLT4301,1000,PAID,STREET,2026-04-06",
                "CIT4302,PLT4302,2000,PAID,GARAGE,2026-04-06",
                "CIT4303,PLT4303,3000,POSTED,LOT,2026-04-06",
                "CIT4304,PLT4304,4000,PAID,LOT,2026-04-06",
            ],
            [
                "CIT4301,PLT4301,1000,STREET,2026-04-07,ACH",
                "CIT4302,PLT9999,2000,GRG,2026-04-05,ACH",
                "CIT4303,PLT4303,3000,LT,2026-04-05,ACH",
                "CIT4304,PLT4304,4100,LT,2026-04-05,ACH",
            ],
            ["2026-04-05 open", "2026-04-07 open"],
            ["ACH,true"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert [row["zone"] for row in rows] == ["", "", "", ""]
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 10100

    def test_method_gate_preserves_latest_date_selection_and_consumption(self):
        """Method gating should still use latest due_date selection and row consumption."""
        write_inputs(
            [
                "CIT4401,PLT4401,500,PAID,GARAGE,2026-04-04",
                "CIT4401,PLT4401,500,PAID,GARAGE,2026-04-08",
                "CIT4401,PLT4401,500,PAID,GARAGE,2026-04-08",
            ],
            [
                "CIT4401,PLT4401,500,GRG,2026-04-03,CARD",
                "CIT4401,PLT4401,500,GRG,2026-04-03,CARD",
                "CIT4401,PLT4401,500,GRG,2026-04-03,CARD",
                "CIT4401,PLT4401,500,GRG,2026-04-03,CARD",
            ],
            ["2026-04-03 open"],
            ["CARD,true"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["zone"] for row in rows] == ["GARAGE", "GARAGE", "GARAGE", ""]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 1500,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }
