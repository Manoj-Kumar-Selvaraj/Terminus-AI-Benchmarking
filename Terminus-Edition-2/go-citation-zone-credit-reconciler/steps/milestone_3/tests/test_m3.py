"""Milestone 3 verifier tests for dated citation credit reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
BILLS = APP / "data" / "citations.csv"
REFUNDS = APP / "data" / "credits.csv"
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


def write_inputs(bill_rows, refund_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated credit scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    BILLS.write_text("citation_id,plate_id,amount_cents,status,zone,due_date\n" + "\n".join(bill_rows) + "\n")
    REFUNDS.write_text("citation_id,plate_id,amount_cents,zone,credit_date\n" + "\n".join(refund_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_legacy_inputs(bill_rows, refund_rows, calendar_rows):
    """Write older input schemas without date columns for no-crash legacy handling."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    BILLS.write_text("citation_id,plate_id,amount_cents,status,zone\n" + "\n".join(bill_rows) + "\n")
    REFUNDS.write_text("citation_id,plate_id,amount_cents,zone\n" + "\n".join(refund_rows) + "\n")
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
    """Date gates and latest eligible citation selection for refunds."""

    def test_open_credit_date_and_latest_due_date_win(self):
        """Open credit dates should gate matching and latest eligible due date should win."""
        write_inputs(
            [
                "BILL9301,CUST9301,1000,PAID,STREET,2026-04-03",
                "BILL9301,CUST9301,1000,PAID,GARAGE,2026-04-04",
                "BILL9302,CUST9302,2000,PAID,GARAGE,2026-04-02",
                "BILL9303,CUST9303,3000,PAID,LOT,2026-04-05",
                "BILL9304,CUST9304,4000,PAID,LOT,2026-04-05",
            ],
            [
                "BILL9301,CUST9301,1000,GRG,2026-04-02",
                "BILL9302,CUST9302,2000,GRG,2026-04-04",
                "BILL9303,CUST9303,3000,LT,2026-04-06",
                "BILL9304,CUST9304,4000,LOT,2026-04-07",
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
        assert rows[0]["zone"] == "GARAGE"
        assert [row["zone"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_due_date_candidates_still_enforce_consumption(self):
        """Same-date candidates should still consume each source row at most once."""
        write_inputs(
            [
                "BILL9401,CUST9401,500,PAID,GARAGE,2026-04-05",
                "BILL9401,CUST9401,500,PAID,GARAGE,2026-04-05",
                "BILL9402,CUST9402,700,PAID,STREET,2026-04-05",
            ],
            [
                "BILL9401,CUST9401,500,GRG,2026-04-04",
                "BILL9401,CUST9401,500,GRG,2026-04-04",
                "BILL9401,CUST9401,500,GRG,2026-04-04",
                "BILL9402,CUST9402,700,STREET,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["zone"] for row in rows] == ["GARAGE", "GARAGE", "", "STREET"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_legacy_schema_without_dates_is_readable_but_unmatched(self):
        """Older input schemas without date columns should not crash and should remain unmatched."""
        write_legacy_inputs(
            [
                "BILL9451,CUST9451,900,PAID,GARAGE",
                "BILL9452,CUST9452,600,PAID,STREET",
            ],
            [
                "BILL9451,CUST9451,900,GRG",
                "BILL9452,CUST9452,600,ST",
            ],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert [row["zone"] for row in rows] == ["", ""]
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 2,
            "unmatched_amount_cents": 1500,
        }

    def test_latest_due_date_wins_before_older_bill_is_used(self):
        """A later eligible due date should be consumed before an older eligible citation."""
        write_inputs(
            [
                "BILL9501,CUST9501,800,PAID,GARAGE,2026-04-03",
                "BILL9501,CUST9501,800,PAID,GARAGE,2026-04-06",
            ],
            [
                "BILL9501,CUST9501,800,GRG,2026-04-02",
                "BILL9501,CUST9501,800,GRG,2026-04-04",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["zone"] for row in rows] == ["GARAGE", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_closed_credit_date_is_not_eligible(self):
        """A credit whose date is listed as closed must not match."""
        write_inputs(
            ["BILL9601,CUST9601,1000,PAID,GARAGE,2026-04-10"],
            ["BILL9601,CUST9601,1000,GRG,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["zone"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_non_paid_citation_not_eligible_even_with_valid_dates(self):
        """Date gates must not accidentally allow non-PAID citations to match."""
        write_inputs(
            ["BILL8001,CUST8001,500,DRAFT,GARAGE,2026-04-10"],
            ["BILL8001,CUST8001,500,GRG,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["zone"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_unlisted_credit_date_is_not_eligible(self):
        """A credit date absent from the calendar must not be treated as open."""
        write_inputs(
            ["BILL9651,CUST9651,500,PAID,GARAGE,2026-04-30"],
            ["BILL9651,CUST9651,500,GRG,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["zone"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_credit_date_is_not_eligible(self):
        """A credit with an empty credit_date must not match any citation."""
        write_inputs(
            ["BILL9701,CUST9701,900,PAID,STREET,2026-04-05"],
            ["BILL9701,CUST9701,900,STREET,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["zone"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_bill_without_due_date_is_not_eligible(self):
        """A citation with an empty due_date cannot be consumed."""
        write_inputs(
            ["BILL9801,CUST9801,700,PAID,LOT,"],
            ["BILL9801,CUST9801,700,LT,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["zone"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_lt_alias_matches_lot_bill_and_emits_canonical_zone(self):
        """A LT credit should match a LOT citation and report the canonical zone."""
        write_inputs(
            ["BILL9901,CUST9901,600,PAID,LOT,2026-04-10"],
            ["BILL9901,CUST9901,600,LT,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["zone"] == "LOT"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_st_alias_matches_street_citation_under_date_gates(self):
        """An ST credit should match a STREET citation when the credit date is open and eligible."""
        write_inputs(
            [
                "BILL9911,CUST9911,450,PAID,STREET,2026-04-08",
                "BILL9912,CUST9912,550,PAID,GARAGE,2026-04-08",
            ],
            [
                "BILL9911,CUST9911,450,ST,2026-04-06",
                "BILL9912,CUST9912,550,GRG,2026-04-06",
            ],
            [
                "2026-04-06 open",
                "2026-04-08 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["zone"] for row in rows] == ["STREET", "GARAGE"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1000,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_st_alias_does_not_match_garage_citation(self):
        """An ST credit must not match a GARAGE citation even when other fields and dates align."""
        write_inputs(
            ["BILL9921,CUST9921,700,PAID,GARAGE,2026-04-05"],
            ["BILL9921,CUST9921,700,ST,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["zone"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 700,
        }
