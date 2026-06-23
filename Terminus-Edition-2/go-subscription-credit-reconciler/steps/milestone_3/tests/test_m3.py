"""Milestone 3 verifier tests for subscription credit date controls."""

import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
INVOICES = APP / "data" / "subscriptions.csv"
PAYMENTS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go reconciliation CLI for the current source tree."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


def write_inputs(subscription_rows, credit_rows, calendar_rows):
    """Replace CSV and calendar inputs with a focused date-control scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    INVOICES.write_text(
        "subscription_id,account_id,amount_cents,status,channel,due_date\n" + "\n".join(subscription_rows) + "\n"
    )
    PAYMENTS.write_text(
        "subscription_id,account_id,amount_cents,channel,credit_date\n" + "\n".join(credit_rows) + "\n"
    )
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_raw_inputs(subscription_header, subscription_rows, credit_header, credit_rows, calendar_rows):
    """Replace inputs with explicit headers for backward-compatibility scenarios."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    INVOICES.write_text(subscription_header + "\n" + "\n".join(subscription_rows) + "\n")
    PAYMENTS.write_text(credit_header + "\n" + "\n".join(credit_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone3:
    """Verify credit date gates and latest eligible subscription selection."""

    def test_open_credit_dates_and_latest_due_date_selection(self):
        """Open calendar dates should gate matching and latest eligible due date should win."""
        build_program()
        write_inputs(
            [
                "INV9101,CUST9101,1000,POSTED,ACH,2026-04-03",
                "INV9101,CUST9101,1000,POSTED,WIRE,2026-04-04",
                "INV9102,CUST9102,2000,POSTED,CARD,2026-04-02",
                "INV9103,CUST9103,3000,POSTED,ACH,2026-04-05",
                "INV9104,CUST9104,4000,POSTED,WIRE,2026-04-05",
            ],
            [
                "INV9101,CUST9101,1000,WIR,2026-04-02",
                "INV9102,CUST9102,2000,CC,2026-04-04",
                "INV9103,CUST9103,3000,ACH,2026-04-06",
                "INV9104,CUST9104,4000,WIRE,2026-04-07",
            ],
            [
                "2026-04-02 open",
                "2026-04-03 closed",
                "2026-04-04 open",
                "2026-04-05 open",
                "2026-04-06 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert rows[0]["channel"] == "WIRE"
        assert [row["channel"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_due_date_tie_uses_subscription_input_order_and_consumption(self):
        """Same-date candidates should use subscription order and still respect consumption."""
        build_program()
        write_inputs(
            [
                "INV9201,CUST9201,500,POSTED,CARD,2026-04-05",
                "INV9201,CUST9201,500,POSTED,CARD,2026-04-05",
                "INV9202,CUST9202,700,POSTED,ACH,2026-04-05",
            ],
            [
                "INV9201,CUST9201,500,CC,2026-04-04",
                "INV9201,CUST9201,500,CC,2026-04-04",
                "INV9201,CUST9201,500,CC,2026-04-04",
                "INV9202,CUST9202,700,ACH,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["channel"] for row in rows] == ["CARD", "CARD", "", "ACH"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_due_date_is_chosen_before_older_subscription_is_used(self):
        """A later eligible due date should be consumed before an older eligible subscription."""
        build_program()
        write_inputs(
            [
                "INV9301,CUST9301,800,POSTED,ACH,2026-04-01",
                "INV9301,CUST9301,800,POSTED,ACH,2026-04-03",
            ],
            [
                "INV9301,CUST9301,800,ACH,2026-04-01",
                "INV9301,CUST9301,800,ACH,2026-04-02",
            ],
            [
                "2026-04-01 open",
                "2026-04-02 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["channel"] for row in rows] == ["ACH", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_closed_credit_date_is_not_open(self):
        """A credit date present in the calendar as closed should not be eligible."""
        build_program()
        write_inputs(
            [
                "INV9351,CUST9351,900,POSTED,ACH,2026-04-10",
            ],
            [
                "INV9351,CUST9351,900,ACH,2026-04-03",
            ],
            [
                "2026-04-03 closed",
                "2026-04-10 open",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 900,
        }

    def test_older_rows_without_date_columns_are_readable_but_not_eligible(self):
        """Old CSV shapes without due_date or credit_date should not crash and should not match."""
        build_program()
        write_raw_inputs(
            "subscription_id,account_id,amount_cents,status,channel",
            [
                "INV9401,CUST9401,600,POSTED,ACH",
                "INV9402,CUST9402,700,POSTED,CARD",
            ],
            "subscription_id,account_id,amount_cents,channel",
            [
                "INV9401,CUST9401,600,ACH",
                "INV9402,CUST9402,700,CC",
            ],
            [
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert [row["channel"] for row in rows] == ["", ""]
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 2,
            "unmatched_amount_cents": 1300,
        }
