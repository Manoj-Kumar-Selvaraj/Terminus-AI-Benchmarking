"""Milestone 3 verifier tests for dated bill refund reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
BILLS = APP / "data" / "bills.csv"
REFUNDS = APP / "data" / "refunds.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "refund_report.csv"
SUMMARY = APP / "out" / "refund_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go refund reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 3 tests."""
    build_program()


def write_inputs(
    bill_rows,
    refund_rows,
    calendar_rows,
    bill_header="bill_id,customer_id,amount_cents,status,channel,due_date",
    refund_header="bill_id,customer_id,amount_cents,channel,refund_date",
):
    """Replace CSV inputs and calendar with a dated refund scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    BILLS.write_text(bill_header + "\n" + "\n".join(bill_rows) + "\n")
    REFUNDS.write_text(refund_header + "\n" + "\n".join(refund_rows) + "\n")
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
    """Date gates and latest eligible bill selection for refunds."""

    def test_open_refund_date_and_latest_due_date_win(self):
        """Open refund dates should gate matching and latest eligible due date should win."""
        write_inputs(
            [
                "BILL9301,CUST9301,1000,POSTED,ACH,2026-04-03",
                "BILL9301,CUST9301,1000,POSTED,CARD,2026-04-04",
                "BILL9302,CUST9302,2000,POSTED,CARD,2026-04-02",
                "BILL9303,CUST9303,3000,POSTED,WIRE,2026-04-05",
                "BILL9304,CUST9304,4000,POSTED,WIRE,2026-04-05",
            ],
            [
                "BILL9301,CUST9301,1000,CC,2026-04-02",
                "BILL9302,CUST9302,2000,CC,2026-04-04",
                "BILL9303,CUST9303,3000,WIR,2026-04-06",
                "BILL9304,CUST9304,4000,WIRE,2026-04-07",
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

    def test_same_due_date_tie_uses_bill_order_and_consumption(self):
        """Same-date candidates should use bill order and still enforce consumption."""
        write_inputs(
            [
                "BILL9401,CUST9401,500,POSTED,CARD,2026-04-05",
                "BILL9401,CUST9401,500,POSTED,CARD,2026-04-05",
                "BILL9402,CUST9402,700,POSTED,ACH,2026-04-05",
            ],
            [
                "BILL9401,CUST9401,500,CC,2026-04-04",
                "BILL9401,CUST9401,500,CC,2026-04-04",
                "BILL9401,CUST9401,500,CC,2026-04-04",
                "BILL9402,CUST9402,700,ACH,2026-04-05",
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

    def test_equal_due_date_tie_breaks_to_earliest_bill_row(self):
        """Equal due dates with interleaved bill ids must consume earliest qualifying rows in file order."""
        write_inputs(
            [
                "BILL9420,CUST9420,500,POSTED,CARD,2026-04-05",
                "BILL9421,CUST9421,700,POSTED,ACH,2026-04-05",
                "BILL9420,CUST9420,500,POSTED,CARD,2026-04-05",
            ],
            [
                "BILL9420,CUST9420,500,CC,2026-04-04",
                "BILL9420,CUST9420,500,CC,2026-04-04",
                "BILL9421,CUST9421,700,ACH,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["channel"] for row in rows] == ["CARD", "CARD", "ACH"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 1700,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_latest_due_date_wins_before_older_bill_is_used(self):
        """A later eligible due date should be consumed before an older eligible bill."""
        write_inputs(
            [
                "BILL9501,CUST9501,800,POSTED,CARD,2026-04-03",
                "BILL9501,CUST9501,800,POSTED,CARD,2026-04-06",
            ],
            [
                "BILL9501,CUST9501,800,CC,2026-04-02",
                "BILL9501,CUST9501,800,CC,2026-04-04",
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

    def test_closed_refund_date_is_not_eligible(self):
        """A refund whose date is listed as closed must not match."""
        write_inputs(
            ["BILL9601,CUST9601,1000,POSTED,CARD,2026-04-10"],
            ["BILL9601,CUST9601,1000,CC,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_refund_date_is_not_eligible(self):
        """A refund date absent from the calendar must not be treated as open."""
        write_inputs(
            ["BILL9651,CUST9651,500,POSTED,CARD,2026-04-30"],
            ["BILL9651,CUST9651,500,CC,2026-04-15"],
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

    def test_missing_refund_date_is_not_eligible(self):
        """A refund with an empty refund_date must not match any bill."""
        write_inputs(
            ["BILL9701,CUST9701,900,POSTED,ACH,2026-04-05"],
            ["BILL9701,CUST9701,900,ACH,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_bill_without_due_date_is_not_eligible(self):
        """A bill with an empty due_date cannot be consumed."""
        write_inputs(
            ["BILL9801,CUST9801,700,POSTED,WIRE,"],
            ["BILL9801,CUST9801,700,WIR,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_wir_alias_matches_wire_bill_and_emits_canonical_channel(self):
        """A WIR refund should match a WIRE bill and report the canonical channel."""
        write_inputs(
            ["BILL9901,CUST9901,600,POSTED,WIRE,2026-04-10"],
            ["BILL9901,CUST9901,600,WIR,2026-04-05"],
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

    def test_omitted_date_columns_use_alias_aware_undated_matching(self):
        """Files without due_date/refund_date columns should still reconcile with milestone 2 rules."""
        write_inputs(
            [
                "BILL9951,CUST9951,610,POSTED,CARD",
                "BILL9952,CUST9952,620,POSTED,WIRE",
                "BILL9953,CUST9953,630,POSTED,ACH",
            ],
            [
                "BILL9951,CUST9951,610,CC",
                "BILL9952,CUST9952,620,WIR",
                "BILL9953,CUST9953,630,ACH",
            ],
            ["2026-04-05 closed"],
            bill_header="bill_id,customer_id,amount_cents,status,channel",
            refund_header="bill_id,customer_id,amount_cents,channel",
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["channel"] for row in rows] == ["CARD", "WIRE", "ACH"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 1860,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
