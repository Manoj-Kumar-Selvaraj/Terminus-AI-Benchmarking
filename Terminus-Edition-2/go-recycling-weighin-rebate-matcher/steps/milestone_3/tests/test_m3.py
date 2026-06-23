"""Milestone 3 verifier tests for dated rebate reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
SOURCE_FILE = APP / "data" / "weighins.csv"
ACTION_FILE = APP / "data" / "rebates.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "weighin_rebate_report.csv"
SUMMARY = APP / "out" / "weighin_rebate_summary.json"
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
    SOURCE_FILE.write_text("weighin_id,account_id,amount_cents,status,material_tier,weighin_date\n" + "\n".join(bill_rows) + "\n")
    ACTION_FILE.write_text("weighin_id,account_id,amount_cents,material_tier,rebate_date\n" + "\n".join(credit_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_legacy_inputs(source_rows, action_rows):
    """Pre-date schema: milestone 3 must keep milestone 2 behavior without calendar gates."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_FILE.write_text(
        "weighin_id,account_id,amount_cents,status,material_tier\n" + "\n".join(source_rows) + "\n"
    )
    ACTION_FILE.write_text(
        "weighin_id,account_id,amount_cents,material_tier\n" + "\n".join(action_rows) + "\n"
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
    """Date gates and latest eligible source-row selection for action rows."""

    def test_legacy_schema_without_dates_keeps_prior_alias_and_consumption(self):
        """Pre-date inputs should keep milestone 2 matching without requiring calendar dates."""
        write_legacy_inputs(
            [
                "RCY9001,CUST9001,1200,COMPLETED,GLASS",
                "RCY9001,CUST9001,1200,COMPLETED,GLASS",
                "RCY9002,CUST9002,700,COMPLETED,METAL",
            ],
            [
                "RCY9001,CUST9001,1200,GL",
                "RCY9001,CUST9001,1200,GL",
                "RCY9002,CUST9002,700,MT",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["material_tier"] for row in rows] == ["GLASS", "GLASS", "METAL"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 3100,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }


    def test_open_rebate_date_and_latest_weighin_date_win(self):
        """Open action dates should gate matching and the latest eligible source date should win."""
        write_inputs(
            [
                "RCY9301,CUST9301,1000,COMPLETED,METAL,2026-04-03",
                "RCY9301,CUST9301,1000,COMPLETED,PAPER,2026-04-04",
                "RCY9302,CUST9302,2000,COMPLETED,PAPER,2026-04-02",
                "RCY9303,CUST9303,3000,COMPLETED,GLASS,2026-04-05",
                "RCY9304,CUST9304,4000,COMPLETED,GLASS,2026-04-05",
            ],
            [
                "RCY9301,CUST9301,1000,PP,2026-04-02",
                "RCY9302,CUST9302,2000,PP,2026-04-04",
                "RCY9303,CUST9303,3000,GL,2026-04-06",
                "RCY9304,CUST9304,4000,GLASS,2026-04-07",
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
        assert rows[0]["material_tier"] == "PAPER"
        assert [row["material_tier"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_weighin_date_tie_uses_record_order_and_consumption(self):
        """Same-date candidates should use source row order and still enforce consumption."""
        write_inputs(
            [
                "RCY9401,CUST9401,500,COMPLETED,PAPER,2026-04-05",
                "RCY9401,CUST9401,500,COMPLETED,PAPER,2026-04-05",
                "RCY9402,CUST9402,700,COMPLETED,METAL,2026-04-05",
            ],
            [
                "RCY9401,CUST9401,500,PP,2026-04-04",
                "RCY9401,CUST9401,500,PP,2026-04-04",
                "RCY9401,CUST9401,500,PP,2026-04-04",
                "RCY9402,CUST9402,700,METAL,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["material_tier"] for row in rows] == ["PAPER", "PAPER", "", "METAL"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_weighin_date_wins_before_older_record_is_used(self):
        """Latest weighin_date must win when the later input row carries the later date."""
        write_inputs(
            [
                "RCY9501,CUST9501,500,COMPLETED,METAL,2026-04-03",
                "RCY9501,CUST9501,800,COMPLETED,PAPER,2026-04-06",
                "RCY9501,CUST9501,700,COMPLETED,PAPER,2026-04-05",
            ],
            [
                "RCY9501,CUST9501,800,PP,2026-04-02",
                "RCY9501,CUST9501,700,PP,2026-04-04",
                "RCY9501,CUST9501,500,MT,2026-04-03",
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
            ["RCY9601,CUST9601,1000,COMPLETED,PAPER,2026-04-10"],
            ["RCY9601,CUST9601,1000,PP,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["material_tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_rebate_date_is_not_eligible(self):
        """A credit date absent from the calendar must not be treated as open."""
        write_inputs(
            ["RCY9651,CUST9651,500,COMPLETED,PAPER,2026-04-30"],
            ["RCY9651,CUST9651,500,PP,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["material_tier"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_rebate_date_is_not_eligible(self):
        """A credit with an empty rebate_date must not match any source row."""
        write_inputs(
            ["RCY9701,CUST9701,900,COMPLETED,METAL,2026-04-05"],
            ["RCY9701,CUST9701,900,METAL,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["material_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_record_without_weighin_date_is_not_eligible(self):
        """A source row with an empty weighin_date cannot be consumed."""
        write_inputs(
            ["RCY9801,CUST9801,700,COMPLETED,GLASS,"],
            ["RCY9801,CUST9801,700,GL,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["material_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_gl_alias_matches_canonical_record_and_emits_canonical_material_tier(self):
        """A GL action row should match a GLASS source row and report the canonical material_tier."""
        write_inputs(
            ["RCY9901,CUST9901,600,COMPLETED,GLASS,2026-04-10"],
            ["RCY9901,CUST9901,600,GL,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["material_tier"] == "GLASS"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }


    def test_mismatched_material_tier_does_not_match_even_with_valid_dates(self):
        """Date logic must not bypass the original material_tier equality requirement."""
        write_inputs(
            ["RCY9851,CUST9851,775,COMPLETED,METAL,2026-04-10"],
            ["RCY9851,CUST9851,775,PAPER,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["material_tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 775

    def test_alias_matches_canonical_record_with_dated_matching(self):
        """The MT alias should still normalize to METAL when date gates are present."""
        write_inputs(
            ["RCY9951,CUST9951,650,COMPLETED,METAL,2026-04-10"],
            ["RCY9951,CUST9951,650,MT,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["material_tier"] == "METAL"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 650,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
