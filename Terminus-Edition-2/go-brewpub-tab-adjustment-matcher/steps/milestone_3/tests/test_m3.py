"""Milestone 3 verifier tests for dated tab adjustment reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
TABS = APP / "data" / "tabs.csv"
ADJUSTMENTS = APP / "data" / "adjustments.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "tab_adjustment_report.csv"
SUMMARY = APP / "out" / "tab_adjustment_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go tab adjustment reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 3 tests."""
    build_program()


def write_inputs(tab_rows, adjustment_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated adjustment scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    TABS.write_text("tab_id,patron_id,amount_cents,status,pour_tier,tab_date\n" + "\n".join(tab_rows) + "\n")
    ADJUSTMENTS.write_text("tab_id,patron_id,amount_cents,pour_tier,adjust_date\n" + "\n".join(adjustment_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_undated_inputs(tab_rows, adjustment_rows):
    """Replace inputs without date columns to verify milestone 2 fallback."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    TABS.write_text("tab_id,patron_id,amount_cents,status,pour_tier\n" + "\n".join(tab_rows) + "\n")
    ADJUSTMENTS.write_text("tab_id,patron_id,amount_cents,pour_tier\n" + "\n".join(adjustment_rows) + "\n")
    CALENDAR.write_text("2026-04-05 closed\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse its CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone3:
    """Date gates and latest eligible tab selection for adjustments."""

    def test_undated_inputs_skip_calendar_gates(self):
        """Without date columns, milestone 2 matching should still run."""
        write_undated_inputs(
            ["TAB9201,CUST9201,900,COMPLETED,PINT"],
            ["TAB9201,CUST9201,900,PT"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["pour_tier"] == "PINT"
        assert summary["matched_count"] == 1

    def test_open_calendar_date_allows_matching(self):
        """Credits whose calendar date is listed as open (case-insensitive) may match."""
        write_inputs(
            ["TAB9301,CUST9301,1000,COMPLETED,PITCH,2026-04-04"],
            ["TAB9301,CUST9301,1000,PC,2026-04-02"],
            ["2026-04-02 OpEn"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["pour_tier"] == "PITCH"

    def test_three_adjustments_match_two_tied_tab_rows_once(self):
        """Three adjustments against two tied tab rows should match twice then stay unmatched."""
        write_inputs(
            [
                "TAB9401,CUST9401,500,COMPLETED,PITCH,2026-04-05",
                "TAB9401,CUST9401,500,COMPLETED,PITCH,2026-04-05",
            ],
            [
                "TAB9401,CUST9401,500,PC,2026-04-04",
                "TAB9401,CUST9401,500,PC,2026-04-04",
                "TAB9401,CUST9401,500,PC,2026-04-04",
            ],
            ["2026-04-04 open", "2026-04-05 open"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert summary["unmatched_amount_cents"] == 500

    def test_two_adjustments_match_two_tab_date_rows(self):
        """Latest eligible tab dates must be consumed first, which can leave later adjustments unmatched."""
        write_inputs(
            [
                "TAB9501,CUST9501,800,COMPLETED,PITCH,2026-04-03",
                "TAB9501,CUST9501,800,COMPLETED,PITCH,2026-04-06",
            ],
            [
                "TAB9501,CUST9501,800,PC,2026-04-03",
                "TAB9501,CUST9501,800,PC,2026-04-06",
            ],
            ["2026-04-03 open", "2026-04-06 open"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["pour_tier"] for row in rows] == ["PITCH", ""]
        assert summary["matched_amount_cents"] == 800
        assert summary["unmatched_amount_cents"] == 800

    def test_adjust_date_after_tab_date_is_not_eligible(self):
        """An adjust_date later than tab_date must not match even when the calendar is open."""
        write_inputs(
            ["TAB9671,CUST9671,500,COMPLETED,PITCH,2026-04-10"],
            ["TAB9671,CUST9671,500,PC,2026-04-15"],
            ["2026-04-15 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["pour_tier"] == ""

    def test_closed_adjust_date_is_not_eligible(self):
        """An adjustment whose date is listed as closed must not match."""
        write_inputs(
            ["TAB9601,CUST9601,1000,COMPLETED,PITCH,2026-04-10"],
            ["TAB9601,CUST9601,1000,PC,2026-04-05"],
            ["2026-04-05   closed  "],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["pour_tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_adjust_date_is_not_eligible(self):
        """An adjust_date absent from the calendar must not be treated as open."""
        write_inputs(
            ["TAB9651,CUST9651,500,COMPLETED,PITCH,2026-04-30"],
            ["TAB9651,CUST9651,500,PC,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["pour_tier"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_malformed_adjust_date_is_not_eligible_even_when_listed_open(self):
        """A malformed adjust_date must not match even if the calendar lists that text as open."""
        write_inputs(
            ["TAB9661,CUST9661,650,COMPLETED,PITCH,2026-04-30"],
            ["TAB9661,CUST9661,650,PC,0000-00-00"],
            ["0000-00-00 open", "2026-04-30 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["pour_tier"] == ""

    def test_non_numeric_adjust_date_is_not_eligible(self):
        """An adjust_date with non-numeric month digits is malformed and cannot match."""
        write_inputs(
            ["TAB9821,CUST9821,300,COMPLETED,PITCH,2026-04-30"],
            ["TAB9821,CUST9821,300,PC,2026-ab-05"],
            ["2026-ab-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"

    def test_missing_adjust_date_is_not_eligible(self):
        """An adjustment with an empty adjust_date must not match any tab."""
        write_inputs(
            ["TAB9701,CUST9701,900,COMPLETED,PINT,2026-04-05"],
            ["TAB9701,CUST9701,900,PINT,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["pour_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_invalid_month_tab_date_is_not_eligible(self):
        """A tab_date with month outside 01-12 is malformed and cannot be consumed."""
        write_inputs(
            ["TAB9841,CUST9841,400,COMPLETED,PITCH,2026-13-01"],
            ["TAB9841,CUST9841,400,PC,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"

    def test_invalid_day_adjust_date_is_not_eligible(self):
        """An adjust_date with day outside 01-31 is malformed and cannot match even if listed open."""
        write_inputs(
            ["TAB9842,CUST9842,650,COMPLETED,PINT,2026-04-10"],
            ["TAB9842,CUST9842,650,PT,2026-04-32"],
            ["2026-04-32 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["pour_tier"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 650,
        }

    def test_record_without_tab_date_is_not_eligible(self):
        """A tab with an empty tab_date cannot be consumed."""
        write_inputs(
            ["TAB9801,CUST9801,700,COMPLETED,KEG,"],
            ["TAB9801,CUST9801,700,KG,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["pour_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_calendar_date_and_state_trim_whitespace_before_compare(self):
        """Calendar date and state tokens with surrounding spaces should still gate matching."""
        write_inputs(
            ["TAB9681,CUST9681,600,COMPLETED,PITCH,2026-04-10"],
            ["TAB9681,CUST9681,600,PC,2026-04-05"],
            ["  2026-04-05   open  "],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["pour_tier"] == "PITCH"

    def test_report_header_and_summary_keys_are_stable(self):
        """Dated batches must keep the required report header and summary JSON keys."""
        write_inputs(
            ["TAB9921,CUST9921,100,COMPLETED,PINT,2026-04-10"],
            ["TAB9921,CUST9921,100,PT,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "tab_id,patron_id,pour_tier,amount_cents,status"
        assert set(summary.keys()) == {
            "matched_count",
            "matched_amount_cents",
            "unmatched_count",
            "unmatched_amount_cents",
        }
        assert all(isinstance(summary[key], int) for key in summary)

    def test_kg_alias_matches_keg_record_and_emits_canonical_pour_tier(self):
        """A KG adjustment should match a KEG tab and report the canonical pour_tier."""
        write_inputs(
            ["TAB9901,CUST9901,600,COMPLETED,KEG,2026-04-10"],
            ["TAB9901,CUST9901,600,KG,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["pour_tier"] == "KEG"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }


    def test_mismatched_pour_tier_does_not_match_even_with_valid_dates(self):
        """Date logic must not bypass the original pour_tier equality requirement."""
        write_inputs(
            ["TAB9851,CUST9851,775,COMPLETED,PINT,2026-04-10"],
            ["TAB9851,CUST9851,775,PITCH,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["pour_tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 775

    def test_pt_alias_matches_pint_record_with_dated_matching(self):
        """The PT alias should still normalize to PINT when date gates are present."""
        write_inputs(
            ["TAB9951,CUST9951,650,COMPLETED,PINT,2026-04-10"],
            ["TAB9951,CUST9951,650,PT,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["pour_tier"] == "PINT"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 650,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
