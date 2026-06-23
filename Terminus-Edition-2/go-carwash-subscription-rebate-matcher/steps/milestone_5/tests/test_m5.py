"""Milestone 5 verifier tests for customer-specific rebate limits."""

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
LIMITS = APP / "config" / "customer_limits.csv"
REPORT = APP / "out" / "wash_rebate_report.csv"
SUMMARY = APP / "out" / "wash_rebate_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go reconciliation CLI for milestone 5 tests."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 5 tests."""
    build_program()


def write_inputs(wash_rows, rebate_rows, method_rows, limit_rows, calendar_rows=None, dated=False):
    """Replace data, methods, limits, and calendar inputs for a milestone 5 scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    if dated:
        WSHS.write_text("wash_id,customer_id,amount_cents,status,plan_tier,wash_date\n" + "\n".join(wash_rows) + "\n")
        REBATES.write_text("wash_id,customer_id,amount_cents,plan_tier,rebate_date\n" + "\n".join(rebate_rows) + "\n")
    else:
        WSHS.write_text("wash_id,customer_id,amount_cents,status,plan_tier\n" + "\n".join(wash_rows) + "\n")
        REBATES.write_text("wash_id,customer_id,amount_cents,plan_tier\n" + "\n".join(rebate_rows) + "\n")
    METHODS.write_text("plan_tier,rebate_enabled\n" + "\n".join(method_rows) + "\n")
    LIMITS.write_text("customer_id,plan_tier,max_rebate_cents,enabled\n" + "\n".join(limit_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows or ["2026-04-01 open", "2026-04-02 open", "2026-04-03 open"]) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse report plus summary outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone5:
    """Verify donor-like customer limits combine with methods, dates, aliases, and consumption rules."""

    def test_customer_limits_apply_to_undated_amounts(self):
        """A rebate amount must be less than or equal to the enabled customer/tier maximum."""
        write_inputs(
            [
                "WSHL501,CUST501,1000,COMPLETED,BASIC",
                "WSHL502,CUST502,2500,COMPLETED,PLUS",
                "WSHL503,CUST503,3000,COMPLETED,PRO",
            ],
            [
                "WSHL501,CUST501,1000,BASIC",
                "WSHL502,CUST502,2500,PL",
                "WSHL503,CUST503,3000,PR",
            ],
            ["BASIC,true", "PLUS,true", "PRO,true"],
            [
                "CUST501,BASIC,1000,true",
                "CUST502,PLUS,2400,true",
                "CUST503,PRO,3000,false",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED"]
        assert [row["plan_tier"] for row in rows] == ["BASIC", "", ""]
        assert summary == {"matched_count": 1, "matched_amount_cents": 1000, "unmatched_count": 2, "unmatched_amount_cents": 5500}

    def test_customer_limit_parser_trims_and_normalizes_alias_tiers(self):
        """Customer limits should trim ids, normalize aliases, and parse enabled=true case-insensitively."""
        write_inputs(
            [
                "WSHL511,CUST511,1800,COMPLETED,PLUS",
                "WSHL512,CUST512,1900,COMPLETED,PRO",
            ],
            [
                "WSHL511,CUST511,1800,PL",
                "WSHL512,CUST512,1900,PR",
            ],
            ["PLUS,true", "PRO,true"],
            [
                " CUST511 , pl , 1800 , TRUE ",
                " CUST512 , pr , 2000 , true ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["plan_tier"] for row in rows] == ["PLUS", "PRO"]
        assert summary["matched_amount_cents"] == 3700

    def test_last_customer_limit_row_is_authoritative(self):
        """Later policy rows for the same customer and tier should override earlier rows."""
        write_inputs(
            [
                "WSHL521,CUST521,900,COMPLETED,BASIC",
                "WSHL522,CUST522,800,COMPLETED,PLUS",
            ],
            [
                "WSHL521,CUST521,900,BS",
                "WSHL522,CUST522,800,PL",
            ],
            ["BASIC,true", "PLUS,true"],
            [
                "CUST521,BASIC,900,true",
                "CUST521,BASIC,900,false",
                "CUST522,PLUS,1200,false",
                "CUST522,PLUS,1200,true",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert [row["plan_tier"] for row in rows] == ["", "PLUS"]
        assert summary["matched_amount_cents"] == 800
        assert summary["unmatched_amount_cents"] == 900

    def test_invalid_customer_limit_rows_make_that_customer_tier_ineligible(self):
        """Blank, non-integer, negative, and non-true limit values should not enable matches."""
        write_inputs(
            [
                "WSHL531,CUST531,100,COMPLETED,BASIC",
                "WSHL532,CUST532,200,COMPLETED,PLUS",
                "WSHL533,CUST533,300,COMPLETED,PRO",
                "WSHL534,CUST534,400,COMPLETED,BASIC",
            ],
            [
                "WSHL531,CUST531,100,BS",
                "WSHL532,CUST532,200,PL",
                "WSHL533,CUST533,300,PR",
                "WSHL534,CUST534,400,BASIC",
            ],
            ["BASIC,true", "PLUS,true", "PRO,true"],
            [
                "CUST531,BASIC,,true",
                "CUST532,PLUS,abc,true",
                "CUST533,PRO,-1,true",
                "CUST534,BASIC,400,yes",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 1000

    def test_limits_apply_with_dated_latest_selection_and_consumption(self):
        """Customer limits should combine with dated latest-row selection and physical row consumption."""
        write_inputs(
            [
                "WSHL541,CUST541,700,COMPLETED,PLUS,2026-04-04",
                "WSHL541,CUST541,700,COMPLETED,PLUS,2026-04-09",
                "WSHL542,CUST542,900,COMPLETED,BASIC,2026-04-05",
            ],
            [
                "WSHL541,CUST541,700,PL,2026-04-01",
                "WSHL541,CUST541,700,PLUS,2026-04-01",
                "WSHL542,CUST542,900,BS,2026-04-01",
            ],
            ["PLUS,true", "BASIC,true"],
            [
                "CUST541,PLUS,700,true",
                "CUST542,BASIC,800,true",
            ],
            [
                "2026-04-01 open",
                "2026-04-04 open",
                "2026-04-05 open",
                "2026-04-09 open",
            ],
            dated=True,
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["plan_tier"] for row in rows] == ["PLUS", "PLUS", ""]
        assert summary["matched_amount_cents"] == 1400
        assert summary["unmatched_amount_cents"] == 900

    def test_methods_gate_still_blocks_when_customer_limit_allows(self):
        """A valid customer limit must not bypass disabled methods eligibility."""
        write_inputs(
            ["WSHL551,CUST551,1200,COMPLETED,PRO"],
            ["WSHL551,CUST551,1200,PR"],
            ["PRO,false"],
            ["CUST551,PRO,1200,true"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["plan_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 1200

    def test_customer_limit_does_not_bypass_base_matching(self):
        """A valid limit must not bypass amount, customer, status, or tier equality checks."""
        write_inputs(
            [
                "WSHL561,CUST561,500,COMPLETED,BASIC",
                "WSHL562,CUST562,600,DRAFT,PLUS",
                "WSHL563,CUST563,700,COMPLETED,PRO",
            ],
            [
                "WSHL561,CUST561,501,BS",
                "WSHL562,CUST562,600,PL",
                "WSHL563,CUST999,700,PR",
            ],
            ["BASIC,true", "PLUS,true", "PRO,true"],
            [
                "CUST561,BASIC,1000,true",
                "CUST562,PLUS,1000,true",
                "CUST999,PRO,1000,true",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 1801
