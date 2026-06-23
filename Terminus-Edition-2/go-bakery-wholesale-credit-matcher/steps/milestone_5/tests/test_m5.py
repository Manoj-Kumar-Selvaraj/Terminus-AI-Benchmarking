"""Milestone 5 verifier tests for cafe limits and route blackouts."""

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
LIMITS = APP / "config" / "cafe_limits.csv"
BLACKOUTS = APP / "config" / "route_blackouts.csv"
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
    """Compile the Go reconciliation CLI once for all milestone 5 tests."""
    build_program()
    assert BIN.exists()


def write_inputs(order_rows, credit_rows, calendar_rows=None, policy_rows=None, limit_rows=None, blackout_rows=None):
    """Replace dated CSV inputs and milestone 5 config files."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    ORDERS.write_text("order_id,cafe_id,amount_cents,status,route,bake_date\n" + "\n".join(order_rows) + "\n")
    CREDITS.write_text("order_id,cafe_id,amount_cents,route,credit_date\n" + "\n".join(credit_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows or ["2026-04-02 open", "2026-04-03 open"]) + "\n")
    POLICY.write_text(
        "route,enabled,priority\n"
        + "\n".join(policy_rows or ["LOCAL,Y,20", "REGIONAL,Y,10", "EXPORT,Y,30"])
        + "\n"
    )
    LIMITS.write_text(
        "cafe_id,effective_date,max_daily_amount_cents\n"
        + "\n".join(limit_rows or ["CAFE-A,2026-01-01,10000", "CAFE-B,2026-01-01,900"])
        + "\n"
    )
    BLACKOUTS.write_text("cafe_id,route,start_date,end_date\n" + "\n".join(blackout_rows or []) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_legacy_inputs(order_rows, credit_rows, limit_rows=None, blackout_rows=None):
    """Replace older undated CSV inputs while still writing milestone 5 config files."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    ORDERS.write_text("order_id,cafe_id,amount_cents,status,route\n" + "\n".join(order_rows) + "\n")
    CREDITS.write_text("order_id,cafe_id,amount_cents,route\n" + "\n".join(credit_rows) + "\n")
    CALENDAR.write_text("2026-04-02 open\n")
    POLICY.write_text("route,enabled,priority\nLOCAL,Y,20\nREGIONAL,Y,10\nEXPORT,Y,30\n")
    LIMITS.write_text(
        "cafe_id,effective_date,max_daily_amount_cents\n"
        + "\n".join(limit_rows or ["CAFE-LEGACY,2026-01-01,1"])
        + "\n"
    )
    BLACKOUTS.write_text(
        "cafe_id,route,start_date,end_date\n"
        + "\n".join(blackout_rows or ["CAFE-LEGACY,REGIONAL,2026-01-01,2026-12-31"])
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


class TestMilestone5:
    """Cafe daily caps, effective limits, and route blackout gates."""

    def test_legacy_schema_ignores_limits_and_blackouts(self):
        write_legacy_inputs(
            ["ORD-LEGACY,CAFE-LEGACY,500,FULFILLED,REGIONAL"],
            ["ORD-LEGACY,CAFE-LEGACY,500,REG"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["route"] == "REGIONAL"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 500,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_cafe_daily_limit_rejects_without_consuming_order_or_budget(self):
        write_inputs(
            [
                "ORD-LIM-1,CAFE-B,600,FULFILLED,REGIONAL,2026-04-04",
                "ORD-LIM-2,CAFE-B,400,FULFILLED,REGIONAL,2026-04-04",
                "ORD-LIM-1,CAFE-B,600,FULFILLED,REGIONAL,2026-04-04",
            ],
            [
                "ORD-LIM-1,CAFE-B,600,REG,2026-04-02",
                "ORD-LIM-2,CAFE-B,400,REG,2026-04-02",
                "ORD-LIM-1,CAFE-B,600,REG,2026-04-03",
            ],
            ["2026-04-02 open", "2026-04-03 open"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["route"] for row in rows] == ["REGIONAL", "", "REGIONAL"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1200,
            "unmatched_count": 1,
            "unmatched_amount_cents": 400,
        }

    def test_limit_rejection_does_not_consume_any_order_or_budget(self):
        """A limit-rejected ANY credit should leave its candidate order available for a later date."""
        write_inputs(
            [
                "ORD-CAP-1,CAFE-D,500,FULFILLED,LOCAL,2026-04-05",
                "ORD-CAP-2,CAFE-D,400,FULFILLED,REGIONAL,2026-04-05",
            ],
            [
                "ORD-CAP-1,CAFE-D,500,ANY,2026-04-02",
                "ORD-CAP-2,CAFE-D,400,ANY,2026-04-02",
                "ORD-CAP-2,CAFE-D,400,ANY,2026-04-03",
            ],
            ["2026-04-02 open", "2026-04-03 open"],
            limit_rows=["CAFE-D,2026-01-01,500"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["route"] for row in rows] == ["LOCAL", "", "REGIONAL"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 900,
            "unmatched_count": 1,
            "unmatched_amount_cents": 400,
        }

    def test_latest_effective_limit_and_same_date_file_order_win(self):
        write_inputs(
            [
                "ORD-LIM-3,CAFE-C,700,FULFILLED,LOCAL,2026-04-04",
                "ORD-LIM-4,CAFE-C,600,FULFILLED,LOCAL,2026-04-04",
            ],
            [
                "ORD-LIM-3,CAFE-C,700,LOC,2026-04-02",
                "ORD-LIM-4,CAFE-C,600,LOC,2026-04-02",
            ],
            limit_rows=["CAFE-C,2026-01-01,700", "CAFE-C,2026-04-01,1200", "CAFE-C,2026-04-01,1300"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert summary["matched_amount_cents"] == 1300

    def test_missing_dated_limit_blocks_match(self):
        write_inputs(
            ["ORD-NOLIM,CAFE-NO-LIMIT,500,FULFILLED,LOCAL,2026-04-04"],
            ["ORD-NOLIM,CAFE-NO-LIMIT,500,LOC,2026-04-02"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["route"] == ""
        assert summary["unmatched_amount_cents"] == 500

    def test_blackout_filters_candidates_before_any_ranking(self):
        write_inputs(
            [
                "ORD-BLK,CAFE-A,500,FULFILLED,REGIONAL,2026-04-06",
                "ORD-BLK,CAFE-A,500,FULFILLED,LOCAL,2026-04-05",
            ],
            ["ORD-BLK,CAFE-A,500,ANY,2026-04-02"],
            blackout_rows=["CAFE-A,REGIONAL,2026-04-06,2026-04-06", "CAFE-A,REGIONAL,2026-04-09,2026-04-01"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["route"] == "LOCAL"
        assert summary["matched_amount_cents"] == 500

    def test_blackout_route_trim_and_case_folding(self):
        write_inputs(
            [
                "ORD-CF,CAFE-A,500,FULFILLED,REGIONAL,2026-04-05",
                "ORD-CF,CAFE-A,500,FULFILLED,LOCAL,2026-04-04",
            ],
            ["ORD-CF,CAFE-A,500,ANY,2026-04-02"],
            blackout_rows=["CAFE-A, Regional ,2026-04-01,2026-04-30"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["route"] == "LOCAL"
        assert summary["matched_amount_cents"] == 500

    def test_blank_blackout_dates_are_ignored(self):
        write_inputs(
            [
                "ORD-BLANK,CAFE-A,450,FULFILLED,REGIONAL,2026-04-05",
                "ORD-BLANK,CAFE-A,450,FULFILLED,LOCAL,2026-04-04",
            ],
            ["ORD-BLANK,CAFE-A,450,ANY,2026-04-02"],
            blackout_rows=["CAFE-A,REGIONAL,,2026-04-05", "CAFE-A,REGIONAL,2026-04-04,"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["route"] == "REGIONAL"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 450,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_unknown_blackout_routes_are_ignored(self):
        write_inputs(
            [
                "ORD-UNK-BLK,CAFE-A,350,FULFILLED,REGIONAL,2026-04-05",
                "ORD-UNK-BLK,CAFE-A,350,FULFILLED,LOCAL,2026-04-04",
            ],
            ["ORD-UNK-BLK,CAFE-A,350,ANY,2026-04-02"],
            blackout_rows=["CAFE-A,WHOLESALE,2026-04-01,2026-04-30"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["route"] == "REGIONAL"
        assert summary["matched_amount_cents"] == 350

    def test_blank_cafe_blackout_rows_are_ignored(self):
        write_inputs(
            ["ORD-BLANK-CAFE,CAFE-A,250,FULFILLED,REGIONAL,2026-04-05"],
            ["ORD-BLANK-CAFE,CAFE-A,250,ANY,2026-04-02"],
            blackout_rows=[",REGIONAL,2026-04-01,2026-04-30"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["route"] == "REGIONAL"
        assert summary["matched_amount_cents"] == 250
