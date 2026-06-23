"""Milestone 3 verifier tests for dated travel booking adjustment matching CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
BOOKS = APP / "data" / "bookings.csv"
ADJUSTMENTS = APP / "data" / "adjustments.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "adjustment_report.csv"
SUMMARY = APP / "out" / "adjustment_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    build_program()


def write_inputs(booking_rows, adjustment_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated adjustment scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    BOOKS.write_text("booking_id,customer_id,amount_cents,status,channel,due_date\n" + "\n".join(booking_rows) + "\n")
    ADJUSTMENTS.write_text("booking_id,customer_id,amount_cents,channel,adjustment_date\n" + "\n".join(adjustment_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse its CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone3:
    """Date gates and latest eligible booking selection for adjustments."""

    def test_open_adjustment_date_and_latest_due_date_win(self):
        """Open adjustment dates should gate matching and latest eligible due date should win."""
        write_inputs(
            [
                "BOOK9301,CUST9301,1000,POSTED,ACH,2026-04-03",
                "BOOK9301,CUST9301,1000,POSTED,CARD,2026-04-04",
                "BOOK9302,CUST9302,2000,POSTED,CARD,2026-04-02",
                "BOOK9303,CUST9303,3000,POSTED,WIRE,2026-04-05",
                "BOOK9304,CUST9304,4000,POSTED,WIRE,2026-04-05",
            ],
            [
                "BOOK9301,CUST9301,1000,CC,2026-04-02",
                "BOOK9302,CUST9302,2000,CC,2026-04-04",
                "BOOK9303,CUST9303,3000,WIR,2026-04-06",
                "BOOK9304,CUST9304,4000,WIRE,2026-04-07",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
                "2026-04-05 open",
                "2026-04-06 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert rows[0]["channel"] == "CARD"
        assert [row["channel"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_due_date_tie_uses_booking_order_and_consumption(self):
        """Same-date candidates should use booking order and still enforce consumption."""
        write_inputs(
            [
                "BOOK9401,CUST9401,500,POSTED,CARD,2026-04-05",
                "BOOK9401,CUST9401,500,POSTED,CARD,2026-04-05",
                "BOOK9402,CUST9402,700,POSTED,ACH,2026-04-05",
            ],
            [
                "BOOK9401,CUST9401,500,CC,2026-04-04",
                "BOOK9401,CUST9401,500,CC,2026-04-04",
                "BOOK9401,CUST9401,500,CC,2026-04-04",
                "BOOK9402,CUST9402,700,ACH,2026-04-05",
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

    def test_latest_due_date_wins_before_older_booking_is_used(self):
        """A later eligible due date should be consumed before an older eligible booking."""
        write_inputs(
            [
                "BOOK9501,CUST9501,800,POSTED,CARD,2026-04-03",
                "BOOK9501,CUST9501,800,POSTED,CARD,2026-04-06",
            ],
            [
                "BOOK9501,CUST9501,800,CC,2026-04-02",
                "BOOK9501,CUST9501,800,CC,2026-04-04",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["channel"] for row in rows] == ["CARD", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_closed_adjustment_date_is_not_eligible(self):
        """A adjustment whose date is listed as closed must not match."""
        write_inputs(
            ["BOOK9601,CUST9601,1000,POSTED,CARD,2026-04-10"],
            ["BOOK9601,CUST9601,1000,CC,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_adjustment_date_is_not_eligible(self):
        """A adjustment date absent from the calendar must not be treated as open."""
        write_inputs(
            ["BOOK9651,CUST9651,500,POSTED,CARD,2026-04-30"],
            ["BOOK9651,CUST9651,500,CC,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_adjustment_date_is_not_eligible(self):
        """A adjustment with an empty adjustment_date must not match any booking."""
        write_inputs(
            ["BOOK9701,CUST9701,900,POSTED,ACH,2026-04-05"],
            ["BOOK9701,CUST9701,900,ACH,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_booking_without_due_date_is_not_eligible(self):
        """A booking with an empty due_date cannot be consumed."""
        write_inputs(
            ["BOOK9801,CUST9801,700,POSTED,WIRE,"],
            ["BOOK9801,CUST9801,700,WIR,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_wir_alias_matches_wire_booking_and_emits_canonical_channel(self):
        """A WIR adjustment should match a WIRE booking and report the canonical channel."""
        write_inputs(
            ["BOOK9901,CUST9901,600,POSTED,WIRE,2026-04-10"],
            ["BOOK9901,CUST9901,600,WIR,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["channel"] == "WIRE"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
