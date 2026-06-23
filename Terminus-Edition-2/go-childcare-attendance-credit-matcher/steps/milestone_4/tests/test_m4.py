"""Milestone 4 verifier tests for methods, ANY, child limits, and blackouts."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
SOURCES = APP / "data" / "attendances.csv"
CREDITS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
METHODS = APP / "config" / "methods.csv"
LIMITS = APP / "config" / "child_limits.csv"
BLACKOUTS = APP / "config" / "blackouts.csv"
REPORT = APP / "out" / "attendance_credit_report.csv"
SUMMARY = APP / "out" / "attendance_credit_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")
DEFAULT_METHODS = "care_type,enabled,priority\nHALF,true,2\nFULL,true,1\nEXT,true,3\n"


def build_program():
    """Compile the Go attendance credit reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 4 tests."""
    build_program()


def write_inputs(
    attendance_rows,
    credit_rows,
    calendar_rows,
    method_rows=None,
    limit_rows=None,
    blackout_rows=None,
    dated=True,
):
    """Replace CSV inputs, calendar, and config files with one verifier scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    if dated:
        CLASSES.write_text("attendance_id,child_id,amount_cents,status,care_type,attendance_date\n" + "\n".join(attendance_rows) + "\n")
        CREDITS.write_text("attendance_id,child_id,amount_cents,care_type,credit_date\n" + "\n".join(credit_rows) + "\n")
    else:
        CLASSES.write_text("attendance_id,child_id,amount_cents,status,care_type\n" + "\n".join(attendance_rows) + "\n")
        CREDITS.write_text("attendance_id,child_id,amount_cents,care_type\n" + "\n".join(credit_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    if method_rows is not None:
        METHODS.write_text("care_type,enabled,priority\n" + "\n".join(method_rows) + "\n")
    else:
        METHODS.write_text(DEFAULT_METHODS)
    limit_body = "" if limit_rows is None else "\n".join(limit_rows) + ("\n" if limit_rows else "")
    LIMITS.write_text("child_id,care_type,effective_date,max_daily_amount,status\n" + limit_body)
    blackout_body = "" if blackout_rows is None else "\n".join(blackout_rows) + ("\n" if blackout_rows else "")
    BLACKOUTS.write_text("care_type,start_date,end_date,state\n" + blackout_body)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse its CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone4:
    """Methods config, ANY credits, child limits, and blackouts interact with prior matching gates."""

    def test_disabled_configured_care_type_rejects_otherwise_valid_credit(self):
        """Disabled methods.csv care types must not match even with valid ids, dates, and aliases."""
        write_inputs(
            ["CFG1001,CUST1001,1200,ACTIVE,FULL,2026-04-10"],
            ["CFG1001,CUST1001,1200,FD,2026-04-05"],
            ["2026-04-05 open"],
            ["HALF,true,2", "FULL,false,1", "EXT,true,3"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["care_type"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1200,
        }

    def test_any_same_date_uses_config_priority_before_attendance_order(self):
        """ANY ties on visit date should use configured priority before attendance row order."""
        write_inputs(
            [
                "ANY2001,CUST2001,700,ACTIVE,HALF,2026-04-08",
                "ANY2001,CUST2001,700,ACTIVE,EXT,2026-04-08",
                "ANY2001,CUST2001,700,ACTIVE,FULL,2026-04-08",
            ],
            ["ANY2001,CUST2001,700,ANY,2026-04-04"],
            ["2026-04-04 open"],
            ["HALF,true,5", "FULL,true,1", "EXT,true,3"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["care_type"] == "FULL"
        assert summary["matched_count"] == 1

    def test_any_equal_priority_tie_uses_earliest_attendance_row(self):
        """ANY ties on date and priority should choose the earliest attendance input row."""
        write_inputs(
            [
                "ANY3001,CUST3001,800,ACTIVE,HALF,2026-04-09",
                "ANY3001,CUST3001,800,ACTIVE,FULL,2026-04-09",
            ],
            ["ANY3001,CUST3001,800,ANY,2026-04-04"],
            ["2026-04-04 open"],
            ["HALF,true,1", "FULL,true,1", "EXT,true,9"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["care_type"] == "HALF"
        assert summary["matched_amount_cents"] == 800

    def test_any_consumes_selected_row_and_reranks_remaining_candidates(self):
        """ANY matching should consume by row position and rerank remaining candidates."""
        write_inputs(
            [
                "ANY4001,CUST4001,500,ACTIVE,HALF,2026-04-07",
                "ANY4001,CUST4001,500,ACTIVE,FULL,2026-04-07",
            ],
            [
                "ANY4001,CUST4001,500,ANY,2026-04-04",
                "ANY4001,CUST4001,500,ANY,2026-04-04",
                "ANY4001,CUST4001,500,ANY,2026-04-04",
            ],
            ["2026-04-04 open"],
            ["HALF,true,1", "FULL,true,2", "EXT,true,3"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["care_type"] for row in rows] == ["HALF", "FULL", ""]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1000,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_non_any_still_requires_exact_canonical_care_type(self):
        """Config policy must not turn named class-type credits into wildcard matches."""
        write_inputs(
            ["CFG5001,CUST5001,900,ACTIVE,HALF,2026-04-10"],
            ["CFG5001,CUST5001,900,FD,2026-04-05"],
            ["2026-04-05 open"],
            ["HALF,true,1", "FULL,true,2", "EXT,true,3"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["care_type"] == ""
        assert summary["unmatched_amount_cents"] == 900

    def test_missing_and_malformed_methods_do_not_enable_care_type(self):
        """Missing, blank, malformed, and non-true method rows should leave types ineligible."""
        write_inputs(
            [
                "BILLM411,CUSTM411,1100,ACTIVE,HALF,2026-05-12",
                "BILLM412,CUSTM412,1200,ACTIVE,FULL,2026-05-12",
                "BILLM413,CUSTM413,1300,ACTIVE,EXT,2026-05-12",
            ],
            [
                "BILLM411,CUSTM411,1100,HALF,2026-05-06",
                "BILLM412,CUSTM412,1200,FD,2026-05-06",
                "BILLM413,CUSTM413,1300,EX,2026-05-06",
            ],
            ["2026-05-06 open"],
            [
                "HALF,maybe,2",
                "FULL",
                ",true,1",
                "EXT,TRUE,3",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "MATCHED"]
        assert [row["care_type"] for row in rows] == ["", "", "EXT"]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1300,
            "unmatched_count": 2,
            "unmatched_amount_cents": 2300,
        }

    def test_methods_alias_normalization_enables_fd_entry(self):
        """Method care_type aliases such as FD should normalize before enabled checks."""
        write_inputs(
            ["CFG6001,CUST6001,750,ACTIVE,FULL,2026-04-10"],
            ["CFG6001,CUST6001,750,FD,2026-04-05"],
            ["2026-04-05 open"],
            ["FD,true,1", "HALF,true,2"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["care_type"] == "FULL"
        assert summary["matched_count"] == 1

    def test_any_undated_inputs_rank_by_priority_then_attendance_order(self):
        """Without date columns, ANY should rank only by priority then earliest attendance row."""
        write_inputs(
            [
                "UND7001,CUST7001,600,ACTIVE,EXT",
                "UND7001,CUST7001,600,ACTIVE,HALF",
                "UND7001,CUST7001,600,ACTIVE,FULL",
            ],
            ["UND7001,CUST7001,600,ANY"],
            ["2026-04-01 closed"],
            ["HALF,true,3", "FULL,true,1", "EXT,true,2"],
            dated=False,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["care_type"] == "FULL"
        assert summary["matched_amount_cents"] == 600

    def test_enabled_method_does_not_bypass_closed_calendar_date(self):
        """An enabled care type must still fail when the credit date is not open."""
        write_inputs(
            ["BILLM431,CUSTM431,1500,ACTIVE,HALF,2026-05-15"],
            ["BILLM431,CUSTM431,1500,HF,2026-05-09"],
            ["2026-05-09 closed"],
            ["HALF,true,1"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["care_type"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1500,
        }

    def test_methods_gate_preserves_latest_attendance_date_selection(self):
        """Enabled methods should not weaken latest attendance_date selection or consumption."""
        write_inputs(
            [
                "BILLM421,CUSTM421,1400,ACTIVE,HALF,2026-05-08",
                "BILLM421,CUSTM421,1400,ACTIVE,HALF,2026-05-14",
                "BILLM421,CUSTM421,1400,ACTIVE,HALF,2026-05-14",
            ],
            [
                "BILLM421,CUSTM421,1400,HF,2026-05-07",
                "BILLM421,CUSTM421,1400,HF,2026-05-07",
                "BILLM421,CUSTM421,1400,HF,2026-05-07",
                "BILLM421,CUSTM421,1400,HF,2026-05-07",
            ],
            ["2026-05-07 open"],
            ["HALF,true,1"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["care_type"] for row in rows] == ["HALF", "HALF", "HALF", ""]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 4200,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1400,
        }

    def test_latest_effective_limit_caps_daily_credits_in_credit_order(self):
        """The latest active limit should cap same child/access/date credits cumulatively."""
        write_inputs(
            [
                "LIM5001,CUST5001,600,ACTIVE,HALF,2026-06-10",
                "LIM5002,CUST5001,500,ACTIVE,HALF,2026-06-10",
                "LIM5003,CUST5001,400,ACTIVE,HALF,2026-06-10",
            ],
            [
                "LIM5001,CUST5001,600,HF,2026-06-05",
                "LIM5002,CUST5001,500,HF,2026-06-05",
                "LIM5003,CUST5001,400,HF,2026-06-05",
            ],
            ["2026-06-05 open"],
            ["HALF,true,1"],
            [
                "CUST5001,HALF,2026-05-01,900,ACTIVE",
                "CUST5001,HF,2026-06-01,1100,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["care_type"] for row in rows] == ["HALF", "HALF", ""]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1100,
            "unmatched_count": 1,
            "unmatched_amount_cents": 400,
        }

    def test_budget_is_partitioned_by_child_selected_care_type_and_credit_date(self):
        """Budget consumption should be keyed by child, selected care type, and credit_date."""
        write_inputs(
            [
                "LIM5101,CUST5101,700,ACTIVE,HALF,2026-06-10",
                "LIM5102,CUST5101,700,ACTIVE,EXT,2026-06-10",
                "LIM5103,CUST5101,700,ACTIVE,HALF,2026-06-11",
                "LIM5104,CUST5102,700,ACTIVE,HALF,2026-06-10",
            ],
            [
                "LIM5101,CUST5101,700,HF,2026-06-05",
                "LIM5102,CUST5101,700,EX,2026-06-05",
                "LIM5103,CUST5101,700,HF,2026-06-06",
                "LIM5104,CUST5102,700,HF,2026-06-05",
            ],
            ["2026-06-05 open", "2026-06-06 open"],
            ["HALF,true,1", "EXT,true,2"],
            [
                "CUST5101,HALF,2026-06-01,700,ACTIVE",
                "CUST5101,EXT,2026-06-01,700,ACTIVE",
                "CUST5102,HALF,2026-06-01,700,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "MATCHED"]
        assert [row["care_type"] for row in rows] == ["HALF", "EXT", "HALF", "HALF"]
        assert summary["matched_count"] == 4
        assert summary["matched_amount_cents"] == 2800

    def test_any_credit_uses_selected_candidate_care_type_for_limit(self):
        """ANY credits should look up budget against the care type of the selected attendance."""
        write_inputs(
            [
                "LIM5201,CUST5201,800,ACTIVE,HALF,2026-06-10",
                "LIM5201,CUST5201,800,ACTIVE,EXT,2026-06-10",
            ],
            [
                "LIM5201,CUST5201,800,ANY,2026-06-05",
                "LIM5201,CUST5201,800,ANY,2026-06-05",
            ],
            ["2026-06-05 open"],
            ["HALF,true,1", "EXT,true,2"],
            [
                "CUST5201,HALF,2026-06-01,800,ACTIVE",
                "CUST5201,EXT,2026-06-01,700,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["care_type"] for row in rows] == ["HALF", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_inactive_future_unknown_and_nonnumeric_limits_are_ignored(self):
        """Only active, effective, numeric limits for known care types should enable budget matching."""
        write_inputs(
            [
                "LIM5301,CUST5301,300,ACTIVE,HALF,2026-06-10",
                "LIM5302,CUST5302,300,ACTIVE,HALF,2026-06-10",
                "LIM5303,CUST5303,300,ACTIVE,HALF,2026-06-10",
                "LIM5304,CUST5304,300,ACTIVE,HALF,2026-06-10",
                "LIM5305,CUST5305,300,ACTIVE,HALF,2026-06-10",
            ],
            [
                "LIM5301,CUST5301,300,HF,2026-06-05",
                "LIM5302,CUST5302,300,HF,2026-06-05",
                "LIM5303,CUST5303,300,HF,2026-06-05",
                "LIM5304,CUST5304,300,HF,2026-06-05",
                "LIM5305,CUST5305,300,HF,2026-06-05",
            ],
            ["2026-06-05 open"],
            ["HALF,true,1"],
            [
                "CUST5301,HALF,2026-06-01,300,INACTIVE",
                "CUST5302,HALF,2026-06-06,300,ACTIVE",
                "CUST5303,HALF,2026-06-01,not-number,ACTIVE",
                "CUST5304,BAD,2026-06-01,300,ACTIVE",
                "CUST5305,HF,2026-06-01,300,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert [row["care_type"] for row in rows] == ["", "", "", "", "HALF"]
        assert summary["matched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1200

    def test_budget_rejection_does_not_consume_attendance_row_needed_by_later_credit(self):
        """An over-limit credit must not consume a attendance row needed by a later eligible credit."""
        write_inputs(
            [
                "LIM5401,CUST5401,900,ACTIVE,HALF,2026-06-10",
                "LIM5401,CUST5401,400,ACTIVE,HALF,2026-06-10",
            ],
            [
                "LIM5401,CUST5401,900,HF,2026-06-05",
                "LIM5401,CUST5401,400,HF,2026-06-05",
            ],
            ["2026-06-05 open"],
            ["HALF,true,1"],
            ["CUST5401,HF,2026-06-01,500,ACTIVE"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert [row["care_type"] for row in rows] == ["", "HALF"]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 400,
            "unmatched_count": 1,
            "unmatched_amount_cents": 900,
        }

    def test_undated_inputs_keep_methods_and_any_behavior_without_limits(self):
        """When credit_date is absent, child_limits.csv should not gate matching."""
        write_inputs(
            ["LIM5501,CUST5501,1000,ACTIVE,HALF"],
            ["LIM5501,CUST5501,1000,HF"],
            ["2026-06-05 closed"],
            ["HALF,true,1"],
            [],
            dated=False,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["care_type"] == "HALF"
        assert summary["matched_count"] == 1

    def test_named_credit_is_blocked_by_active_blackout_range(self):
        """A matching attendance should be ineligible when its care type is blacked out on credit_date."""
        write_inputs(
            ["BLK6001,CUST6001,600,ACTIVE,EXT,2026-07-10"],
            ["BLK6001,CUST6001,600,EX,2026-07-05"],
            ["2026-07-05 open"],
            ["EXT,true,1"],
            ["CUST6001,EXT,2026-07-01,600,ACTIVE"],
            ["EXT,2026-07-01,2026-07-06,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["care_type"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 600,
        }

    def test_any_skips_blacked_out_higher_ranked_candidate(self):
        """ANY should skip blacked-out candidates before priority ranking and report the selected type."""
        write_inputs(
            [
                "BLK6101,CUST6101,700,ACTIVE,FULL,2026-07-10",
                "BLK6101,CUST6101,700,ACTIVE,HALF,2026-07-10",
            ],
            ["BLK6101,CUST6101,700,ANY,2026-07-05"],
            ["2026-07-05 open"],
            ["FULL,true,1", "HALF,true,2"],
            [
                "CUST6101,FULL,2026-07-01,700,ACTIVE",
                "CUST6101,HALF,2026-07-01,700,ACTIVE",
            ],
            ["FD,2026-07-01,2026-07-06,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["care_type"] == "HALF"
        assert summary["matched_count"] == 1

    def test_blackout_filter_happens_before_budget_consumption(self):
        """A blacked-out candidate should not consume attendance rows or child budget."""
        write_inputs(
            [
                "BLK6201,CUST6201,900,ACTIVE,EXT,2026-07-10",
                "BLK6201,CUST6201,400,ACTIVE,EXT,2026-07-10",
            ],
            [
                "BLK6201,CUST6201,900,EX,2026-07-05",
                "BLK6201,CUST6201,400,EX,2026-07-07",
            ],
            ["2026-07-05 open", "2026-07-07 open"],
            ["EXT,true,1"],
            ["CUST6201,EXT,2026-07-01,500,ACTIVE"],
            ["EXT,2026-07-01,2026-07-06,ACTIVE"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert [row["care_type"] for row in rows] == ["", "EXT"]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 400,
            "unmatched_count": 1,
            "unmatched_amount_cents": 900,
        }

    def test_inactive_malformed_and_out_of_range_blackouts_are_ignored(self):
        """Only active well-formed blackout ranges containing credit_date should block."""
        write_inputs(
            [
                "BLK6301,CUST6301,300,ACTIVE,HALF,2026-07-10",
                "BLK6302,CUST6302,300,ACTIVE,HALF,2026-07-10",
                "BLK6303,CUST6303,300,ACTIVE,HALF,2026-07-10",
                "BLK6304,CUST6304,300,ACTIVE,HALF,2026-07-10",
            ],
            [
                "BLK6301,CUST6301,300,HF,2026-07-05",
                "BLK6302,CUST6302,300,HF,2026-07-05",
                "BLK6303,CUST6303,300,HF,2026-07-05",
                "BLK6304,CUST6304,300,HF,2026-07-05",
            ],
            ["2026-07-05 open"],
            ["HALF,true,1"],
            [
                "CUST6301,HALF,2026-07-01,300,ACTIVE",
                "CUST6302,HALF,2026-07-01,300,ACTIVE",
                "CUST6303,HALF,2026-07-01,300,ACTIVE",
                "CUST6304,HALF,2026-07-01,300,ACTIVE",
            ],
            [
                "HALF,2026-07-01,2026-07-06,INACTIVE",
                "HALF,bad-date,2026-07-06,ACTIVE",
                "HALF,2026-07-06,2026-07-10,ACTIVE",
                "BAD,2026-07-01,2026-07-06,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "MATCHED"]
        assert summary["matched_count"] == 4

    def test_undated_inputs_skip_blackouts_and_limits_but_keep_methods_and_any(self):
        """Without credit_date, blackout and limit gates should be skipped while methods and ANY behavior remains."""
        write_inputs(
            ["BLK6401,CUST6401,500,ACTIVE,EXT"],
            ["BLK6401,CUST6401,500,ANY"],
            ["2026-07-05 closed"],
            ["EXT,true,1"],
            [],
            ["EXT,2026-01-01,2026-12-31,ACTIVE"],
            dated=False,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["care_type"] == "EXT"
        assert summary["matched_amount_cents"] == 500

    def test_malformed_policy_rows_are_ignored_without_blocking_valid_rows(self):
        """Malformed method, limit, and blackout rows should be skipped while valid policy rows still allow a match."""
        write_inputs(
            ["POLICY1,CUSTPOL1,1600,ACTIVE,EXT,2026-04-10"],
            ["POLICY1,CUSTPOL1,1600,EXT,2026-04-04"],
            ["2026-04-04 open"],
            ["SHORTMETHOD", ",true,1", "EXT,true,1"],
            [
                ", EXT,2026-04-01,9999,ACTIVE",
                "CUSTPOL1,EXT",
                "CUSTPOL1,EXT,not-a-date,9999,ACTIVE",
                "CUSTPOL1,EXT,2026-04-01,2000,ACTIVE",
            ],
            [
                ",2026-04-01,2026-04-09,ACTIVE",
                "EXT,2026-04-01",
                "EXT,not-a-date,2026-04-09,ACTIVE",
                "EXT,2026-04-01,also-bad,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["care_type"] == "EXT"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 1600

    def test_malformed_and_missing_priorities_rank_after_numeric_priority(self):
        """Malformed or missing method priorities should rank after configured numeric priorities."""
        write_inputs(
            [
                "PRIORITY1,CUSTPRI1,1800,ACTIVE,HALF,2026-04-10",
                "PRIORITY1,CUSTPRI1,1800,ACTIVE,FULL,2026-04-10",
                "PRIORITY1,CUSTPRI1,1800,ACTIVE,EXT,2026-04-10",
            ],
            ["PRIORITY1,CUSTPRI1,1800,ANY,2026-04-04"],
            ["2026-04-04 open"],
            ["HALF,true,notnum", "FULL,true,2", "EXT,true"],
            ["CUSTPRI1,FULL,2026-04-01,3000,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["care_type"] == "FULL"
        assert summary["matched_amount_cents"] == 1800

    def test_equal_effective_limit_dates_prefer_earliest_limit_row(self):
        """When limit effective dates tie, the earliest limit row should decide the daily cap."""
        write_inputs(
            ["LIMITTIE1,CUSTLIM1,1500,ACTIVE,HALF,2026-04-10"],
            ["LIMITTIE1,CUSTLIM1,1500,HALF,2026-04-04"],
            ["2026-04-04 open"],
            ["HALF,true,1"],
            [
                "CUSTLIM1,HALF,2026-04-01,1000,ACTIVE",
                "CUSTLIM1,HALF,2026-04-01,2000,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["care_type"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 1500

    def test_malformed_method_rows_alone_do_not_enable_matching(self):
        """Malformed methods.csv rows must not make an otherwise valid type eligible."""
        write_inputs(
            ["METHBAD1,CUSTMET1,1300,ACTIVE,EXT,2026-04-10"],
            ["METHBAD1,CUSTMET1,1300,EXT,2026-04-04"],
            ["2026-04-04 open"],
            ["SHORTMETHOD", ",true,1", "EXT,,1"],
            ["CUSTMET1,EXT,2026-04-01,3000,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["care_type"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 1300

    def test_short_limit_rows_are_ignored_without_blocking_valid_limit(self):
        """Short limit rows should be ignored while a later valid limit can still allow matching."""
        write_inputs(
            ["SHORTLIM1,CUSTSL1,1400,ACTIVE,EXT,2026-04-10"],
            ["SHORTLIM1,CUSTSL1,1400,EXT,2026-04-04"],
            ["2026-04-04 open"],
            ["EXT,true,1"],
            ["CUSTSL1,EXT", "CUSTSL1,EXT,2026-04-01,2000,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["care_type"] == "EXT"
        assert summary["matched_amount_cents"] == 1400


    def test_short_blackout_rows_are_ignored_without_blocking_match(self):
        """Short blackout rows should be ignored instead of blocking an otherwise valid match."""
        write_inputs(
            ["SHORTBLK1,CUSTSB1,1450,ACTIVE,EXT,2026-04-10"],
            ["SHORTBLK1,CUSTSB1,1450,EXT,2026-04-04"],
            ["2026-04-04 open"],
            ["EXT,true,1"],
            ["CUSTSB1,EXT,2026-04-01,2000,ACTIVE"],
            ["EXT,2026-04-01"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["care_type"] == "EXT"
        assert summary["matched_amount_cents"] == 1450


    def test_undated_any_priorities_treat_missing_and_malformed_as_late(self):
        """Undated ANY ranking should put missing and malformed priorities after numeric priorities."""
        write_inputs(
            [
                "UNDPRI1,CUSTUP1,900,ACTIVE,HALF",
                "UNDPRI1,CUSTUP1,900,ACTIVE,FULL",
                "UNDPRI1,CUSTUP1,900,ACTIVE,EXT",
            ],
            ["UNDPRI1,CUSTUP1,900,ANY"],
            ["2026-04-04 closed"],
            ["HALF,true,bad", "FULL,true,4", "EXT,true"],
            [],
            [],
            dated=False,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["care_type"] == "FULL"
        assert summary["matched_amount_cents"] == 900

    def test_any_latest_date_beats_config_priority(self):
        """For dated ANY actions, latest source date should rank before configured type priority."""
        write_inputs(
            [
                "ANYDATE1,CUSTAD1,1750,ACTIVE,FULL,2026-04-08",
                "ANYDATE1,CUSTAD1,1750,ACTIVE,EXT,2026-04-11",
            ],
            ["ANYDATE1,CUSTAD1,1750,ANY,2026-04-04"],
            ["2026-04-04 open"],
            ["FULL,true,1", "EXT,true,9"],
            ["CUSTAD1,EXT,2026-04-01,3000,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["care_type"] == "EXT"
        assert summary["matched_amount_cents"] == 1750
