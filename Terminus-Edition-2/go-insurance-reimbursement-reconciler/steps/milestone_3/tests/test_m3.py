"""Milestone 3 verifier tests for dated insurance account reimbursement reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
ACCTS = APP / "data" / "accounts.csv"
REIMBURSEMENTS = APP / "data" / "reimbursements.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "reimbursement_report.csv"
SUMMARY = APP / "out" / "reimbursement_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go reimbursement reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 3 tests."""
    build_program()


def write_inputs(account_rows, reimbursement_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated reimbursement scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    ACCTS.write_text("account_id,customer_id,amount_cents,status,channel,due_date\n" + "\n".join(account_rows) + "\n")
    REIMBURSEMENTS.write_text("account_id,customer_id,amount_cents,channel,reimbursement_date\n" + "\n".join(reimbursement_rows) + "\n")
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
    """Date gates and latest eligible account selection for reimbursements."""

    def test_open_reimbursement_date_and_latest_due_date_win(self):
        """Open reimbursement dates should gate matching and latest eligible due date should win."""
        write_inputs(
            [
                "ACCT9301,CUST9301,1000,POSTED,ACH,2026-04-03",
                "ACCT9301,CUST9301,1000,POSTED,CARD,2026-04-04",
                "ACCT9302,CUST9302,2000,POSTED,CARD,2026-04-02",
                "ACCT9303,CUST9303,3000,POSTED,WIRE,2026-04-05",
                "ACCT9304,CUST9304,4000,POSTED,WIRE,2026-04-05",
            ],
            [
                "ACCT9301,CUST9301,1000,CC,2026-04-02",
                "ACCT9302,CUST9302,2000,CC,2026-04-04",
                "ACCT9303,CUST9303,3000,WIR,2026-04-06",
                "ACCT9304,CUST9304,4000,WIRE,2026-04-07",
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

    def test_same_due_date_tie_uses_account_order_and_consumption(self):
        """Same-date candidates should use account order and still enforce consumption."""
        write_inputs(
            [
                "ACCT9401,CUST9401,500,POSTED,CARD,2026-04-05",
                "ACCT9401,CUST9401,500,POSTED,CARD,2026-04-05",
                "ACCT9402,CUST9402,700,POSTED,ACH,2026-04-05",
            ],
            [
                "ACCT9401,CUST9401,500,CC,2026-04-04",
                "ACCT9401,CUST9401,500,CC,2026-04-04",
                "ACCT9401,CUST9401,500,CC,2026-04-04",
                "ACCT9402,CUST9402,700,ACH,2026-04-05",
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

    def test_latest_due_date_wins_before_older_account_is_used(self):
        """A later eligible due date should be consumed before an older eligible account."""
        write_inputs(
            [
                "ACCT9501,CUST9501,800,POSTED,CARD,2026-04-03",
                "ACCT9501,CUST9501,800,POSTED,CARD,2026-04-06",
            ],
            [
                "ACCT9501,CUST9501,800,CC,2026-04-02",
                "ACCT9501,CUST9501,800,CC,2026-04-04",
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

    def test_closed_reimbursement_date_is_not_eligible(self):
        """A reimbursement whose date is listed as closed must not match."""
        write_inputs(
            ["ACCT9601,CUST9601,1000,POSTED,CARD,2026-04-10"],
            ["ACCT9601,CUST9601,1000,CC,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_reimbursement_date_is_not_eligible(self):
        """A reimbursement date absent from the calendar must not be treated as open."""
        write_inputs(
            ["ACCT9651,CUST9651,500,POSTED,CARD,2026-04-30"],
            ["ACCT9651,CUST9651,500,CC,2026-04-15"],
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

    def test_missing_reimbursement_date_is_not_eligible(self):
        """A reimbursement with an empty reimbursement_date must not match any account."""
        write_inputs(
            ["ACCT9701,CUST9701,900,POSTED,ACH,2026-04-05"],
            ["ACCT9701,CUST9701,900,ACH,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_account_without_due_date_is_not_eligible(self):
        """An account with an empty due_date cannot be consumed."""
        write_inputs(
            ["ACCT9801,CUST9801,700,POSTED,WIRE,"],
            ["ACCT9801,CUST9801,700,WIR,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_wir_alias_matches_wire_account_and_emits_canonical_channel(self):
        """A WIR reimbursement should match a WIRE account and report the canonical channel."""
        write_inputs(
            ["ACCT9901,CUST9901,600,POSTED,WIRE,2026-04-10"],
            ["ACCT9901,CUST9901,600,WIR,2026-04-05"],
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
