"""Milestone 4 verifier tests for runtime plan-tier method eligibility."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
WSHS = APP / "data" / "washes.csv"
REBATES = APP / "data" / "rebates.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
METHODS = APP / "config" / "methods.csv"
REPORT = APP / "out" / "wash_rebate_report.csv"
SUMMARY = APP / "out" / "wash_rebate_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go reconciliation CLI for milestone 4 tests."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 4 tests."""
    build_program()


def write_inputs(wash_rows, rebate_rows, method_rows, calendar_rows=None, dated=False):
    """Replace inputs and methods policy with a focused milestone 4 scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    if dated:
        WSHS.write_text("wash_id,customer_id,amount_cents,status,plan_tier,wash_date\n" + "\n".join(wash_rows) + "\n")
        REBATES.write_text("wash_id,customer_id,amount_cents,plan_tier,rebate_date\n" + "\n".join(rebate_rows) + "\n")
    else:
        WSHS.write_text("wash_id,customer_id,amount_cents,status,plan_tier\n" + "\n".join(wash_rows) + "\n")
        REBATES.write_text("wash_id,customer_id,amount_cents,plan_tier\n" + "\n".join(rebate_rows) + "\n")
    METHODS.write_text("plan_tier,rebate_enabled\n" + "\n".join(method_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows or ["2026-04-01 open", "2026-04-02 open", "2026-04-03 open"]) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse report plus summary outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone4:
    """Verify runtime methods.csv gating across undated and dated batches without weakening prior reconciliation rules."""

    def test_methods_gate_applies_to_undated_batches(self):
        """Disabled and missing method tiers should be unmatched even when base fields match."""
        write_inputs(
            [
                "WSHM401,CUST401,1000,COMPLETED,BASIC",
                "WSHM402,CUST402,2000,COMPLETED,PLUS",
                "WSHM403,CUST403,3000,COMPLETED,PRO",
            ],
            [
                "WSHM401,CUST401,1000,BASIC",
                "WSHM402,CUST402,2000,PL",
                "WSHM403,CUST403,3000,PR",
            ],
            [
                "BASIC,true",
                "PLUS,false",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED"]
        assert [row["plan_tier"] for row in rows] == ["BASIC", "", ""]
        assert summary == {"matched_count": 1, "matched_amount_cents": 1000, "unmatched_count": 2, "unmatched_amount_cents": 5000}

    def test_methods_parser_trims_and_normalizes_alias_rows(self):
        """Method rows should tolerate whitespace, casing, and aliases before gating."""
        write_inputs(
            [
                "WSHM411,CUST411,1500,COMPLETED,PLUS",
                "WSHM412,CUST412,1600,COMPLETED,PRO",
            ],
            [
                "WSHM411,CUST411,1500,pl",
                "WSHM412,CUST412,1600,PR",
            ],
            [
                " pl , TRUE ",
                " pr , true ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["plan_tier"] for row in rows] == ["PLUS", "PRO"]
        assert summary["matched_amount_cents"] == 3100

    def test_malformed_unsupported_and_non_true_method_rows_are_ineligible(self):
        """Only explicit true rows for supported canonical tiers should enable matching."""
        write_inputs(
            [
                "WSHM421,CUST421,500,COMPLETED,BASIC",
                "WSHM422,CUST422,600,COMPLETED,PLUS",
                "WSHM423,CUST423,700,COMPLETED,PRO",
            ],
            [
                "WSHM421,CUST421,500,BASIC",
                "WSHM422,CUST422,600,PL",
                "WSHM423,CUST423,700,PR",
            ],
            [
                "BASIC,yes",
                "VIP,true",
                "PLUS,",
                "PRO,false",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert [row["plan_tier"] for row in rows] == ["", "", ""]
        assert summary["unmatched_amount_cents"] == 1800

    def test_methods_gate_applies_with_dated_latest_wash_selection(self):
        """Methods eligibility should combine with open-date gating and latest wash_date selection."""
        write_inputs(
            [
                "WSHM431,CUST431,1100,COMPLETED,PLUS,2026-04-04",
                "WSHM431,CUST431,1100,COMPLETED,PLUS,2026-04-08",
                "WSHM432,CUST432,1200,COMPLETED,BASIC,2026-04-08",
            ],
            [
                "WSHM431,CUST431,1100,PL,2026-04-02",
                "WSHM431,CUST431,1100,PLUS,2026-04-02",
                "WSHM432,CUST432,1200,BS,2026-04-02",
            ],
            [
                "PLUS,true",
                "BASIC,false",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
                "2026-04-08 open",
            ],
            dated=True,
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["plan_tier"] for row in rows] == ["PLUS", "PLUS", ""]
        assert summary["matched_amount_cents"] == 2200
        assert summary["unmatched_amount_cents"] == 1200

    def test_method_gate_does_not_bypass_original_matching_fields(self):
        """An enabled method must not bypass amount, customer, status, or tier equality checks."""
        write_inputs(
            [
                "WSHM441,CUST441,900,COMPLETED,BASIC",
                "WSHM442,CUST442,1000,DRAFT,PLUS",
                "WSHM443,CUST443,1100,COMPLETED,BASIC",
            ],
            [
                "WSHM441,CUST441,901,BASIC",
                "WSHM442,CUST442,1000,PL",
                "WSHM443,CUST443,1100,PL",
            ],
            [
                "BASIC,true",
                "PLUS,true",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 3001

    def test_enabled_and_disabled_tiers_are_independent(self):
        """Disabling one canonical tier should not block other enabled tiers."""
        write_inputs(
            [
                "WSHM451,CUST451,100,COMPLETED,BASIC",
                "WSHM452,CUST452,200,COMPLETED,PLUS",
                "WSHM453,CUST453,300,COMPLETED,PRO",
            ],
            [
                "WSHM451,CUST451,100,BS",
                "WSHM452,CUST452,200,PL",
                "WSHM453,CUST453,300,PR",
            ],
            [
                "BASIC,true",
                "PLUS,false",
                "PRO,true",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["plan_tier"] for row in rows] == ["BASIC", "", "PRO"]
        assert summary["matched_amount_cents"] == 400
        assert summary["unmatched_amount_cents"] == 200
