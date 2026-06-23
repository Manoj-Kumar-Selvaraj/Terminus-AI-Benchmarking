"""Milestone 3 verifier tests for dated rebate reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
SOURCE_FILE = APP / "data" / "cycles.csv"
ACTION_FILE = APP / "data" / "rebates.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "cycle_rebate_report.csv"
SUMMARY = APP / "out" / "cycle_rebate_summary.json"
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
    SOURCE_FILE.write_text("cycle_id,customer_id,amount_cents,status,machine_tier,cycle_date\n" + "\n".join(bill_rows) + "\n")
    ACTION_FILE.write_text("cycle_id,customer_id,amount_cents,machine_tier,rebate_date\n" + "\n".join(credit_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_legacy_inputs(source_rows, action_rows):
    """Pre-date schema: milestone 3 must keep milestone 2 behavior without calendar gates."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_FILE.write_text(
        "cycle_id,customer_id,amount_cents,status,machine_tier\n" + "\n".join(source_rows) + "\n"
    )
    ACTION_FILE.write_text(
        "cycle_id,customer_id,amount_cents,machine_tier\n" + "\n".join(action_rows) + "\n"
    )
    CALENDAR.write_text("")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)




def run_program():
    """Run the compiled program and parse its CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone3:
    """Date gates and latest eligible source-row selection for rebates."""

    def test_milestone3_report_header_and_status_vocabulary(self):
        """Milestone 3 keeps the same report schema and MATCHED/UNMATCHED status labels."""
        write_legacy_inputs(
            ["LDM0001,CUST0001,100,COMPLETED,WASH"],
            ["LDM0001,CUST0001,100,WS"],
        )
        rows, _ = run_program()
        with REPORT.open(newline="") as handle:
            assert handle.readline().strip() == "cycle_id,customer_id,machine_tier,amount_cents,status"
        assert {row["status"] for row in rows} <= {"MATCHED", "UNMATCHED"}


    def test_legacy_schema_without_dates_keeps_prior_alias_and_consumption(self):
        """Pre-date inputs should keep milestone 2 matching without requiring calendar dates."""
        write_legacy_inputs(
            [
                "LDM9001,CUST9001,1200,COMPLETED,COMBO",
                "LDM9001,CUST9001,1200,COMPLETED,COMBO",
                "LDM9002,CUST9002,700,COMPLETED,WASH",
            ],
            [
                "LDM9001,CUST9001,1200,CB",
                "LDM9001,CUST9001,1200,CB",
                "LDM9002,CUST9002,700,WS",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["machine_tier"] for row in rows] == ["COMBO", "COMBO", "WASH"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 3100,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }


    def test_open_rebate_date_and_latest_cycle_date_win(self):
        """Open rebate_date gates matching; matched row uses canonical machine_tier from latest cycle_date."""
        write_inputs(
            [
                "LDM9301,CUST9301,1000,COMPLETED,WASH,2026-04-03",
                "LDM9301,CUST9301,1000,COMPLETED,DRY,2026-04-04",
                "LDM9302,CUST9302,2000,COMPLETED,DRY,2026-04-02",
                "LDM9303,CUST9303,3000,COMPLETED,COMBO,2026-04-05",
                "LDM9304,CUST9304,4000,COMPLETED,COMBO,2026-04-05",
            ],
            [
                "LDM9301,CUST9301,1000,DR,2026-04-02",
                "LDM9302,CUST9302,2000,DR,2026-04-04",
                "LDM9303,CUST9303,3000,CB,2026-04-06",
                "LDM9304,CUST9304,4000,COMBO,2026-04-07",
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
        assert rows[0]["machine_tier"] == "DRY"
        assert [row["machine_tier"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_cycle_date_tie_uses_record_order_and_consumption(self):
        """Same-date candidates should use source row order and still enforce consumption."""
        write_inputs(
            [
                "LDM9401,CUST9401,500,COMPLETED,DRY,2026-04-05",
                "LDM9401,CUST9401,500,COMPLETED,DRY,2026-04-05",
                "LDM9402,CUST9402,700,COMPLETED,WASH,2026-04-05",
            ],
            [
                "LDM9401,CUST9401,500,DR,2026-04-04",
                "LDM9401,CUST9401,500,DR,2026-04-04",
                "LDM9401,CUST9401,500,DR,2026-04-04",
                "LDM9402,CUST9402,700,WASH,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["machine_tier"] for row in rows] == ["DRY", "DRY", "", "WASH"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_cycle_date_wins_before_older_record_is_used(self):
        """Latest cycle_date must win when the later input row carries the later date."""
        write_inputs(
            [
                "LDM9501,CUST9501,500,COMPLETED,WASH,2026-04-03",
                "LDM9501,CUST9501,800,COMPLETED,DRY,2026-04-06",
                "LDM9501,CUST9501,700,COMPLETED,DRY,2026-04-05",
            ],
            [
                "LDM9501,CUST9501,800,DR,2026-04-02",
                "LDM9501,CUST9501,700,DR,2026-04-04",
                "LDM9501,CUST9501,500,WS,2026-04-03",
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
            ["LDM9601,CUST9601,1000,COMPLETED,DRY,2026-04-10"],
            ["LDM9601,CUST9601,1000,DR,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["machine_tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_rebate_date_is_not_eligible(self):
        """A credit date absent from the calendar must not be treated as open."""
        write_inputs(
            ["LDM9651,CUST9651,500,COMPLETED,DRY,2026-04-30"],
            ["LDM9651,CUST9651,500,DR,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["machine_tier"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_rebate_date_is_not_eligible(self):
        """A credit with an empty rebate_date must not match any source row."""
        write_inputs(
            ["LDM9701,CUST9701,900,COMPLETED,WASH,2026-04-05"],
            ["LDM9701,CUST9701,900,WASH,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["machine_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_record_without_cycle_date_is_not_eligible(self):
        """A source row with an empty cycle_date cannot be consumed."""
        write_inputs(
            ["LDM9801,CUST9801,700,COMPLETED,COMBO,"],
            ["LDM9801,CUST9801,700,CB,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["machine_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_cb_alias_matches_canonical_record_and_emits_canonical_machine_tier(self):
        """A CB cycle rebate should match a COMBO source row and report the canonical machine_tier."""
        write_inputs(
            ["LDM9901,CUST9901,600,COMPLETED,COMBO,2026-04-10"],
            ["LDM9901,CUST9901,600,CB,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["machine_tier"] == "COMBO"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }


    def test_mismatched_machine_tier_does_not_match_even_with_valid_dates(self):
        """Date logic must not bypass the original machine_tier equality requirement."""
        write_inputs(
            ["LDM9851,CUST9851,775,COMPLETED,WASH,2026-04-10"],
            ["LDM9851,CUST9851,775,DRY,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["machine_tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 775

    def test_alias_matches_canonical_record_with_dated_matching(self):
        """The WS alias should still normalize to WASH when date gates are present."""
        write_inputs(
            ["LDM9951,CUST9951,650,COMPLETED,WASH,2026-04-10"],
            ["LDM9951,CUST9951,650,WS,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["machine_tier"] == "WASH"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 650,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
