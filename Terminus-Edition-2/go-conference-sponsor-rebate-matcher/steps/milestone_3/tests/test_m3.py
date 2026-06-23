"""Milestone 3 tests for dated sponsorship rebate reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
BILLS = APP / "data" / "sponsorships.csv"
REFUNDS = APP / "data" / "rebates.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "rebate_report.csv"
SUMMARY = APP / "out" / "rebate_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go rebate reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 3 tests."""
    build_program()


def write_inputs(bill_rows, refund_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated rebate scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    BILLS.write_text("sponsorship_id,sponsor_id,amount_cents,status,level,event_end\n" + "\n".join(bill_rows) + "\n")
    REFUNDS.write_text("sponsorship_id,sponsor_id,amount_cents,level,rebate_date\n" + "\n".join(refund_rows) + "\n")
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
    """Date gates and latest eligible sponsorship selection for refunds."""

    def test_undated_inputs_apply_alias_matching_without_calendar_gates(self):
        """Without date columns, matching must follow alias-aware rules and ignore the calendar."""
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        BILLS.write_text(
            "sponsorship_id,sponsor_id,amount_cents,status,level\n"
            "UND8001,CUST8001,1000,SIGNED,BRONZE\n"
            "UND8002,CUST8002,2000,SIGNED,GOLD\n"
        )
        REFUNDS.write_text(
            "sponsorship_id,sponsor_id,amount_cents,level\n"
            "UND8001,CUST8001,1000,BRZ\n"
            "UND8002,CUST8002,2000,GLD\n"
        )
        CALENDAR.write_text("2026-04-01 closed\n")
        REPORT.unlink(missing_ok=True)
        SUMMARY.unlink(missing_ok=True)
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["level"] for row in rows] == ["BRONZE", "GOLD"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 3000,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_open_rebate_date_and_latest_event_end_win(self):
        """Open rebate dates should gate matching and latest eligible due date should win."""
        write_inputs(
            [
                "BILL9301,CUST9301,1000,SIGNED,BRONZE,2026-04-03",
                "BILL9301,CUST9301,1000,SIGNED,GOLD,2026-04-04",
                "BILL9302,CUST9302,2000,SIGNED,GOLD,2026-04-02",
                "BILL9303,CUST9303,3000,SIGNED,PLATINUM,2026-04-05",
                "BILL9304,CUST9304,4000,SIGNED,PLATINUM,2026-04-05",
            ],
            [
                "BILL9301,CUST9301,1000,GLD,2026-04-02",
                "BILL9302,CUST9302,2000,GLD,2026-04-04",
                "BILL9303,CUST9303,3000,PLT,2026-04-06",
                "BILL9304,CUST9304,4000,PLATINUM,2026-04-07",
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
        assert rows[0]["level"] == "GOLD"
        assert [row["level"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_event_end_tie_uses_bill_order_and_consumption(self):
        """Same-date candidates should use sponsorship order and still enforce consumption."""
        write_inputs(
            [
                "BILL9401,CUST9401,500,SIGNED,GOLD,2026-04-05",
                "BILL9401,CUST9401,500,SIGNED,GOLD,2026-04-05",
                "BILL9402,CUST9402,700,SIGNED,BRONZE,2026-04-05",
            ],
            [
                "BILL9401,CUST9401,500,GLD,2026-04-04",
                "BILL9401,CUST9401,500,GLD,2026-04-04",
                "BILL9401,CUST9401,500,GLD,2026-04-04",
                "BILL9402,CUST9402,700,BRONZE,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["level"] for row in rows] == ["GOLD", "GOLD", "", "BRONZE"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_event_end_wins_before_older_sponsorship_row_is_used(self):
        """Latest event_end must win; consuming the older row leaves the second rebate ineligible."""
        write_inputs(
            [
                "BILL9501,CUST9501,800,SIGNED,GOLD,2026-04-03",
                "BILL9501,CUST9501,800,SIGNED,GOLD,2026-04-06",
            ],
            [
                "BILL9501,CUST9501,800,GLD,2026-04-02",
                "BILL9501,CUST9501,800,GLD,2026-04-04",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["level"] for row in rows] == ["GOLD", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_closed_rebate_date_is_not_eligible(self):
        """A rebate whose date is listed as closed must not match."""
        write_inputs(
            ["BILL9601,CUST9601,1000,SIGNED,GOLD,2026-04-10"],
            ["BILL9601,CUST9601,1000,GLD,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["level"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_rebate_date_is_not_eligible(self):
        """A rebate date absent from the calendar must not be treated as open."""
        write_inputs(
            ["BILL9651,CUST9651,500,SIGNED,GOLD,2026-04-30"],
            ["BILL9651,CUST9651,500,GLD,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["level"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_rebate_date_is_not_eligible(self):
        """A rebate with an empty rebate_date must not match any sponsorship."""
        write_inputs(
            ["BILL9701,CUST9701,900,SIGNED,BRONZE,2026-04-05"],
            ["BILL9701,CUST9701,900,BRONZE,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["level"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_bill_without_event_end_is_not_eligible(self):
        """A sponsorship with an empty event_end cannot be consumed."""
        write_inputs(
            ["BILL9801,CUST9801,700,SIGNED,PLATINUM,"],
            ["BILL9801,CUST9801,700,PLT,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["level"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_latest_event_end_wins_even_when_later_dated_row_appears_first(self):
        """Among same-level rows, latest event_end wins even when it appears earlier in the file."""
        write_inputs(
            [
                "BILL9051,CUST9051,1000,SIGNED,GOLD,2026-04-08",
                "BILL9051,CUST9051,1000,SIGNED,GOLD,2026-04-03",
            ],
            [
                "BILL9051,CUST9051,1000,GLD,2026-04-02",
                "BILL9051,CUST9051,1000,GLD,2026-04-04",
            ],
            ["2026-04-02 open", "2026-04-04 open"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[0]["level"] == "GOLD"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1000,
        }

    def test_brz_alias_matches_bronze_under_dated_matching(self):
        """The BRZ alias should still normalize to BRONZE when date gates are present."""
        write_inputs(
            ["BILL9951,CUST9951,650,SIGNED,BRONZE,2026-04-10"],
            ["BILL9951,CUST9951,650,BRZ,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["level"] == "BRONZE"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 650,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_plt_alias_matches_platinum_bill_and_emits_canonical_level(self):
        """A PLT rebate should match a PLATINUM sponsorship and report the canonical level."""
        write_inputs(
            ["BILL9901,CUST9901,600,SIGNED,PLATINUM,2026-04-10"],
            ["BILL9901,CUST9901,600,PLT,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["level"] == "PLATINUM"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
