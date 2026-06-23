"""Milestone 3 verifier tests for dated rebate reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
SOLS = APP / "data" / "installs.csv"
ACTION_FILE = APP / "data" / "rebates.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "solar_rebate_report.csv"
SUMMARY = APP / "out" / "solar_rebate_summary.json"
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
    SOLS.write_text("install_id,site_id,amount_cents,status,system_tier,install_date\n" + "\n".join(bill_rows) + "\n")
    ACTION_FILE.write_text("install_id,site_id,amount_cents,system_tier,rebate_date\n" + "\n".join(credit_rows) + "\n")
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
    """Date gates and latest eligible source-row selection for action rows."""

    def test_open_rebate_date_and_latest_install_date_win(self):
        """Open action dates should gate matching and the latest eligible source date should win."""
        write_inputs(
            [
                "SOL9301,CUST9301,1000,COMPLETED,HOME,2026-04-03",
                "SOL9301,CUST9301,1000,COMPLETED,BIZ,2026-04-04",
                "SOL9302,CUST9302,2000,COMPLETED,BIZ,2026-04-02",
                "SOL9303,CUST9303,3000,COMPLETED,IND,2026-04-05",
                "SOL9304,CUST9304,4000,COMPLETED,IND,2026-04-05",
            ],
            [
                "SOL9301,CUST9301,1000,BZ,2026-04-02",
                "SOL9302,CUST9302,2000,BZ,2026-04-04",
                "SOL9303,CUST9303,3000,IN,2026-04-06",
                "SOL9304,CUST9304,4000,IND,2026-04-07",
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
        assert rows[0]["system_tier"] == "BIZ"
        assert [row["system_tier"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_install_date_tie_uses_record_order_and_consumption(self):
        """Same-date candidates should use source row order and still enforce consumption."""
        write_inputs(
            [
                "SOL9401,CUST9401,500,COMPLETED,BIZ,2026-04-05",
                "SOL9401,CUST9401,500,COMPLETED,BIZ,2026-04-05",
                "SOL9402,CUST9402,700,COMPLETED,HOME,2026-04-05",
            ],
            [
                "SOL9401,CUST9401,500,BZ,2026-04-04",
                "SOL9401,CUST9401,500,BZ,2026-04-04",
                "SOL9401,CUST9401,500,BZ,2026-04-04",
                "SOL9402,CUST9402,700,HOME,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["system_tier"] for row in rows] == ["BIZ", "BIZ", "", "HOME"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_install_date_wins_before_older_record_is_used(self):
        """Latest install_date must win when the later input row carries the later date."""
        write_inputs(
            [
                "SOL9501,CUST9501,500,COMPLETED,HOME,2026-04-03",
                "SOL9501,CUST9501,800,COMPLETED,BIZ,2026-04-06",
                "SOL9501,CUST9501,700,COMPLETED,BIZ,2026-04-05",
            ],
            [
                "SOL9501,CUST9501,800,BZ,2026-04-02",
                "SOL9501,CUST9501,700,BZ,2026-04-04",
                "SOL9501,CUST9501,500,HO,2026-04-03",
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

    def test_closed_rebate_date_is_not_eligible(self):
        """A credit whose date is listed as closed must not match."""
        write_inputs(
            ["SOL9601,CUST9601,1000,COMPLETED,BIZ,2026-04-10"],
            ["SOL9601,CUST9601,1000,BZ,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["system_tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_rebate_date_is_not_eligible(self):
        """A credit date absent from the calendar must not be treated as open."""
        write_inputs(
            ["SOL9651,CUST9651,500,COMPLETED,BIZ,2026-04-30"],
            ["SOL9651,CUST9651,500,BZ,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["system_tier"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_rebate_date_is_not_eligible(self):
        """A credit with an empty rebate_date must not match any source row."""
        write_inputs(
            ["SOL9701,CUST9701,900,COMPLETED,HOME,2026-04-05"],
            ["SOL9701,CUST9701,900,HOME,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["system_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_record_without_install_date_is_not_eligible(self):
        """A source row with an empty install_date cannot be consumed."""
        write_inputs(
            ["SOL9801,CUST9801,700,COMPLETED,IND,"],
            ["SOL9801,CUST9801,700,IN,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["system_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_alias_matches_canonical_record_and_emits_canonical_system_tier(self):
        """A IN action row should match a IND source row and report the canonical system_tier."""
        write_inputs(
            ["SOL9901,CUST9901,600,COMPLETED,IND,2026-04-10"],
            ["SOL9901,CUST9901,600,IN,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["system_tier"] == "IND"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }


    def test_mismatched_system_tier_does_not_match_even_with_valid_dates(self):
        """Date logic must not bypass the original system_tier equality requirement."""
        write_inputs(
            ["SOL9851,CUST9851,775,COMPLETED,HOME,2026-04-10"],
            ["SOL9851,CUST9851,775,BIZ,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["system_tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 775

    def test_alias_matches_canonical_record_with_dated_matching(self):
        """The HO alias should still normalize to HOME when date gates are present."""
        write_inputs(
            ["SOL9951,CUST9951,650,COMPLETED,HOME,2026-04-10"],
            ["SOL9951,CUST9951,650,HO,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["system_tier"] == "HOME"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 650,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
