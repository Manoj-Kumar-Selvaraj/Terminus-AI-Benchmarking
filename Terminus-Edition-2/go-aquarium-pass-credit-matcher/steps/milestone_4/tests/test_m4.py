"""Milestone 4 verifier tests for pass credit reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
PASSES = APP / "data" / "passes.csv"
CREDITS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
METHODS = APP / "config" / "methods.csv"
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
    """Compile the Go reconciliation CLI once for all milestone 4 tests."""
    build_program()


def write_inputs(pass_rows, credit_rows, calendar_rows=None, dated=False):
    """Replace CSV inputs and optional calendar with a scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    pass_header = "pass_id,guest_id,amount_cents,status,program" + (",valid_until" if dated else "")
    credit_header = "pass_id,guest_id,amount_cents,program" + (",credit_date" if dated else "")
    PASSES.write_text(pass_header + "\n" + "\n".join(pass_rows) + "\n")
    CREDITS.write_text(credit_header + "\n" + "\n".join(credit_rows) + "\n")
    if calendar_rows is not None:
        CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_methods(rows):
    """Replace program policy with enabled flags and priorities."""
    METHODS.write_text("program,enabled,priority\n" + "\n".join(rows) + "\n")


def run_program():
    """Run the compiled program and parse its CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone3Regression:
    """Key M3 behaviours that must still pass after M4 changes."""

    def test_open_credit_date_gates_matching_and_latest_valid_until_wins(self):
        """Open credit dates should gate matching and latest eligible valid_until should win."""
        write_inputs(
            [
                "BILL9301,CUST9301,1000,ACTIVE,GENERAL,2026-04-03",
                "BILL9301,CUST9301,1000,ACTIVE,TOUR,2026-04-04",
                "BILL9302,CUST9302,2000,ACTIVE,TOUR,2026-04-02",
            ],
            [
                "BILL9301,CUST9301,1000,TR,2026-04-02",
                "BILL9302,CUST9302,2000,TR,2026-04-04",
            ],
            ["2026-04-02 open", "2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[0]["program"] == "TOUR"
        assert summary["matched_amount_cents"] == 1000
        assert summary["unmatched_amount_cents"] == 2000

    def test_closed_credit_date_is_not_eligible(self):
        """A credit whose date is listed as closed must not match."""
        write_inputs(
            ["BILL9601,CUST9601,1000,ACTIVE,TOUR,2026-04-10"],
            ["BILL9601,CUST9601,1000,TR,2026-04-05"],
            ["2026-04-05 closed"],
            dated=True,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["program"] == ""
        assert summary["unmatched_count"] == 1

    def test_undated_csv_without_date_columns_preserves_matching(self):
        """Older CSVs without date columns should keep the prior matching behavior."""
        write_inputs(
            ["OLD9001,CUST9001,3200,ACTIVE,TOUR"],
            ["OLD9001,CUST9001,3200,TR"],
            dated=False,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["program"] == "TOUR"
        assert summary["matched_amount_cents"] == 3200

    def test_pass_without_valid_until_is_not_eligible(self):
        """A pass with an empty valid_until cannot be consumed in dated mode."""
        write_inputs(
            ["BILL9801,CUST9801,700,ACTIVE,MEMBER,"],
            ["BILL9801,CUST9801,700,MEM,2026-04-04"],
            ["2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_credit_date_after_valid_until_stays_unmatched(self):
        """credit_date later than valid_until must stay unmatched under policy gating."""
        write_methods(["GENERAL,true,1", "TOUR,true,2", "MEMBER,true,3"])
        write_inputs(
            ["BILL9711,CUST9711,600,ACTIVE,TOUR,2026-04-03"],
            ["BILL9711,CUST9711,600,TR,2026-04-05"],
            ["2026-04-03 open", "2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["program"] == ""
        assert summary["matched_count"] == 0


class TestMilestone4:
    """Config-driven program policy and ANY program ranking."""

    def test_disabled_program_rejects_otherwise_valid_credit(self):
        """Disabled methods.csv programs must not match even with valid ids and aliases."""
        write_methods(["GENERAL,true,2", "TOUR,false,1", "MEMBER,true,3"])
        write_inputs(
            ["CFG1001,CUST1001,1200,ACTIVE,TOUR,2026-04-10"],
            ["CFG1001,CUST1001,1200,TR,2026-04-05"],
            ["2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["program"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1200,
        }

    def test_any_same_date_uses_config_priority_before_pass_order(self):
        """ANY ties on valid_until should use configured priority before pass row order."""
        write_methods(["GENERAL,true,5", "TOUR,true,3", "MEMBER,true,1"])
        write_inputs(
            [
                "ANY2001,CUST2001,700,ACTIVE,GENERAL,2026-04-08",
                "ANY2001,CUST2001,700,ACTIVE,TOUR,2026-04-08",
                "ANY2001,CUST2001,700,ACTIVE,MEMBER,2026-04-08",
            ],
            ["ANY2001,CUST2001,700,ANY,2026-04-04"],
            ["2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["program"] == "MEMBER"
        assert summary["matched_count"] == 1

    def test_any_equal_priority_tie_uses_earliest_pass_row(self):
        """ANY ties on date and priority should visibly choose the earliest pass row."""
        write_methods(["GENERAL,true,1", "TOUR,true,1", "MEMBER,true,9"])
        write_inputs(
            [
                "ANY3001,CUST3001,800,ACTIVE,GENERAL,2026-04-09",
                "ANY3001,CUST3001,800,ACTIVE,TOUR,2026-04-09",
            ],
            ["ANY3001,CUST3001,800,ANY,2026-04-04"],
            ["2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["program"] == "GENERAL"
        assert summary["matched_amount_cents"] == 800

    def test_any_consumes_selected_row_and_next_credit_uses_next_best(self):
        """ANY matching should consume by row position and rerank remaining candidates."""
        write_methods(["GENERAL,true,1", "TOUR,true,2", "MEMBER,true,3"])
        write_inputs(
            [
                "ANY4001,CUST4001,500,ACTIVE,GENERAL,2026-04-07",
                "ANY4001,CUST4001,500,ACTIVE,TOUR,2026-04-07",
            ],
            [
                "ANY4001,CUST4001,500,ANY,2026-04-04",
                "ANY4001,CUST4001,500,ANY,2026-04-04",
                "ANY4001,CUST4001,500,ANY,2026-04-04",
            ],
            ["2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["program"] for row in rows] == ["GENERAL", "TOUR", ""]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1000,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_non_any_still_requires_exact_canonical_program_under_config_policy(self):
        """Config policy must not turn named program credits into wildcard matches."""
        write_methods(["GENERAL,true,1", "TOUR,true,2", "MEMBER,true,3"])
        write_inputs(
            ["CFG5001,CUST5001,900,ACTIVE,GENERAL,2026-04-10"],
            ["CFG5001,CUST5001,900,TOUR,2026-04-05"],
            ["2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["program"] == ""
        assert summary["unmatched_amount_cents"] == 900

    def test_malformed_priority_ranks_after_numeric_priorities(self):
        """A malformed priority value should rank after all numeric priorities."""
        write_methods(["GENERAL,true,fast", "TOUR,true,1", "MEMBER,true,3"])
        write_inputs(
            [
                "ANY6001,CUST6001,640,ACTIVE,GENERAL,2026-04-09",
                "ANY6001,CUST6001,640,ACTIVE,TOUR,2026-04-09",
            ],
            ["ANY6001,CUST6001,640,ANY,2026-04-04"],
            ["2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["program"] == "TOUR"
        assert summary["matched_count"] == 1

    def test_undated_csv_honors_disabled_program_policy(self):
        """Undated CSVs should still honour methods.csv enabled flags."""
        write_methods(["GENERAL,true,1", "TOUR,false,2", "MEMBER,true,3"])
        write_inputs(
            ["OLD9701,CUST9701,450,ACTIVE,TOUR"],
            ["OLD9701,CUST9701,450,TR"],
            dated=False,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert summary["unmatched_amount_cents"] == 450

    def test_any_with_closed_credit_date_is_ineligible(self):
        """ANY must still respect open credit_date gates together with program policy."""
        write_methods(["GENERAL,true,1", "TOUR,true,2", "MEMBER,true,3"])
        write_inputs(
            [
                "ANY7001,CUST7001,550,ACTIVE,GENERAL,2026-04-10",
                "ANY7001,CUST7001,550,ACTIVE,TOUR,2026-04-10",
            ],
            ["ANY7001,CUST7001,550,ANY,2026-04-05"],
            ["2026-04-05 closed"],
            dated=True,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_any_emits_canonical_program_not_any_in_report(self):
        """Matched ANY credits must emit the selected pass program, never 'ANY'."""
        write_methods(["GENERAL,true,1", "TOUR,true,2", "MEMBER,true,3"])
        write_inputs(
            ["ANY8001,CUST8001,300,ACTIVE,GENERAL,2026-04-10"],
            ["ANY8001,CUST8001,300,ANY,2026-04-05"],
            ["2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["program"] == "GENERAL"
        assert rows[0]["program"] != "ANY"
        assert summary["matched_amount_cents"] == 300

    def test_blank_credit_program_matches_without_priority_ordering(self):
        """Blank program credits should match without methods.csv priority ordering."""
        write_methods(["GENERAL,true,5", "TOUR,true,1", "MEMBER,true,2"])
        write_inputs(
            [
                "BLK2001,CUST2001,700,ACTIVE,GENERAL,2026-04-08",
                "BLK2001,CUST2001,700,ACTIVE,TOUR,2026-04-08",
            ],
            ["BLK2001,CUST2001,700,,2026-04-04"],
            ["2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["program"] == "GENERAL"
        assert summary["matched_count"] == 1

    def test_blank_credit_program_still_rejects_disabled_pass_program(self):
        """Blank program credits must not match passes whose program is disabled in methods.csv."""
        write_methods(["GENERAL,true,1", "TOUR,false,2", "MEMBER,true,3"])
        write_inputs(
            ["BLK3001,CUST3001,800,ACTIVE,TOUR,2026-04-10"],
            ["BLK3001,CUST3001,800,,2026-04-05"],
            ["2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["program"] == ""
        assert summary["unmatched_amount_cents"] == 800
