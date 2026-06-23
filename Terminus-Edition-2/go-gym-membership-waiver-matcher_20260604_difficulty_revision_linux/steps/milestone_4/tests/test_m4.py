"""Milestone 4 verifier tests for method-gated membership waiver reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
MEMBERSHIPS = APP / "data" / "memberships.csv"
WAIVERS = APP / "data" / "waivers.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
METHODS = APP / "config" / "methods.csv"
REPORT = APP / "out" / "waiver_report.csv"
SUMMARY = APP / "out" / "waiver_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go waiver reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 4 tests."""
    build_program()


def write_inputs(membership_rows, waiver_rows, calendar_rows, method_rows):
    """Replace CSV inputs, calendar, and method policy with a focused scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    MEMBERSHIPS.write_text(
        "membership_id,member_id,amount_cents,status,plan,renewal_date\n" + "\n".join(membership_rows) + "\n"
    )
    WAIVERS.write_text(
        "membership_id,member_id,amount_cents,plan,waiver_date,waiver_method\n" + "\n".join(waiver_rows) + "\n"
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
    """Method policy gates composed with earlier identity, alias, and date rules."""

    def test_enabled_methods_match_with_aliases_and_dates(self):
        """Enabled methods should allow otherwise eligible dated alias waivers to match."""
        write_inputs(
            [
                "GYM4101,MEM4101,1000,ACTIVE,BASIC,2026-04-06",
                "GYM4102,MEM4102,2000,ACTIVE,ELITE,2026-04-07",
            ],
            [
                "GYM4101,MEM4101,1000,BAS,2026-04-05,ach",
                "GYM4102,MEM4102,2000,ELI,2026-04-05, CARD ",
            ],
            [
                "2026-04-05 open",
            ],
            [
                " ACH , true ",
                "card,TRUE",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "membership_id,member_id,plan,amount_cents,status"
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["plan"] for row in rows] == ["BASIC", "ELITE"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 3000,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_disabled_missing_blank_and_malformed_methods_are_ineligible(self):
        """Disabled, absent, blank, and non-true method policy values should reject waivers."""
        write_inputs(
            [
                "GYM4201,MEM4201,100,ACTIVE,BASIC,2026-04-06",
                "GYM4202,MEM4202,200,ACTIVE,PLUS,2026-04-06",
                "GYM4203,MEM4203,300,ACTIVE,ELITE,2026-04-06",
                "GYM4204,MEM4204,400,ACTIVE,BASIC,2026-04-06",
            ],
            [
                "GYM4201,MEM4201,100,BAS,2026-04-05,CHECK",
                "GYM4202,MEM4202,200,PLU,2026-04-05,CASH",
                "GYM4203,MEM4203,300,ELI,2026-04-05,",
                "GYM4204,MEM4204,400,BASIC,2026-04-05,WIRE",
            ],
            [
                "2026-04-05 open",
            ],
            [
                "CHECK,false",
                "WIRE,yes",
                ",true",
                "BROKEN",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert [row["plan"] for row in rows] == ["", "", "", ""]
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
                "GYM4301,MEM4301,1000,ACTIVE,BASIC,2026-04-06",
                "GYM4302,MEM4302,2000,ACTIVE,PLUS,2026-04-06",
                "GYM4303,MEM4303,3000,PAUSED,ELITE,2026-04-06",
                "GYM4304,MEM4304,4000,ACTIVE,ELITE,2026-04-06",
            ],
            [
                "GYM4301,MEM4301,1000,BASIC,2026-04-07,ACH",
                "GYM4302,MEM9999,2000,PLU,2026-04-05,ACH",
                "GYM4303,MEM4303,3000,ELI,2026-04-05,ACH",
                "GYM4304,MEM4304,4100,ELI,2026-04-05,ACH",
            ],
            [
                "2026-04-05 open",
                "2026-04-07 open",
            ],
            [
                "ACH,true",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert [row["plan"] for row in rows] == ["", "", "", ""]
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 10100

    def test_method_gate_preserves_latest_date_selection_and_consumption(self):
        """Method gating should still use latest renewal_date selection and row consumption."""
        write_inputs(
            [
                "GYM4401,MEM4401,500,ACTIVE,PLUS,2026-04-04",
                "GYM4401,MEM4401,500,ACTIVE,PLUS,2026-04-08",
                "GYM4401,MEM4401,500,ACTIVE,PLUS,2026-04-08",
            ],
            [
                "GYM4401,MEM4401,500,PLU,2026-04-03,CARD",
                "GYM4401,MEM4401,500,PLU,2026-04-03,CARD",
                "GYM4401,MEM4401,500,PLU,2026-04-03,CARD",
                "GYM4401,MEM4401,500,PLU,2026-04-03,CARD",
            ],
            [
                "2026-04-03 open",
            ],
            [
                "CARD,true",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["plan"] for row in rows] == ["PLUS", "PLUS", "PLUS", ""]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 1500,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }
