"""Milestone 3 verifier tests for dated hotel reservation credit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
RSVS = APP / "data" / "reservations.csv"
CREDITS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
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
    """Compile the Go reconciliation CLI once for all milestone 3 tests."""
    build_program()


def write_inputs(reservation_rows, credit_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated credit scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    RSVS.write_text("reservation_id,customer_id,amount_cents,status,channel,due_date\n" + "\n".join(reservation_rows) + "\n")
    CREDITS.write_text("reservation_id,customer_id,amount_cents,channel,credit_date\n" + "\n".join(credit_rows) + "\n")
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
    """Date gates and latest eligible reservation selection for credits."""

    def test_open_credit_date_and_latest_due_date_win(self):
        """Open credit dates should gate matching and latest eligible due date should win."""
        write_inputs(
            [
                "RSV9301,CUST9301,1000,POSTED,ACH,2026-04-03",
                "RSV9301,CUST9301,1000,POSTED,CARD,2026-04-04",
                "RSV9302,CUST9302,2000,POSTED,CARD,2026-04-02",
                "RSV9303,CUST9303,3000,POSTED,WIRE,2026-04-05",
                "RSV9304,CUST9304,4000,POSTED,WIRE,2026-04-05",
            ],
            [
                "RSV9301,CUST9301,1000,CC,2026-04-02",
                "RSV9302,CUST9302,2000,CC,2026-04-04",
                "RSV9303,CUST9303,3000,WIR,2026-04-06",
                "RSV9304,CUST9304,4000,WIRE,2026-04-07",
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

    def test_same_due_date_tie_uses_reservation_order_and_consumption(self):
        """Same-date candidates should use reservation order and still enforce consumption."""
        write_inputs(
            [
                "RSV9401,CUST9401,500,POSTED,CARD,2026-04-05",
                "RSV9401,CUST9401,500,POSTED,CARD,2026-04-05",
                "RSV9402,CUST9402,700,POSTED,ACH,2026-04-05",
            ],
            [
                "RSV9401,CUST9401,500,CC,2026-04-04",
                "RSV9401,CUST9401,500,CC,2026-04-04",
                "RSV9401,CUST9401,500,CC,2026-04-04",
                "RSV9402,CUST9402,700,ACH,2026-04-05",
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

    def test_latest_due_date_wins_before_older_reservation_is_used(self):
        """A later eligible due date should be consumed before an older eligible reservation."""
        write_inputs(
            [
                "RSV9501,CUST9501,800,POSTED,CARD,2026-04-03",
                "RSV9501,CUST9501,800,POSTED,CARD,2026-04-06",
            ],
            [
                "RSV9501,CUST9501,800,CC,2026-04-02",
                "RSV9501,CUST9501,800,CC,2026-04-04",
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

    def test_closed_credit_date_is_not_eligible(self):
        """A credit whose date is listed as closed must not match."""
        write_inputs(
            ["RSV9601,CUST9601,1000,POSTED,CARD,2026-04-10"],
            ["RSV9601,CUST9601,1000,CC,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_credit_date_is_not_eligible(self):
        """A credit date absent from the calendar must not be treated as open."""
        write_inputs(
            ["RSV9651,CUST9651,500,POSTED,CARD,2026-04-30"],
            ["RSV9651,CUST9651,500,CC,2026-04-15"],
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

    def test_missing_credit_date_is_not_eligible(self):
        """A credit with an empty credit_date must not match any reservation."""
        write_inputs(
            ["RSV9701,CUST9701,900,POSTED,ACH,2026-04-05"],
            ["RSV9701,CUST9701,900,ACH,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_reservation_without_due_date_is_not_eligible(self):
        """A reservation with an empty due_date cannot be consumed."""
        write_inputs(
            ["RSV9801,CUST9801,700,POSTED,WIRE,"],
            ["RSV9801,CUST9801,700,WIR,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_wir_alias_matches_wire_reservation_and_emits_canonical_channel(self):
        """A WIR credit should match a WIRE reservation and report the canonical channel."""
        write_inputs(
            ["RSV9901,CUST9901,600,POSTED,WIRE,2026-04-10"],
            ["RSV9901,CUST9901,600,WIR,2026-04-05"],
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

    def test_calendar_open_status_is_case_insensitive(self):
        """A calendar line with OPEN in uppercase should still gate a valid dated credit."""
        write_inputs(
            ["RSV9951,CUST9951,750,POSTED,ACH,2026-04-20"],
            ["RSV9951,CUST9951,750,ACH,2026-04-10"],
            ["2026-04-10 OPEN"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["channel"] == "ACH"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 750
