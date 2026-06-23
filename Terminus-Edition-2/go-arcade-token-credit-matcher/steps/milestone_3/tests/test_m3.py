"""Milestone 3 verifier tests for dated token credit reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
ARCS = APP / "data" / "plays.csv"
REFUNDS = APP / "data" / "token_credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "token_credit_report.csv"
SUMMARY = APP / "out" / "token_credit_summary.json"
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


def write_inputs(bill_rows, credit_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated credit scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    ARCS.write_text("play_id,member_id,amount_cents,status,token_tier,play_date\n" + "\n".join(bill_rows) + "\n")
    REFUNDS.write_text("play_id,member_id,amount_cents,token_tier,credit_date\n" + "\n".join(credit_rows) + "\n")
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
    """Date gates and latest eligible trip selection for credits."""

    def test_open_credit_date_and_latest_play_date_win(self):
        """Open credit dates should gate matching and latest eligible due date should win."""
        write_inputs(
            [
                "ARC9301,CUST9301,1000,COMPLETED,ARC,2026-04-03",
                "ARC9301,CUST9301,1000,COMPLETED,PRO,2026-04-04",
                "ARC9302,CUST9302,2000,COMPLETED,PRO,2026-04-02",
                "ARC9303,CUST9303,3000,COMPLETED,VIP,2026-04-05",
                "ARC9304,CUST9304,4000,COMPLETED,VIP,2026-04-05",
            ],
            [
                "ARC9301,CUST9301,1000,PR,2026-04-02",
                "ARC9302,CUST9302,2000,PR,2026-04-04",
                "ARC9303,CUST9303,3000,VI,2026-04-06",
                "ARC9304,CUST9304,4000,VIP,2026-04-07",
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
        assert rows[0]["token_tier"] == "PRO"
        assert [row["token_tier"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_play_date_tie_uses_record_order_and_consumption(self):
        """Same-date candidates should use trip order and still enforce consumption."""
        write_inputs(
            [
                "ARC9401,CUST9401,500,COMPLETED,PRO,2026-04-05",
                "ARC9401,CUST9401,500,COMPLETED,PRO,2026-04-05",
                "ARC9402,CUST9402,700,COMPLETED,ARC,2026-04-05",
            ],
            [
                "ARC9401,CUST9401,500,PR,2026-04-04",
                "ARC9401,CUST9401,500,PR,2026-04-04",
                "ARC9401,CUST9401,500,PR,2026-04-04",
                "ARC9402,CUST9402,700,ARC,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["token_tier"] for row in rows] == ["PRO", "PRO", "", "ARC"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_play_date_wins_before_older_record_is_used(self):
        """Latest play_date must win when the later input row carries the later date."""
        write_inputs(
            [
                "ARC9501,CUST9501,500,COMPLETED,ARC,2026-04-03",
                "ARC9501,CUST9501,800,COMPLETED,PRO,2026-04-06",
                "ARC9501,CUST9501,700,COMPLETED,PRO,2026-04-05",
            ],
            [
                "ARC9501,CUST9501,800,PR,2026-04-02",
                "ARC9501,CUST9501,700,PR,2026-04-04",
                "ARC9501,CUST9501,500,AR,2026-04-03",
            ],
            [
                "2026-04-02 open",
                "2026-04-03 open",
                "2026-04-04 open",
                "2026-04-05 open",
                "2026-04-06 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 2000,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_closed_credit_date_is_not_eligible(self):
        """A credit whose date is listed as closed must not match."""
        write_inputs(
            ["ARC9601,CUST9601,1000,COMPLETED,PRO,2026-04-10"],
            ["ARC9601,CUST9601,1000,PR,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["token_tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_credit_date_is_not_eligible(self):
        """A credit date absent from the calendar must not be treated as open."""
        write_inputs(
            ["ARC9651,CUST9651,500,COMPLETED,PRO,2026-04-30"],
            ["ARC9651,CUST9651,500,PR,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["token_tier"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_credit_date_is_not_eligible(self):
        """A credit with an empty credit_date must not match any trip."""
        write_inputs(
            ["ARC9701,CUST9701,900,COMPLETED,ARC,2026-04-05"],
            ["ARC9701,CUST9701,900,ARC,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["token_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_record_without_play_date_is_not_eligible(self):
        """A trip with an empty play_date cannot be consumed."""
        write_inputs(
            ["ARC9801,CUST9801,700,COMPLETED,VIP,"],
            ["ARC9801,CUST9801,700,VI,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["token_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_vi_alias_matches_vip_record_and_emits_canonical_token_tier(self):
        """A VI credit should match a VIP trip and report the canonical token_tier."""
        write_inputs(
            ["ARC9901,CUST9901,600,COMPLETED,VIP,2026-04-10"],
            ["ARC9901,CUST9901,600,VI,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["token_tier"] == "VIP"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }


    def test_mismatched_token_tier_does_not_match_even_with_valid_dates(self):
        """Date logic must not bypass the original token_tier equality requirement."""
        write_inputs(
            ["ARC9851,CUST9851,775,COMPLETED,ARC,2026-04-10"],
            ["ARC9851,CUST9851,775,PRO,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["token_tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 775

    def test_ar_alias_matches_arc_record_with_dated_matching(self):
        """The AR alias should still normalize to ARC when date gates are present."""
        write_inputs(
            ["ARC9951,CUST9951,650,COMPLETED,ARC,2026-04-10"],
            ["ARC9951,CUST9951,650,AR,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["token_tier"] == "ARC"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 650,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
