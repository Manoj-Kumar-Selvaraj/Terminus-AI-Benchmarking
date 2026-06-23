"""Milestone 4 verifier tests for hotel reservation credit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
RSVS = APP / "data" / "reservations.csv"
CREDITS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
METHODS = APP / "config" / "methods.csv"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go credit reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 4 tests."""
    build_program()


def write_inputs(reservation_rows, credit_rows, calendar_rows=None, dated=False):
    """Replace CSV inputs and optional calendar with a scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    rsv_header = "reservation_id,customer_id,amount_cents,status,channel" + (",due_date" if dated else "")
    crd_header = "reservation_id,customer_id,amount_cents,channel" + (",credit_date" if dated else "")
    RSVS.write_text(rsv_header + "\n" + "\n".join(reservation_rows) + "\n")
    CREDITS.write_text(crd_header + "\n" + "\n".join(credit_rows) + "\n")
    if calendar_rows is not None:
        CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_methods(rows):
    """Replace channel policy with enabled flags and priorities."""
    METHODS.write_text("channel,enabled,priority\n" + "\n".join(rows) + "\n")


def run_program():
    """Run the compiled program and parse its CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone3Regression:
    """Key M3 behaviours that must still pass after M4 changes."""

    def test_open_credit_date_gates_matching_and_latest_due_date_wins(self):
        """Open credit dates should gate matching and latest eligible due date should win."""
        write_inputs(
            [
                "RSV9301,CUST9301,1000,POSTED,ACH,2026-04-03",
                "RSV9301,CUST9301,1000,POSTED,CARD,2026-04-04",
                "RSV9302,CUST9302,2000,POSTED,CARD,2026-04-02",
            ],
            [
                "RSV9301,CUST9301,1000,CC,2026-04-02",
                "RSV9302,CUST9302,2000,CC,2026-04-04",
            ],
            ["2026-04-02 open", "2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[0]["channel"] == "CARD"
        assert summary["matched_amount_cents"] == 1000
        assert summary["unmatched_amount_cents"] == 2000

    def test_closed_credit_date_is_not_eligible(self):
        """A credit whose date is listed as closed must not match."""
        write_inputs(
            ["RSV9601,CUST9601,1000,POSTED,CARD,2026-04-10"],
            ["RSV9601,CUST9601,1000,CC,2026-04-05"],
            ["2026-04-05 closed"],
            dated=True,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["unmatched_count"] == 1

    def test_undated_csv_without_date_columns_preserves_matching(self):
        """Older CSVs without date columns should keep the prior matching behavior."""
        write_inputs(
            ["OLD9001,CUST9001,3200,POSTED,WIRE"],
            ["OLD9001,CUST9001,3200,WIR"],
            dated=False,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["channel"] == "WIRE"
        assert summary["matched_amount_cents"] == 3200

    def test_reservation_without_due_date_is_not_eligible(self):
        """A reservation with an empty due_date cannot be consumed in dated mode."""
        write_inputs(
            ["RSV9801,CUST9801,700,POSTED,WIRE,"],
            ["RSV9801,CUST9801,700,WIR,2026-04-04"],
            ["2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0


class TestMilestone4:
    """Config-driven channel policy and ANY channel ranking."""

    def test_disabled_channel_rejects_otherwise_valid_credit(self):
        """Disabled methods.csv channels must not match even with valid ids and aliases."""
        write_methods(["ACH,true,2", "CARD,false,1", "WIRE,true,3"])
        write_inputs(
            ["CFG1001,CUST1001,1200,POSTED,CARD,2026-04-10"],
            ["CFG1001,CUST1001,1200,CC,2026-04-05"],
            ["2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1200,
        }

    def test_any_latest_due_date_wins_before_priority_and_row_order(self):
        """ANY must choose the latest eligible due_date before priority or row order."""
        write_methods(["ACH,true,1", "CARD,true,9", "WIRE,true,9"])
        write_inputs(
            [
                "ANY1501,CUST1501,600,POSTED,ACH,2026-04-06",
                "ANY1501,CUST1501,600,POSTED,CARD,2026-04-10",
            ],
            ["ANY1501,CUST1501,600,ANY,2026-04-04"],
            ["2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["channel"] == "CARD"
        assert summary["matched_count"] == 1

    def test_methods_enabled_values_are_trimmed_and_case_insensitive(self):
        """methods.csv enabled flags must accept TRUE, True, and padded values."""
        write_methods(["ACH, TRUE ,5", "CARD,False,1", "WIRE,true,3"])
        write_inputs(
            ["CFG1101,CUST1101,900,POSTED,ACH,2026-04-10"],
            ["CFG1101,CUST1101,900,ACH,2026-04-05"],
            ["2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["channel"] == "ACH"
        assert summary["matched_count"] == 1

    def test_any_same_date_uses_config_priority_before_reservation_order(self):
        """ANY ties on due date should use configured priority before reservation row order."""
        write_methods(["ACH,true,5", "CARD,true,1", "WIRE,true,3"])
        write_inputs(
            [
                "ANY2001,CUST2001,700,POSTED,ACH,2026-04-08",
                "ANY2001,CUST2001,700,POSTED,WIRE,2026-04-08",
                "ANY2001,CUST2001,700,POSTED,CARD,2026-04-08",
            ],
            ["ANY2001,CUST2001,700,ANY,2026-04-04"],
            ["2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["channel"] == "CARD"
        assert summary["matched_count"] == 1

    def test_any_equal_priority_tie_uses_earliest_reservation_row(self):
        """ANY ties on date and priority should visibly choose the earliest reservation row."""
        write_methods(["ACH,true,1", "CARD,true,1", "WIRE,true,9"])
        write_inputs(
            [
                "ANY3001,CUST3001,800,POSTED,ACH,2026-04-09",
                "ANY3001,CUST3001,800,POSTED,CARD,2026-04-09",
            ],
            ["ANY3001,CUST3001,800,ANY,2026-04-04"],
            ["2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["channel"] == "ACH"
        assert summary["matched_amount_cents"] == 800

    def test_any_consumes_selected_row_and_next_credit_uses_next_best(self):
        """ANY matching should consume by row position and rerank remaining candidates."""
        write_methods(["ACH,true,1", "CARD,true,2", "WIRE,true,3"])
        write_inputs(
            [
                "ANY4001,CUST4001,500,POSTED,ACH,2026-04-07",
                "ANY4001,CUST4001,500,POSTED,CARD,2026-04-07",
            ],
            [
                "ANY4001,CUST4001,500,ANY,2026-04-04",
                "ANY4001,CUST4001,500,ANY,2026-04-04",
                "ANY4001,CUST4001,500,ANY,2026-04-04",
            ],
            ["2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["channel"] for row in rows] == ["ACH", "CARD", ""]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1000,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_non_any_still_requires_exact_canonical_channel_under_config_policy(self):
        """Config policy must not turn named channel credits into wildcard matches."""
        write_methods(["ACH,true,1", "CARD,true,2", "WIRE,true,3"])
        write_inputs(
            ["CFG5001,CUST5001,900,POSTED,ACH,2026-04-10"],
            ["CFG5001,CUST5001,900,CARD,2026-04-05"],
            ["2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["unmatched_amount_cents"] == 900

    def test_malformed_priority_ranks_after_numeric_priorities(self):
        """A malformed priority value should rank after all numeric priorities."""
        write_methods(["ACH,true,fast", "CARD,true,1", "WIRE,true,3"])
        write_inputs(
            [
                "ANY6001,CUST6001,640,POSTED,ACH,2026-04-09",
                "ANY6001,CUST6001,640,POSTED,CARD,2026-04-09",
            ],
            ["ANY6001,CUST6001,640,ANY,2026-04-04"],
            ["2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["channel"] == "CARD"
        assert summary["matched_count"] == 1

    def test_undated_csv_honors_disabled_channel_policy(self):
        """Undated CSVs should still honour methods.csv enabled flags."""
        write_methods(["ACH,true,1", "CARD,false,2", "WIRE,true,3"])
        write_inputs(
            ["OLD9701,CUST9701,450,POSTED,CARD"],
            ["OLD9701,CUST9701,450,CC"],
            dated=False,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert summary["unmatched_amount_cents"] == 450

    def test_any_with_closed_credit_date_is_ineligible(self):
        """ANY must still respect open credit_date gates together with channel policy."""
        write_methods(["ACH,true,1", "CARD,true,2", "WIRE,true,3"])
        write_inputs(
            [
                "ANY7001,CUST7001,550,POSTED,ACH,2026-04-10",
                "ANY7001,CUST7001,550,POSTED,CARD,2026-04-10",
            ],
            ["ANY7001,CUST7001,550,ANY,2026-04-05"],
            ["2026-04-05 closed"],
            dated=True,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_any_emits_canonical_channel_not_any_in_report(self):
        """Matched ANY credits must emit the selected reservation channel, never 'ANY'."""
        write_methods(["ACH,true,1", "CARD,true,2", "WIRE,true,3"])
        write_inputs(
            ["ANY8001,CUST8001,300,POSTED,ACH,2026-04-10"],
            ["ANY8001,CUST8001,300,ANY,2026-04-05"],
            ["2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["channel"] == "ACH"
        assert rows[0]["channel"] != "ANY"
        assert summary["matched_amount_cents"] == 300
