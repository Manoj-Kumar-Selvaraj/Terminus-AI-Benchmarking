"""Milestone 4 verifier tests for route policy and ANY credit matching."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
ORDERS = APP / "data" / "orders.csv"
CREDITS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
POLICY = APP / "config" / "route_policy.csv"
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
    assert BIN.exists()


def write_inputs(order_rows, credit_rows, calendar_rows=None, policy_rows=None):
    """Replace dated CSV inputs and route policy with a milestone 4 scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    ORDERS.write_text("order_id,cafe_id,amount_cents,status,route,bake_date\n" + "\n".join(order_rows) + "\n")
    CREDITS.write_text("order_id,cafe_id,amount_cents,route,credit_date\n" + "\n".join(credit_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows or ["2026-04-02 open", "2026-04-03 open"]) + "\n")
    POLICY.write_text(
        "route,enabled,priority\n"
        + "\n".join(policy_rows or ["LOCAL,Y,20", "REGIONAL,Y,10", "EXPORT,Y,30"])
        + "\n"
    )
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse its CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone4:
    """Route policy gates, ANY ranking, and canonical route output."""

    def test_disabled_policy_route_rejects_exact_and_any_matches(self):
        write_inputs(
            [
                "ORD-POL-1,CAFE-P,400,FULFILLED,EXPORT,2026-04-04",
                "ORD-POL-2,CAFE-P,500,FULFILLED,EXPORT,2026-04-04",
            ],
            [
                "ORD-POL-1,CAFE-P,400,EXP,2026-04-02",
                "ORD-POL-2,CAFE-P,500,ANY,2026-04-02",
            ],
            policy_rows=["LOCAL,Y,20", "REGIONAL,Y,10", "EXPORT,N,30"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert [row["route"] for row in rows] == ["", ""]
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 2,
            "unmatched_amount_cents": 900,
        }

    def test_policy_route_and_enabled_values_trim_and_case_fold(self):
        write_inputs(
            [
                "ORD-POL-TRIM,CAFE-P,300,FULFILLED,regional,2026-04-04",
                "ORD-POL-DIS,CAFE-P,400,FULFILLED,export,2026-04-04",
            ],
            [
                "ORD-POL-TRIM,CAFE-P,300,REG,2026-04-02",
                "ORD-POL-DIS,CAFE-P,400,EXP,2026-04-02",
            ],
            policy_rows=[" local , y ,20", " regional , y ,10", " export , n ,30"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["route"] for row in rows] == ["REGIONAL", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 300,
            "unmatched_count": 1,
            "unmatched_amount_cents": 400,
        }

    def test_unconfigured_policy_route_rejects_exact_and_any_matches(self):
        write_inputs(
            [
                "ORD-NOPOL-1,CAFE-P,300,FULFILLED,EXPORT,2026-04-04",
                "ORD-NOPOL-2,CAFE-P,400,FULFILLED,EXPORT,2026-04-04",
            ],
            [
                "ORD-NOPOL-1,CAFE-P,300,EXP,2026-04-02",
                "ORD-NOPOL-2,CAFE-P,400,ANY,2026-04-02",
            ],
            policy_rows=["LOCAL,Y,20", "REGIONAL,Y,10"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert [row["route"] for row in rows] == ["", ""]
        assert summary["unmatched_amount_cents"] == 700

    def test_any_uses_latest_bake_date_before_route_priority(self):
        write_inputs(
            [
                "ORD-ANY,CAFE-A,600,FULFILLED,REGIONAL,2026-04-04",
                "ORD-ANY,CAFE-A,600,FULFILLED,LOCAL,2026-04-06",
                "ORD-ANY,CAFE-A,600,FULFILLED,REGIONAL,2026-04-04",
            ],
            [
                "ORD-ANY,CAFE-A,600,ANY,2026-04-02",
                "ORD-ANY,CAFE-A,600,ANY,2026-04-03",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["route"] for row in rows] == ["LOCAL", "REGIONAL"]
        assert summary["matched_amount_cents"] == 1200

    def test_any_same_date_uses_priority_then_order_row(self):
        write_inputs(
            [
                "ORD-PRI,CAFE-A,300,FULFILLED,LOCAL,2026-04-05",
                "ORD-PRI,CAFE-A,300,FULFILLED,REGIONAL,2026-04-05",
                "ORD-PRI,CAFE-A,300,FULFILLED,EXPORT,2026-04-05",
            ],
            [
                "ORD-PRI,CAFE-A,300,ANY,2026-04-02",
                "ORD-PRI,CAFE-A,300,ANY,2026-04-02",
            ],
            policy_rows=["LOCAL,Y,10", "REGIONAL,Y,10", "EXPORT,Y,30"],
        )
        rows, summary = run_program()

        assert [row["route"] for row in rows] == ["LOCAL", "REGIONAL"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_concrete_route_still_requires_exact_canonical_route(self):
        write_inputs(
            ["ORD-EXACT,CAFE-X,700,FULFILLED,REGIONAL,2026-04-04"],
            ["ORD-EXACT,CAFE-X,700,LOC,2026-04-02"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["route"] == ""
        assert summary["unmatched_amount_cents"] == 700

    def test_matched_concrete_route_reports_credit_canonical_route(self):
        write_inputs(
            ["ORD-OUT,CAFE-O,800,FULFILLED,regional,2026-04-04"],
            ["ORD-OUT,CAFE-O,800,REG,2026-04-02"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["route"] == "REGIONAL"
        assert summary["matched_amount_cents"] == 800
