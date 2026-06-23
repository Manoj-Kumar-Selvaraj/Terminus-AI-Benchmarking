"""Milestone 4 verifier tests for methods, ANY, guest limits, and blackouts."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
PASSES = APP / "data" / "passes.csv"
REFUNDS = APP / "data" / "refunds.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
METHODS = APP / "config" / "methods.csv"
LIMITS = APP / "config" / "guest_limits.csv"
BLACKOUTS = APP / "config" / "blackouts.csv"
REPORT = APP / "out" / "refund_report.csv"
SUMMARY = APP / "out" / "refund_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")
DEFAULT_METHODS = "access_type,enabled,priority\nDAY,true,2\nSEASON,true,1\nVIP,true,3\n"


def build_program():
    """Compile the Go pass refund reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 4 tests."""
    build_program()


def write_inputs(
    pass_rows,
    refund_rows,
    calendar_rows,
    method_rows=None,
    limit_rows=None,
    blackout_rows=None,
    dated=True,
):
    """Replace CSV inputs, calendar, and config files with one verifier scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    if dated:
        PASSES.write_text("pass_id,guest_id,amount_cents,status,access_type,visit_date\n" + "\n".join(pass_rows) + "\n")
        REFUNDS.write_text("pass_id,guest_id,amount_cents,access_type,refund_date\n" + "\n".join(refund_rows) + "\n")
    else:
        PASSES.write_text("pass_id,guest_id,amount_cents,status,access_type\n" + "\n".join(pass_rows) + "\n")
        REFUNDS.write_text("pass_id,guest_id,amount_cents,access_type\n" + "\n".join(refund_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    if method_rows is not None:
        METHODS.write_text("access_type,enabled,priority\n" + "\n".join(method_rows) + "\n")
    else:
        METHODS.write_text(DEFAULT_METHODS)
    limit_body = "" if limit_rows is None else "\n".join(limit_rows) + ("\n" if limit_rows else "")
    LIMITS.write_text("guest_id,access_type,effective_date,max_daily_amount,status\n" + limit_body)
    blackout_body = "" if blackout_rows is None else "\n".join(blackout_rows) + ("\n" if blackout_rows else "")
    BLACKOUTS.write_text("access_type,start_date,end_date,state\n" + blackout_body)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse its CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone4:
    """Methods config, ANY refunds, guest limits, and blackouts interact with prior matching gates."""

    def test_disabled_configured_access_type_rejects_otherwise_valid_refund(self):
        """Disabled methods.csv access types must not match even with valid ids, dates, and aliases."""
        write_inputs(
            ["CFG1001,CUST1001,1200,ACTIVE,SEASON,2026-04-10"],
            ["CFG1001,CUST1001,1200,SEA,2026-04-05"],
            ["2026-04-05 open"],
            ["DAY,true,2", "SEASON,false,1", "VIP,true,3"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["access_type"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1200,
        }

    def test_any_same_date_uses_config_priority_before_pass_order(self):
        """ANY ties on visit date should use configured priority before pass row order."""
        write_inputs(
            [
                "ANY2001,CUST2001,700,ACTIVE,DAY,2026-04-08",
                "ANY2001,CUST2001,700,ACTIVE,VIP,2026-04-08",
                "ANY2001,CUST2001,700,ACTIVE,SEASON,2026-04-08",
            ],
            ["ANY2001,CUST2001,700,ANY,2026-04-04"],
            ["2026-04-04 open"],
            ["DAY,true,5", "SEASON,true,1", "VIP,true,3"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["access_type"] == "SEASON"
        assert summary["matched_count"] == 1

    def test_any_equal_priority_tie_uses_earliest_pass_row(self):
        """ANY ties on date and priority should choose the earliest pass input row."""
        write_inputs(
            [
                "ANY3001,CUST3001,800,ACTIVE,DAY,2026-04-09",
                "ANY3001,CUST3001,800,ACTIVE,SEASON,2026-04-09",
            ],
            ["ANY3001,CUST3001,800,ANY,2026-04-04"],
            ["2026-04-04 open"],
            ["DAY,true,1", "SEASON,true,1", "VIP,true,9"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["access_type"] == "DAY"
        assert summary["matched_amount_cents"] == 800

    def test_any_consumes_selected_row_and_reranks_remaining_candidates(self):
        """ANY matching should consume by row position and rerank remaining candidates."""
        write_inputs(
            [
                "ANY4001,CUST4001,500,ACTIVE,DAY,2026-04-07",
                "ANY4001,CUST4001,500,ACTIVE,SEASON,2026-04-07",
            ],
            [
                "ANY4001,CUST4001,500,ANY,2026-04-04",
                "ANY4001,CUST4001,500,ANY,2026-04-04",
                "ANY4001,CUST4001,500,ANY,2026-04-04",
            ],
            ["2026-04-04 open"],
            ["DAY,true,1", "SEASON,true,2", "VIP,true,3"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["access_type"] for row in rows] == ["DAY", "SEASON", ""]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1000,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_non_any_still_requires_exact_canonical_access_type(self):
        """Config policy must not turn named access-type refunds into wildcard matches."""
        write_inputs(
            ["CFG5001,CUST5001,900,ACTIVE,DAY,2026-04-10"],
            ["CFG5001,CUST5001,900,SEA,2026-04-05"],
            ["2026-04-05 open"],
            ["DAY,true,1", "SEASON,true,2", "VIP,true,3"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["access_type"] == ""
        assert summary["unmatched_amount_cents"] == 900

    def test_missing_and_malformed_methods_do_not_enable_access_type(self):
        """Missing, blank, malformed, and non-true method rows should leave types ineligible."""
        write_inputs(
            [
                "BILLM411,CUSTM411,1100,ACTIVE,DAY,2026-05-12",
                "BILLM412,CUSTM412,1200,ACTIVE,SEASON,2026-05-12",
                "BILLM413,CUSTM413,1300,ACTIVE,VIP,2026-05-12",
            ],
            [
                "BILLM411,CUSTM411,1100,DAY,2026-05-06",
                "BILLM412,CUSTM412,1200,SEA,2026-05-06",
                "BILLM413,CUSTM413,1300,V,2026-05-06",
            ],
            ["2026-05-06 open"],
            [
                "DAY,maybe,2",
                "SEASON",
                ",true,1",
                "VIP,TRUE,3",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "MATCHED"]
        assert [row["access_type"] for row in rows] == ["", "", "VIP"]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1300,
            "unmatched_count": 2,
            "unmatched_amount_cents": 2300,
        }

    def test_methods_alias_normalization_enables_sea_entry(self):
        """Method access_type aliases such as SEA should normalize before enabled checks."""
        write_inputs(
            ["CFG6001,CUST6001,750,ACTIVE,SEASON,2026-04-10"],
            ["CFG6001,CUST6001,750,SEA,2026-04-05"],
            ["2026-04-05 open"],
            ["SEA,true,1", "DAY,true,2"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["access_type"] == "SEASON"
        assert summary["matched_count"] == 1

    def test_any_undated_inputs_rank_by_priority_then_pass_order(self):
        """Without date columns, ANY should rank only by priority then earliest pass row."""
        write_inputs(
            [
                "UND7001,CUST7001,600,ACTIVE,VIP",
                "UND7001,CUST7001,600,ACTIVE,DAY",
                "UND7001,CUST7001,600,ACTIVE,SEASON",
            ],
            ["UND7001,CUST7001,600,ANY"],
            ["2026-04-01 closed"],
            ["DAY,true,3", "SEASON,true,1", "VIP,true,2"],
            dated=False,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["access_type"] == "SEASON"
        assert summary["matched_amount_cents"] == 600

    def test_enabled_method_does_not_bypass_closed_calendar_date(self):
        """An enabled access type must still fail when the refund date is not open."""
        write_inputs(
            ["BILLM431,CUSTM431,1500,ACTIVE,DAY,2026-05-15"],
            ["BILLM431,CUSTM431,1500,DY,2026-05-09"],
            ["2026-05-09 closed"],
            ["DAY,true,1"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["access_type"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1500,
        }

    def test_methods_gate_preserves_latest_visit_date_selection(self):
        """Enabled methods should not weaken latest visit_date selection or consumption."""
        write_inputs(
            [
                "BILLM421,CUSTM421,1400,ACTIVE,DAY,2026-05-08",
                "BILLM421,CUSTM421,1400,ACTIVE,DAY,2026-05-14",
                "BILLM421,CUSTM421,1400,ACTIVE,DAY,2026-05-14",
            ],
            [
                "BILLM421,CUSTM421,1400,DY,2026-05-07",
                "BILLM421,CUSTM421,1400,DY,2026-05-07",
                "BILLM421,CUSTM421,1400,DY,2026-05-07",
                "BILLM421,CUSTM421,1400,DY,2026-05-07",
            ],
            ["2026-05-07 open"],
            ["DAY,true,1"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["access_type"] for row in rows] == ["DAY", "DAY", "DAY", ""]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 4200,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1400,
        }

    def test_latest_effective_limit_caps_daily_refunds_in_refund_order(self):
        """The latest active limit should cap same guest/access/date refunds cumulatively."""
        write_inputs(
            [
                "LIM5001,CUST5001,600,ACTIVE,DAY,2026-06-10",
                "LIM5002,CUST5001,500,ACTIVE,DAY,2026-06-10",
                "LIM5003,CUST5001,400,ACTIVE,DAY,2026-06-10",
            ],
            [
                "LIM5001,CUST5001,600,DY,2026-06-05",
                "LIM5002,CUST5001,500,DY,2026-06-05",
                "LIM5003,CUST5001,400,DY,2026-06-05",
            ],
            ["2026-06-05 open"],
            ["DAY,true,1"],
            [
                "CUST5001,DAY,2026-05-01,900,ACTIVE",
                "CUST5001,DY,2026-06-01,1100,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["access_type"] for row in rows] == ["DAY", "DAY", ""]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1100,
            "unmatched_count": 1,
            "unmatched_amount_cents": 400,
        }

    def test_budget_is_partitioned_by_guest_selected_access_type_and_refund_date(self):
        """Budget consumption should be keyed by guest, selected access type, and refund_date."""
        write_inputs(
            [
                "LIM5101,CUST5101,700,ACTIVE,DAY,2026-06-10",
                "LIM5102,CUST5101,700,ACTIVE,VIP,2026-06-10",
                "LIM5103,CUST5101,700,ACTIVE,DAY,2026-06-11",
                "LIM5104,CUST5102,700,ACTIVE,DAY,2026-06-10",
            ],
            [
                "LIM5101,CUST5101,700,DY,2026-06-05",
                "LIM5102,CUST5101,700,V,2026-06-05",
                "LIM5103,CUST5101,700,DY,2026-06-06",
                "LIM5104,CUST5102,700,DY,2026-06-05",
            ],
            ["2026-06-05 open", "2026-06-06 open"],
            ["DAY,true,1", "VIP,true,2"],
            [
                "CUST5101,DAY,2026-06-01,700,ACTIVE",
                "CUST5101,VIP,2026-06-01,700,ACTIVE",
                "CUST5102,DAY,2026-06-01,700,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "MATCHED"]
        assert [row["access_type"] for row in rows] == ["DAY", "VIP", "DAY", "DAY"]
        assert summary["matched_count"] == 4
        assert summary["matched_amount_cents"] == 2800

    def test_any_refund_uses_selected_candidate_access_type_for_limit(self):
        """ANY refunds should look up budget against the access type of the selected pass."""
        write_inputs(
            [
                "LIM5201,CUST5201,800,ACTIVE,DAY,2026-06-10",
                "LIM5201,CUST5201,800,ACTIVE,VIP,2026-06-10",
            ],
            [
                "LIM5201,CUST5201,800,ANY,2026-06-05",
                "LIM5201,CUST5201,800,ANY,2026-06-05",
            ],
            ["2026-06-05 open"],
            ["DAY,true,1", "VIP,true,2"],
            [
                "CUST5201,DAY,2026-06-01,800,ACTIVE",
                "CUST5201,VIP,2026-06-01,700,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["access_type"] for row in rows] == ["DAY", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_inactive_future_unknown_and_nonnumeric_limits_are_ignored(self):
        """Only active, effective, numeric limits for known access types should enable budget matching."""
        write_inputs(
            [
                "LIM5301,CUST5301,300,ACTIVE,DAY,2026-06-10",
                "LIM5302,CUST5302,300,ACTIVE,DAY,2026-06-10",
                "LIM5303,CUST5303,300,ACTIVE,DAY,2026-06-10",
                "LIM5304,CUST5304,300,ACTIVE,DAY,2026-06-10",
                "LIM5305,CUST5305,300,ACTIVE,DAY,2026-06-10",
            ],
            [
                "LIM5301,CUST5301,300,DY,2026-06-05",
                "LIM5302,CUST5302,300,DY,2026-06-05",
                "LIM5303,CUST5303,300,DY,2026-06-05",
                "LIM5304,CUST5304,300,DY,2026-06-05",
                "LIM5305,CUST5305,300,DY,2026-06-05",
            ],
            ["2026-06-05 open"],
            ["DAY,true,1"],
            [
                "CUST5301,DAY,2026-06-01,300,INACTIVE",
                "CUST5302,DAY,2026-06-06,300,ACTIVE",
                "CUST5303,DAY,2026-06-01,not-number,ACTIVE",
                "CUST5304,BAD,2026-06-01,300,ACTIVE",
                "CUST5305,DY,2026-06-01,300,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert [row["access_type"] for row in rows] == ["", "", "", "", "DAY"]
        assert summary["matched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1200

    def test_budget_rejection_does_not_consume_pass_row_needed_by_later_refund(self):
        """An over-limit refund must not consume a pass row needed by a later eligible refund."""
        write_inputs(
            [
                "LIM5401,CUST5401,900,ACTIVE,DAY,2026-06-10",
                "LIM5401,CUST5401,400,ACTIVE,DAY,2026-06-10",
            ],
            [
                "LIM5401,CUST5401,900,DY,2026-06-05",
                "LIM5401,CUST5401,400,DY,2026-06-05",
            ],
            ["2026-06-05 open"],
            ["DAY,true,1"],
            ["CUST5401,DY,2026-06-01,500,ACTIVE"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert [row["access_type"] for row in rows] == ["", "DAY"]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 400,
            "unmatched_count": 1,
            "unmatched_amount_cents": 900,
        }

    def test_undated_inputs_keep_methods_and_any_behavior_without_limits(self):
        """When refund_date is absent, guest_limits.csv should not gate matching."""
        write_inputs(
            ["LIM5501,CUST5501,1000,ACTIVE,DAY"],
            ["LIM5501,CUST5501,1000,DY"],
            ["2026-06-05 closed"],
            ["DAY,true,1"],
            [],
            dated=False,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["access_type"] == "DAY"
        assert summary["matched_count"] == 1

    def test_named_refund_is_blocked_by_active_blackout_range(self):
        """A matching pass should be ineligible when its access type is blacked out on refund_date."""
        write_inputs(
            ["BLK6001,CUST6001,600,ACTIVE,VIP,2026-07-10"],
            ["BLK6001,CUST6001,600,V,2026-07-05"],
            ["2026-07-05 open"],
            ["VIP,true,1"],
            ["CUST6001,VIP,2026-07-01,600,ACTIVE"],
            ["VIP,2026-07-01,2026-07-06,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["access_type"] == ""
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
                "BLK6101,CUST6101,700,ACTIVE,SEASON,2026-07-10",
                "BLK6101,CUST6101,700,ACTIVE,DAY,2026-07-10",
            ],
            ["BLK6101,CUST6101,700,ANY,2026-07-05"],
            ["2026-07-05 open"],
            ["SEASON,true,1", "DAY,true,2"],
            [
                "CUST6101,SEASON,2026-07-01,700,ACTIVE",
                "CUST6101,DAY,2026-07-01,700,ACTIVE",
            ],
            ["SEA,2026-07-01,2026-07-06,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["access_type"] == "DAY"
        assert summary["matched_count"] == 1

    def test_blackout_filter_happens_before_budget_consumption(self):
        """A blacked-out candidate should not consume pass rows or guest budget."""
        write_inputs(
            [
                "BLK6201,CUST6201,900,ACTIVE,VIP,2026-07-10",
                "BLK6201,CUST6201,400,ACTIVE,VIP,2026-07-10",
            ],
            [
                "BLK6201,CUST6201,900,V,2026-07-05",
                "BLK6201,CUST6201,400,V,2026-07-07",
            ],
            ["2026-07-05 open", "2026-07-07 open"],
            ["VIP,true,1"],
            ["CUST6201,VIP,2026-07-01,500,ACTIVE"],
            ["VIP,2026-07-01,2026-07-06,ACTIVE"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert [row["access_type"] for row in rows] == ["", "VIP"]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 400,
            "unmatched_count": 1,
            "unmatched_amount_cents": 900,
        }

    def test_inactive_malformed_and_out_of_range_blackouts_are_ignored(self):
        """Only active well-formed blackout ranges containing refund_date should block."""
        write_inputs(
            [
                "BLK6301,CUST6301,300,ACTIVE,DAY,2026-07-10",
                "BLK6302,CUST6302,300,ACTIVE,DAY,2026-07-10",
                "BLK6303,CUST6303,300,ACTIVE,DAY,2026-07-10",
                "BLK6304,CUST6304,300,ACTIVE,DAY,2026-07-10",
            ],
            [
                "BLK6301,CUST6301,300,DY,2026-07-05",
                "BLK6302,CUST6302,300,DY,2026-07-05",
                "BLK6303,CUST6303,300,DY,2026-07-05",
                "BLK6304,CUST6304,300,DY,2026-07-05",
            ],
            ["2026-07-05 open"],
            ["DAY,true,1"],
            [
                "CUST6301,DAY,2026-07-01,300,ACTIVE",
                "CUST6302,DAY,2026-07-01,300,ACTIVE",
                "CUST6303,DAY,2026-07-01,300,ACTIVE",
                "CUST6304,DAY,2026-07-01,300,ACTIVE",
            ],
            [
                "DAY,2026-07-01,2026-07-06,INACTIVE",
                "DAY,bad-date,2026-07-06,ACTIVE",
                "DAY,2026-07-06,2026-07-10,ACTIVE",
                "BAD,2026-07-01,2026-07-06,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "MATCHED"]
        assert summary["matched_count"] == 4

    def test_undated_inputs_skip_blackouts_and_limits_but_keep_methods_and_any(self):
        """Without refund_date, blackout and limit gates should be skipped while methods and ANY behavior remains."""
        write_inputs(
            ["BLK6401,CUST6401,500,ACTIVE,VIP"],
            ["BLK6401,CUST6401,500,ANY"],
            ["2026-07-05 closed"],
            ["VIP,true,1"],
            [],
            ["VIP,2026-01-01,2026-12-31,ACTIVE"],
            dated=False,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["access_type"] == "VIP"
        assert summary["matched_amount_cents"] == 500
