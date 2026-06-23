"""Milestone 4 tests for methods-config gated payout reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
ORDERS = APP / "data" / "orders.csv"
PAYOUTS = APP / "data" / "payouts.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
METHODS = APP / "config" / "methods.csv"
REPORT = APP / "out" / "payout_report.csv"
SUMMARY = APP / "out" / "payout_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go payout reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 4 tests."""
    build_program()


def write_inputs(order_rows, payout_rows, calendar_rows, methods_rows):
    """Replace CSV inputs and config with a focused scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    ORDERS.write_text("order_id,seller_id,amount_cents,status,lane,ship_date\n" + "\n".join(order_rows) + "\n")
    PAYOUTS.write_text("order_id,seller_id,amount_cents,lane,payout_date\n" + "\n".join(payout_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    METHODS.write_text("lane,enabled\n" + "\n".join(methods_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse report rows plus summary JSON."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone4:
    """Methods config gate should filter eligible canonical lanes."""

    def test_only_enabled_lanes_match_after_alias_normalization(self):
        """Canonical lane must be enabled=true in methods.csv to be eligible."""
        write_inputs(
            [
                "INV401,CUST401,1100,SHIPPED,D2D,2026-05-05",
                "INV402,CUST402,1200,SHIPPED,LOCKER,2026-05-05",
                "INV403,CUST403,1300,SHIPPED,STORE,2026-05-05",
            ],
            [
                "INV401,CUST401,1100,DRP,2026-05-04",
                "INV402,CUST402,1200,PKU,2026-05-04",
                "INV403,CUST403,1300,RTL,2026-05-04",
            ],
            ["2026-05-04 open"],
            ["D2D,true", "LOCKER,false", "STORE,true"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert [r["lane"] for r in rows] == ["D2D", "", "STORE"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 2400,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1200,
        }

    def test_missing_lane_row_in_methods_is_ineligible(self):
        """Lane absent from methods.csv should be treated as disabled."""
        write_inputs(
            ["INV410,CUST410,900,SHIPPED,LOCKER,2026-05-10"],
            ["INV410,CUST410,900,PKU,2026-05-09"],
            ["2026-05-09 open"],
            ["D2D,true", "STORE,true"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["lane"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_malformed_or_non_boolean_methods_rows_do_not_enable_lane(self):
        """Malformed rows and non-true flags must not make a lane eligible."""
        write_inputs(
            ["INV420,CUST420,700,SHIPPED,LOCKER,2026-05-10"],
            ["INV420,CUST420,700,PKU,2026-05-09"],
            ["2026-05-09 open"],
            ["LOCKER,yes", "BROKENROW", "D2D,true"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["lane"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 700,
        }

    def test_methods_gate_applies_in_undated_mode_too(self):
        """When dates are absent, matching still requires methods-enabled lane."""
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        ORDERS.write_text("order_id,seller_id,amount_cents,status,lane\nINV430,CUST430,800,SHIPPED,D2D\n")
        PAYOUTS.write_text("order_id,seller_id,amount_cents,lane\nINV430,CUST430,800,DRP\n")
        METHODS.write_text("lane,enabled\nD2D,false\n")
        CALENDAR.write_text("2026-05-01 open\n")
        REPORT.unlink(missing_ok=True)
        SUMMARY.unlink(missing_ok=True)

        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["lane"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1

    def test_methods_gate_does_not_override_prior_date_rules(self):
        """Enabled lane alone is insufficient when payout date is closed/unlisted."""
        write_inputs(
            ["INV440,CUST440,1500,SHIPPED,STORE,2026-05-12"],
            ["INV440,CUST440,1500,RTL,2026-05-10"],
            ["2026-05-10 closed"],
            ["STORE,true"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["lane"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 1500

    def test_methods_enabled_parsing_is_case_and_whitespace_tolerant(self):
        """Lane names and enabled flags should be trimmed and case-insensitive."""
        write_inputs(
            ["INV450,CUST450,950,SHIPPED,LOCKER,2026-05-11"],
            ["INV450,CUST450,950,PKU,2026-05-10"],
            ["2026-05-10 open"],
            [" LOCKER , TrUe ", "D2D,false"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["lane"] == "LOCKER"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 950,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
