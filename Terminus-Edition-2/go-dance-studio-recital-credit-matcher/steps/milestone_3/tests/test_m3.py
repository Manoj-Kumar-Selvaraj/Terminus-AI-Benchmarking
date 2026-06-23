"""Milestone 3 verifier tests for dated booking credit reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
BOOKINGS = APP / "data" / "bookings.csv"
CREDITS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "recital_credit_report.csv"
SUMMARY = APP / "out" / "recital_credit_summary.json"
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


def write_inputs(booking_rows, credit_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated credit scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    BOOKINGS.write_text("booking_id,dancer_id,amount_cents,status,recital_type,recital_date\n" + "\n".join(booking_rows) + "\n")
    CREDITS.write_text("booking_id,dancer_id,amount_cents,recital_type,credit_date\n" + "\n".join(credit_rows) + "\n")
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
    """Date gates and latest eligible booking selection for credits."""

    def test_undated_inputs_apply_milestone_2_matching_without_calendar_gates(self):
        """Without date columns, matching must follow milestone 2 rules and ignore the calendar."""
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        BOOKINGS.write_text(
            "booking_id,dancer_id,amount_cents,status,recital_type\n"
            "UND8001,CUST8001,1000,ACTIVE,SOLO\n"
            "UND8002,CUST8002,2000,ACTIVE,GROUP\n"
        )
        CREDITS.write_text(
            "booking_id,dancer_id,amount_cents,recital_type\n"
            "UND8001,CUST8001,1000,SL\n"
            "UND8002,CUST8002,2000,GP\n"
        )
        CALENDAR.write_text("2026-04-01 closed\n")
        REPORT.unlink(missing_ok=True)
        SUMMARY.unlink(missing_ok=True)
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["recital_type"] for row in rows] == ["SOLO", "GROUP"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 3000,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_open_credit_date_and_latest_recital_date_win(self):
        """Open credit dates should gate matching and latest eligible source date should win."""
        write_inputs(
            [
                "BILL9301,CUST9301,1000,ACTIVE,SOLO,2026-04-03",
                "BILL9301,CUST9301,1000,ACTIVE,GROUP,2026-04-04",
                "BILL9302,CUST9302,2000,ACTIVE,GROUP,2026-04-02",
                "BILL9303,CUST9303,3000,ACTIVE,STAGE,2026-04-05",
                "BILL9304,CUST9304,4000,ACTIVE,STAGE,2026-04-05",
            ],
            [
                "BILL9301,CUST9301,1000,GP,2026-04-02",
                "BILL9302,CUST9302,2000,GP,2026-04-04",
                "BILL9303,CUST9303,3000,ST,2026-04-06",
                "BILL9304,CUST9304,4000,STAGE,2026-04-07",
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
        assert rows[0]["recital_type"] == "GROUP"
        assert [row["recital_type"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_recital_date_tie_uses_booking_order_and_consumption(self):
        """Same-date candidates should use booking order and still enforce consumption."""
        write_inputs(
            [
                "BILL9401,CUST9401,500,ACTIVE,GROUP,2026-04-05",
                "BILL9401,CUST9401,500,ACTIVE,GROUP,2026-04-05",
                "BILL9402,CUST9402,700,ACTIVE,SOLO,2026-04-05",
            ],
            [
                "BILL9401,CUST9401,500,GP,2026-04-04",
                "BILL9401,CUST9401,500,GP,2026-04-04",
                "BILL9401,CUST9401,500,GP,2026-04-04",
                "BILL9402,CUST9402,700,SOLO,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["recital_type"] for row in rows] == ["GROUP", "GROUP", "", "SOLO"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_recital_date_wins_before_older_booking_row_is_used(self):
        """Latest recital_date must win; consuming the older row leaves the second credit ineligible."""
        write_inputs(
            [
                "BILL9501,CUST9501,800,ACTIVE,GROUP,2026-04-03",
                "BILL9501,CUST9501,800,ACTIVE,GROUP,2026-04-06",
            ],
            [
                "BILL9501,CUST9501,800,GP,2026-04-02",
                "BILL9501,CUST9501,800,GP,2026-04-04",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["recital_type"] for row in rows] == ["GROUP", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_closed_credit_date_is_not_eligible(self):
        """A credit whose date is listed as closed must not match."""
        write_inputs(
            ["BILL9601,CUST9601,1000,ACTIVE,GROUP,2026-04-10"],
            ["BILL9601,CUST9601,1000,GP,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["recital_type"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_credit_date_is_not_eligible(self):
        """A credit date absent from the calendar must not be treated as open."""
        write_inputs(
            ["BILL9651,CUST9651,500,ACTIVE,GROUP,2026-04-30"],
            ["BILL9651,CUST9651,500,GP,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["recital_type"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_credit_date_is_not_eligible(self):
        """A credit with an empty credit_date must not match any booking."""
        write_inputs(
            ["BILL9701,CUST9701,900,ACTIVE,SOLO,2026-04-05"],
            ["BILL9701,CUST9701,900,SOLO,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["recital_type"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_booking_without_recital_date_is_not_eligible(self):
        """A booking with an empty recital_date cannot be consumed."""
        write_inputs(
            ["BILL9801,CUST9801,700,ACTIVE,STAGE,"],
            ["BILL9801,CUST9801,700,ST,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["recital_type"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_latest_recital_date_wins_even_when_later_dated_row_appears_first(self):
        """Among same recital_type rows, latest recital_date wins even when it appears earlier in the file."""
        write_inputs(
            [
                "BILL9051,CUST9051,1000,ACTIVE,GROUP,2026-04-08",
                "BILL9051,CUST9051,1000,ACTIVE,GROUP,2026-04-03",
            ],
            [
                "BILL9051,CUST9051,1000,GP,2026-04-02",
                "BILL9051,CUST9051,1000,GP,2026-04-04",
            ],
            ["2026-04-02 open", "2026-04-04 open"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[0]["recital_type"] == "GROUP"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1000,
        }

    def test_sl_alias_matches_solo_under_dated_matching(self):
        """The SL alias should still normalize to SOLO when date gates are present."""
        write_inputs(
            ["BILL9951,CUST9951,650,ACTIVE,SOLO,2026-04-10"],
            ["BILL9951,CUST9951,650,SL,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["recital_type"] == "SOLO"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 650,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_st_alias_matches_stage_booking_and_emits_canonical_recital_type(self):
        """A ST credit should match a STAGE booking and report the canonical recital_type."""
        write_inputs(
            ["BILL9901,CUST9901,600,ACTIVE,STAGE,2026-04-10"],
            ["BILL9901,CUST9901,600,ST,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["recital_type"] == "STAGE"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_malformed_action_date_stays_unmatched(self):
        """A malformed credit_date must not be treated as an open eligible calendar date."""
        write_inputs(
            ["BADDTE1,CUSTBD1,1400,ACTIVE,SOLO,2026-04-10"],
            ["BADDTE1,CUSTBD1,1400,SOLO,not-a-date"],
            ["2026-04-04 open", "2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["recital_type"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 1400
