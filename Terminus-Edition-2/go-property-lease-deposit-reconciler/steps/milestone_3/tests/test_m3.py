"""Tests for dated property lease deposit reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
LEASES = APP / "data" / "leases.csv"
DEPOSITS = APP / "data" / "deposits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "deposit_report.csv"
SUMMARY = APP / "out" / "deposit_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go deposit reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 3 tests."""
    build_program()


def write_inputs(lease_rows, deposit_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated deposit scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    LEASES.write_text("lease_id,customer_id,amount_cents,status,channel,due_date\n" + "\n".join(lease_rows) + "\n")
    DEPOSITS.write_text("lease_id,customer_id,amount_cents,channel,deposit_date\n" + "\n".join(deposit_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)

def write_undated_inputs(lease_rows, deposit_rows):
    """Replace inputs with schemas that omit both optional date columns."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    LEASES.write_text("lease_id,customer_id,amount_cents,status,channel\n" + "\n".join(lease_rows) + "\n")
    DEPOSITS.write_text("lease_id,customer_id,amount_cents,channel\n" + "\n".join(deposit_rows) + "\n")
    CALENDAR.write_text("2026-04-04 closed\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse its CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone3:
    """Date gates and latest eligible lease selection for deposits."""

    def test_open_deposit_date_and_latest_due_date_win(self):
        """Open deposit dates should gate matching and latest eligible due date should win."""
        write_inputs(
            [
                "LEAS9301,CUST9301,1000,POSTED,ACH,2026-04-03",
                "LEAS9301,CUST9301,1000,POSTED,CARD,2026-04-04",
                "LEAS9302,CUST9302,2000,POSTED,CARD,2026-04-02",
                "LEAS9303,CUST9303,3000,POSTED,WIRE,2026-04-05",
                "LEAS9304,CUST9304,4000,POSTED,WIRE,2026-04-05",
            ],
            [
                "LEAS9301,CUST9301,1000,CC,2026-04-02",
                "LEAS9302,CUST9302,2000,CC,2026-04-04",
                "LEAS9303,CUST9303,3000,WIR,2026-04-06",
                "LEAS9304,CUST9304,4000,WIRE,2026-04-07",
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

    def test_same_due_date_tie_uses_lease_order_and_consumption(self):
        """Same-date candidates should use lease order and still enforce consumption."""
        write_inputs(
            [
                "LEAS9401,CUST9401,500,POSTED,CARD,2026-04-05",
                "LEAS9401,CUST9401,500,POSTED,CARD,2026-04-05",
                "LEAS9402,CUST9402,700,POSTED,ACH,2026-04-05",
            ],
            [
                "LEAS9401,CUST9401,500,CC,2026-04-04",
                "LEAS9401,CUST9401,500,CC,2026-04-04",
                "LEAS9401,CUST9401,500,CC,2026-04-04",
                "LEAS9402,CUST9402,700,ACH,2026-04-05",
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

    def test_latest_due_date_wins_before_older_lease_is_used(self):
        """A later eligible due date should be consumed before an older eligible lease."""
        write_inputs(
            [
                "LEAS9501,CUST9501,800,POSTED,CARD,2026-04-03",
                "LEAS9501,CUST9501,800,POSTED,CARD,2026-04-06",
            ],
            [
                "LEAS9501,CUST9501,800,CC,2026-04-02",
                "LEAS9501,CUST9501,800,CC,2026-04-04",
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

    def test_latest_due_date_wins_even_when_later_lease_appears_first(self):
        """Latest due_date must beat last-row shortcuts when the later eligible lease appears first."""
        write_inputs(
            [
                "LEAS9551,CUST9551,850,POSTED,CARD,2026-04-08",
                "LEAS9551,CUST9551,850,POSTED,CARD,2026-04-05",
            ],
            [
                "LEAS9551,CUST9551,850,CC,2026-04-04",
                "LEAS9551,CUST9551,850,CC,2026-04-06",
            ],
            [
                "2026-04-04 open",
                "2026-04-06 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["channel"] for row in rows] == ["CARD", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 850,
            "unmatched_count": 1,
            "unmatched_amount_cents": 850,
        }

    def test_closed_deposit_date_is_not_eligible(self):
        """A deposit whose date is listed as closed must not match."""
        write_inputs(
            ["LEAS9601,CUST9601,1000,POSTED,CARD,2026-04-10"],
            ["LEAS9601,CUST9601,1000,CC,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_deposit_date_is_not_eligible(self):
        """A deposit date absent from the calendar must not be treated as open."""
        write_inputs(
            ["LEAS9651,CUST9651,500,POSTED,CARD,2026-04-30"],
            ["LEAS9651,CUST9651,500,CC,2026-04-15"],
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

    def test_missing_deposit_date_is_not_eligible(self):
        """A deposit with an empty deposit_date must not match any lease."""
        write_inputs(
            ["LEAS9701,CUST9701,900,POSTED,ACH,2026-04-05"],
            ["LEAS9701,CUST9701,900,ACH,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_malformed_deposit_date_is_not_eligible(self):
        """A malformed deposit_date must not be treated as an open calendar date."""
        write_inputs(
            ["LEAS9751,CUST9751,950,POSTED,CARD,2026-04-10"],
            ["LEAS9751,CUST9751,950,CARD,not-a-date"],
            ["2026-04-04 open", "2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 950

    def test_malformed_due_date_is_not_eligible(self):
        """A malformed lease due_date must not be treated as an open calendar date."""
        write_inputs(
            ["LEAS9761,CUST9761,975,POSTED,ACH,bad-date"],
            ["LEAS9761,CUST9761,975,ACH,2026-04-04"],
            ["2026-04-04 open", "bad-date open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 975

    def test_lease_without_due_date_is_not_eligible(self):
        """A lease with an empty due_date cannot be consumed."""
        write_inputs(
            ["LEAS9801,CUST9801,700,POSTED,WIRE,"],
            ["LEAS9801,CUST9801,700,WIR,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_wir_alias_matches_wire_lease_and_emits_canonical_channel(self):
        """A WIR deposit should match a WIRE lease and report the canonical channel."""
        write_inputs(
            ["LEAS9901,CUST9901,600,POSTED,WIRE,2026-04-10"],
            ["LEAS9901,CUST9901,600,WIR,2026-04-05"],
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

    def test_inputs_without_date_columns_preserve_undated_alias_matching(self):
        """When both date columns are absent, calendar gates are skipped and alias matching remains active."""
        write_undated_inputs(
            ["UND9901,CUST9901,640,POSTED, WIR "],
            ["UND9901,CUST9901,640, wire "],
        )
        rows, summary = run_program()

        assert rows == [
            {
                "lease_id": "UND9901",
                "customer_id": "CUST9901",
                "channel": "WIRE",
                "amount_cents": "640",
                "status": "MATCHED",
            }
        ]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 640,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
