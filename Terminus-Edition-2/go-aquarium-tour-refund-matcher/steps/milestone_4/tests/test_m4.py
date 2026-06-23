"""Milestone 4 verifier tests for methods, ANY, guest limits, and blackouts."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
SOURCES = APP / "data" / "tours.csv"
ACTIONS = APP / "data" / "refunds.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
METHODS = APP / "config" / "methods.csv"
LIMITS = APP / "config" / "member_limits.csv"
BLACKOUTS = APP / "config" / "blackouts.csv"
REPORT = APP / "out" / "tour_refund_report.csv"
SUMMARY = APP / "out" / "tour_refund_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")
DEFAULT_METHODS = "tour_type,enabled,priority\nREEF,true,2\nSHARK,true,1\nVIP,true,3\n"


def build_program():
    """Compile the Go tour refund reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 4 tests."""
    build_program()


def write_inputs(
    tour_rows,
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
        CLASSES.write_text("tour_id,guest_id,amount_cents,status,tour_type,tour_date\n" + "\n".join(tour_rows) + "\n")
        CREDITS.write_text("tour_id,guest_id,amount_cents,tour_type,refund_date\n" + "\n".join(refund_rows) + "\n")
    else:
        CLASSES.write_text("tour_id,guest_id,amount_cents,status,tour_type\n" + "\n".join(tour_rows) + "\n")
        CREDITS.write_text("tour_id,guest_id,amount_cents,tour_type\n" + "\n".join(refund_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    if method_rows is not None:
        METHODS.write_text("tour_type,enabled,priority\n" + "\n".join(method_rows) + "\n")
    else:
        METHODS.write_text(DEFAULT_METHODS)
    limit_body = "" if limit_rows is None else "\n".join(limit_rows) + ("\n" if limit_rows else "")
    LIMITS.write_text("guest_id,tour_type,effective_date,max_daily_amount,status\n" + limit_body)
    blackout_body = "" if blackout_rows is None else "\n".join(blackout_rows) + ("\n" if blackout_rows else "")
    BLACKOUTS.write_text("tour_type,start_date,end_date,state\n" + blackout_body)
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

    def test_disabled_configured_tour_type_rejects_otherwise_valid_refund(self):
        """Disabled methods.csv tour types must not match even with valid ids, dates, and aliases."""
        write_inputs(
            ["CFG1001,CUST1001,1200,ACTIVE,SHARK,2026-04-10"],
            ["CFG1001,CUST1001,1200,SH,2026-04-05"],
            ["2026-04-05 open"],
            ["REEF,true,2", "SHARK,false,1", "VIP,true,3"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["tour_type"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1200,
        }

    def test_any_same_date_uses_config_priority_before_tour_order(self):
        """ANY ties on visit date should use configured priority before tour row order."""
        write_inputs(
            [
                "ANY2001,CUST2001,700,ACTIVE,REEF,2026-04-08",
                "ANY2001,CUST2001,700,ACTIVE,VIP,2026-04-08",
                "ANY2001,CUST2001,700,ACTIVE,SHARK,2026-04-08",
            ],
            ["ANY2001,CUST2001,700,ANY,2026-04-04"],
            ["2026-04-04 open"],
            ["REEF,true,5", "SHARK,true,1", "VIP,true,3"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["tour_type"] == "SHARK"
        assert summary["matched_count"] == 1

    def test_any_equal_priority_tie_uses_earliest_tour_row(self):
        """ANY ties on date and priority should choose the earliest tour input row."""
        write_inputs(
            [
                "ANY3001,CUST3001,800,ACTIVE,REEF,2026-04-09",
                "ANY3001,CUST3001,800,ACTIVE,SHARK,2026-04-09",
            ],
            ["ANY3001,CUST3001,800,ANY,2026-04-04"],
            ["2026-04-04 open"],
            ["REEF,true,1", "SHARK,true,1", "VIP,true,9"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["tour_type"] == "REEF"
        assert summary["matched_amount_cents"] == 800

    def test_any_consumes_selected_row_and_reranks_remaining_candidates(self):
        """ANY matching should consume by row position and rerank remaining candidates."""
        write_inputs(
            [
                "ANY4001,CUST4001,500,ACTIVE,REEF,2026-04-07",
                "ANY4001,CUST4001,500,ACTIVE,SHARK,2026-04-07",
            ],
            [
                "ANY4001,CUST4001,500,ANY,2026-04-04",
                "ANY4001,CUST4001,500,ANY,2026-04-04",
                "ANY4001,CUST4001,500,ANY,2026-04-04",
            ],
            ["2026-04-04 open"],
            ["REEF,true,1", "SHARK,true,2", "VIP,true,3"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["tour_type"] for row in rows] == ["REEF", "SHARK", ""]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1000,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_non_any_still_requires_exact_canonical_tour_type(self):
        """Config policy must not turn named configured-type refunds into wildcard matches."""
        write_inputs(
            ["CFG5001,CUST5001,900,ACTIVE,REEF,2026-04-10"],
            ["CFG5001,CUST5001,900,SH,2026-04-05"],
            ["2026-04-05 open"],
            ["REEF,true,1", "SHARK,true,2", "VIP,true,3"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["tour_type"] == ""
        assert summary["unmatched_amount_cents"] == 900

    def test_missing_and_malformed_methods_do_not_enable_tour_type(self):
        """Missing, blank, malformed, and non-true method rows should leave types ineligible."""
        write_inputs(
            [
                "BILLM411,CUSTM411,1100,ACTIVE,REEF,2026-05-12",
                "BILLM412,CUSTM412,1200,ACTIVE,SHARK,2026-05-12",
                "BILLM413,CUSTM413,1300,ACTIVE,VIP,2026-05-12",
            ],
            [
                "BILLM411,CUSTM411,1100,REEF,2026-05-06",
                "BILLM412,CUSTM412,1200,SH,2026-05-06",
                "BILLM413,CUSTM413,1300,VP,2026-05-06",
            ],
            ["2026-05-06 open"],
            [
                "REEF,maybe,2",
                "SHARK",
                ",true,1",
                "VIP,TRUE,3",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "MATCHED"]
        assert [row["tour_type"] for row in rows] == ["", "", "VIP"]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1300,
            "unmatched_count": 2,
            "unmatched_amount_cents": 2300,
        }

    def test_methods_alias_normalization_enables_sh_entry(self):
        """Method tour_type aliases such as SH should normalize before enabled checks."""
        write_inputs(
            ["CFG6001,CUST6001,750,ACTIVE,SHARK,2026-04-10"],
            ["CFG6001,CUST6001,750,SH,2026-04-05"],
            ["2026-04-05 open"],
            ["SH,true,1", "REEF,true,2"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["tour_type"] == "SHARK"
        assert summary["matched_count"] == 1

    def test_any_undated_inputs_rank_by_priority_then_tour_order(self):
        """Without date columns, ANY should rank only by priority then earliest tour row."""
        write_inputs(
            [
                "UND7001,CUST7001,600,ACTIVE,VIP",
                "UND7001,CUST7001,600,ACTIVE,REEF",
                "UND7001,CUST7001,600,ACTIVE,SHARK",
            ],
            ["UND7001,CUST7001,600,ANY"],
            ["2026-04-01 closed"],
            ["REEF,true,3", "SHARK,true,1", "VIP,true,2"],
            dated=False,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["tour_type"] == "SHARK"
        assert summary["matched_amount_cents"] == 600

    def test_enabled_method_does_not_bypass_closed_calendar_date(self):
        """An enabled tour type must still fail when the refund date is not open."""
        write_inputs(
            ["BILLM431,CUSTM431,1500,ACTIVE,REEF,2026-05-15"],
            ["BILLM431,CUSTM431,1500,RF,2026-05-09"],
            ["2026-05-09 closed"],
            ["REEF,true,1"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["tour_type"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1500,
        }

    def test_methods_gate_preserves_latest_tour_date_selection(self):
        """Enabled methods should not weaken latest tour_date selection or consumption."""
        write_inputs(
            [
                "BILLM421,CUSTM421,1400,ACTIVE,REEF,2026-05-08",
                "BILLM421,CUSTM421,1400,ACTIVE,REEF,2026-05-14",
                "BILLM421,CUSTM421,1400,ACTIVE,REEF,2026-05-14",
            ],
            [
                "BILLM421,CUSTM421,1400,RF,2026-05-07",
                "BILLM421,CUSTM421,1400,RF,2026-05-07",
                "BILLM421,CUSTM421,1400,RF,2026-05-07",
                "BILLM421,CUSTM421,1400,RF,2026-05-07",
            ],
            ["2026-05-07 open"],
            ["REEF,true,1"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["tour_type"] for row in rows] == ["REEF", "REEF", "REEF", ""]
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
                "LIM5001,CUST5001,600,ACTIVE,REEF,2026-06-10",
                "LIM5002,CUST5001,500,ACTIVE,REEF,2026-06-10",
                "LIM5003,CUST5001,400,ACTIVE,REEF,2026-06-10",
            ],
            [
                "LIM5001,CUST5001,600,RF,2026-06-05",
                "LIM5002,CUST5001,500,RF,2026-06-05",
                "LIM5003,CUST5001,400,RF,2026-06-05",
            ],
            ["2026-06-05 open"],
            ["REEF,true,1"],
            [
                "CUST5001,REEF,2026-05-01,900,ACTIVE",
                "CUST5001,RF,2026-06-01,1100,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["tour_type"] for row in rows] == ["REEF", "REEF", ""]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1100,
            "unmatched_count": 1,
            "unmatched_amount_cents": 400,
        }

    def test_budget_is_partitioned_by_guest_selected_tour_type_and_refund_date(self):
        """Budget consumption should be keyed by guest, selected tour type, and refund_date."""
        write_inputs(
            [
                "LIM5101,CUST5101,700,ACTIVE,REEF,2026-06-10",
                "LIM5102,CUST5101,700,ACTIVE,VIP,2026-06-10",
                "LIM5103,CUST5101,700,ACTIVE,REEF,2026-06-11",
                "LIM5104,CUST5102,700,ACTIVE,REEF,2026-06-10",
            ],
            [
                "LIM5101,CUST5101,700,RF,2026-06-05",
                "LIM5102,CUST5101,700,VP,2026-06-05",
                "LIM5103,CUST5101,700,RF,2026-06-06",
                "LIM5104,CUST5102,700,RF,2026-06-05",
            ],
            ["2026-06-05 open", "2026-06-06 open"],
            ["REEF,true,1", "VIP,true,2"],
            [
                "CUST5101,REEF,2026-06-01,700,ACTIVE",
                "CUST5101,VIP,2026-06-01,700,ACTIVE",
                "CUST5102,REEF,2026-06-01,700,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "MATCHED"]
        assert [row["tour_type"] for row in rows] == ["REEF", "VIP", "REEF", "REEF"]
        assert summary["matched_count"] == 4
        assert summary["matched_amount_cents"] == 2800

    def test_any_refund_uses_selected_candidate_tour_type_for_limit(self):
        """ANY refunds should look up budget against the tour type of the selected tour."""
        write_inputs(
            [
                "LIM5201,CUST5201,800,ACTIVE,REEF,2026-06-10",
                "LIM5201,CUST5201,800,ACTIVE,VIP,2026-06-10",
            ],
            [
                "LIM5201,CUST5201,800,ANY,2026-06-05",
                "LIM5201,CUST5201,800,ANY,2026-06-05",
            ],
            ["2026-06-05 open"],
            ["REEF,true,1", "VIP,true,2"],
            [
                "CUST5201,REEF,2026-06-01,800,ACTIVE",
                "CUST5201,VIP,2026-06-01,700,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["tour_type"] for row in rows] == ["REEF", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_inactive_future_unknown_and_nonnumeric_limits_are_ignored(self):
        """Only active, effective, numeric limits for known tour types should enable budget matching."""
        write_inputs(
            [
                "LIM5301,CUST5301,300,ACTIVE,REEF,2026-06-10",
                "LIM5302,CUST5302,300,ACTIVE,REEF,2026-06-10",
                "LIM5303,CUST5303,300,ACTIVE,REEF,2026-06-10",
                "LIM5304,CUST5304,300,ACTIVE,REEF,2026-06-10",
                "LIM5305,CUST5305,300,ACTIVE,REEF,2026-06-10",
            ],
            [
                "LIM5301,CUST5301,300,RF,2026-06-05",
                "LIM5302,CUST5302,300,RF,2026-06-05",
                "LIM5303,CUST5303,300,RF,2026-06-05",
                "LIM5304,CUST5304,300,RF,2026-06-05",
                "LIM5305,CUST5305,300,RF,2026-06-05",
            ],
            ["2026-06-05 open"],
            ["REEF,true,1"],
            [
                "CUST5301,REEF,2026-06-01,300,INACTIVE",
                "CUST5302,REEF,2026-06-06,300,ACTIVE",
                "CUST5303,REEF,2026-06-01,not-number,ACTIVE",
                "CUST5304,BAD,2026-06-01,300,ACTIVE",
                "CUST5305,RF,2026-06-01,300,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert [row["tour_type"] for row in rows] == ["", "", "", "", "REEF"]
        assert summary["matched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1200

    def test_budget_rejection_does_not_consume_tour_row_needed_by_later_refund(self):
        """An over-limit refund must not consume a tour row needed by a later eligible refund."""
        write_inputs(
            [
                "LIM5401,CUST5401,900,ACTIVE,REEF,2026-06-10",
                "LIM5401,CUST5401,400,ACTIVE,REEF,2026-06-10",
            ],
            [
                "LIM5401,CUST5401,900,RF,2026-06-05",
                "LIM5401,CUST5401,400,RF,2026-06-05",
            ],
            ["2026-06-05 open"],
            ["REEF,true,1"],
            ["CUST5401,RF,2026-06-01,500,ACTIVE"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert [row["tour_type"] for row in rows] == ["", "REEF"]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 400,
            "unmatched_count": 1,
            "unmatched_amount_cents": 900,
        }

    def test_undated_inputs_keep_methods_and_any_behavior_without_limits(self):
        """When refund_date is absent, member_limits.csv should not gate matching."""
        write_inputs(
            ["LIM5501,CUST5501,1000,ACTIVE,REEF"],
            ["LIM5501,CUST5501,1000,RF"],
            ["2026-06-05 closed"],
            ["REEF,true,1"],
            [],
            dated=False,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["tour_type"] == "REEF"
        assert summary["matched_count"] == 1

    def test_named_refund_is_blocked_by_active_blackout_range(self):
        """A matching tour should be ineligible when its tour type is blacked out on refund_date."""
        write_inputs(
            ["BLK6001,CUST6001,600,ACTIVE,VIP,2026-07-10"],
            ["BLK6001,CUST6001,600,VP,2026-07-05"],
            ["2026-07-05 open"],
            ["VIP,true,1"],
            ["CUST6001,VIP,2026-07-01,600,ACTIVE"],
            ["VIP,2026-07-01,2026-07-06,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["tour_type"] == ""
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
                "BLK6101,CUST6101,700,ACTIVE,SHARK,2026-07-10",
                "BLK6101,CUST6101,700,ACTIVE,REEF,2026-07-10",
            ],
            ["BLK6101,CUST6101,700,ANY,2026-07-05"],
            ["2026-07-05 open"],
            ["SHARK,true,1", "REEF,true,2"],
            [
                "CUST6101,SHARK,2026-07-01,700,ACTIVE",
                "CUST6101,REEF,2026-07-01,700,ACTIVE",
            ],
            ["SH,2026-07-01,2026-07-06,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["tour_type"] == "REEF"
        assert summary["matched_count"] == 1

    def test_blackout_filter_happens_before_budget_consumption(self):
        """A blacked-out candidate should not consume tour rows or guest budget."""
        write_inputs(
            [
                "BLK6201,CUST6201,900,ACTIVE,VIP,2026-07-10",
                "BLK6201,CUST6201,400,ACTIVE,VIP,2026-07-10",
            ],
            [
                "BLK6201,CUST6201,900,VP,2026-07-05",
                "BLK6201,CUST6201,400,VP,2026-07-07",
            ],
            ["2026-07-05 open", "2026-07-07 open"],
            ["VIP,true,1"],
            ["CUST6201,VIP,2026-07-01,500,ACTIVE"],
            ["VIP,2026-07-01,2026-07-06,ACTIVE"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert [row["tour_type"] for row in rows] == ["", "VIP"]
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
                "BLK6301,CUST6301,300,ACTIVE,REEF,2026-07-10",
                "BLK6302,CUST6302,300,ACTIVE,REEF,2026-07-10",
                "BLK6303,CUST6303,300,ACTIVE,REEF,2026-07-10",
                "BLK6304,CUST6304,300,ACTIVE,REEF,2026-07-10",
            ],
            [
                "BLK6301,CUST6301,300,RF,2026-07-05",
                "BLK6302,CUST6302,300,RF,2026-07-05",
                "BLK6303,CUST6303,300,RF,2026-07-05",
                "BLK6304,CUST6304,300,RF,2026-07-05",
            ],
            ["2026-07-05 open"],
            ["REEF,true,1"],
            [
                "CUST6301,REEF,2026-07-01,300,ACTIVE",
                "CUST6302,REEF,2026-07-01,300,ACTIVE",
                "CUST6303,REEF,2026-07-01,300,ACTIVE",
                "CUST6304,REEF,2026-07-01,300,ACTIVE",
            ],
            [
                "REEF,2026-07-01,2026-07-06,INACTIVE",
                "REEF,bad-date,2026-07-06,ACTIVE",
                "REEF,2026-07-06,2026-07-10,ACTIVE",
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
        assert rows[0]["tour_type"] == "VIP"
        assert summary["matched_amount_cents"] == 500

    def test_malformed_policy_rows_are_ignored_without_blocking_valid_rows(self):
        """Malformed method, limit, and blackout rows should be skipped while valid policy rows still allow a match."""
        write_inputs(
            ["POLICY1,CUSTPOL1,1600,ACTIVE,VIP,2026-04-10"],
            ["POLICY1,CUSTPOL1,1600,VIP,2026-04-04"],
            ["2026-04-04 open"],
            ["SHORTMETHOD", ",true,1", "VIP,true,1"],
            [
                ", VIP,2026-04-01,9999,ACTIVE",
                "CUSTPOL1,VIP",
                "CUSTPOL1,VIP,not-a-date,9999,ACTIVE",
                "CUSTPOL1,VIP,2026-04-01,2000,ACTIVE",
            ],
            [
                ",2026-04-01,2026-04-09,ACTIVE",
                "VIP,2026-04-01",
                "VIP,not-a-date,2026-04-09,ACTIVE",
                "VIP,2026-04-01,also-bad,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["tour_type"] == "VIP"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 1600

    def test_malformed_and_missing_priorities_rank_after_numeric_priority(self):
        """Malformed or missing method priorities should rank after configured numeric priorities."""
        write_inputs(
            [
                "PRIORITY1,CUSTPRI1,1800,ACTIVE,REEF,2026-04-10",
                "PRIORITY1,CUSTPRI1,1800,ACTIVE,SHARK,2026-04-10",
                "PRIORITY1,CUSTPRI1,1800,ACTIVE,VIP,2026-04-10",
            ],
            ["PRIORITY1,CUSTPRI1,1800,ANY,2026-04-04"],
            ["2026-04-04 open"],
            ["REEF,true,notnum", "SHARK,true,2", "VIP,true"],
            ["CUSTPRI1,SHARK,2026-04-01,3000,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["tour_type"] == "SHARK"
        assert summary["matched_amount_cents"] == 1800

    def test_equal_effective_limit_dates_prefer_earliest_limit_row(self):
        """When limit effective dates tie, the earliest limit row should decide the daily cap."""
        write_inputs(
            ["LIMITTIE1,CUSTLIM1,1500,ACTIVE,REEF,2026-04-10"],
            ["LIMITTIE1,CUSTLIM1,1500,REEF,2026-04-04"],
            ["2026-04-04 open"],
            ["REEF,true,1"],
            [
                "CUSTLIM1,REEF,2026-04-01,1000,ACTIVE",
                "CUSTLIM1,REEF,2026-04-01,2000,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["tour_type"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 1500

    def test_malformed_method_rows_alone_do_not_enable_matching(self):
        """Malformed methods.csv rows must not make an otherwise valid type eligible."""
        write_inputs(
            ["METHBAD1,CUSTMET1,1300,ACTIVE,VIP,2026-04-10"],
            ["METHBAD1,CUSTMET1,1300,VIP,2026-04-04"],
            ["2026-04-04 open"],
            ["SHORTMETHOD", ",true,1", "VIP,,1"],
            ["CUSTMET1,VIP,2026-04-01,3000,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["tour_type"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 1300

    def test_short_limit_rows_are_ignored_without_blocking_valid_limit(self):
        """Short limit rows should be ignored while a later valid limit can still allow matching."""
        write_inputs(
            ["SHORTLIM1,CUSTSL1,1400,ACTIVE,VIP,2026-04-10"],
            ["SHORTLIM1,CUSTSL1,1400,VIP,2026-04-04"],
            ["2026-04-04 open"],
            ["VIP,true,1"],
            ["CUSTSL1,VIP", "CUSTSL1,VIP,2026-04-01,2000,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["tour_type"] == "VIP"
        assert summary["matched_amount_cents"] == 1400


    def test_short_blackout_rows_are_ignored_without_blocking_match(self):
        """Short blackout rows should be ignored instead of blocking an otherwise valid match."""
        write_inputs(
            ["SHORTBLK1,CUSTSB1,1450,ACTIVE,VIP,2026-04-10"],
            ["SHORTBLK1,CUSTSB1,1450,VIP,2026-04-04"],
            ["2026-04-04 open"],
            ["VIP,true,1"],
            ["CUSTSB1,VIP,2026-04-01,2000,ACTIVE"],
            ["VIP,2026-04-01"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["tour_type"] == "VIP"
        assert summary["matched_amount_cents"] == 1450


    def test_undated_any_priorities_treat_missing_and_malformed_as_late(self):
        """Undated ANY ranking should put missing and malformed priorities after numeric priorities."""
        write_inputs(
            [
                "UNDPRI1,CUSTUP1,900,ACTIVE,REEF",
                "UNDPRI1,CUSTUP1,900,ACTIVE,SHARK",
                "UNDPRI1,CUSTUP1,900,ACTIVE,VIP",
            ],
            ["UNDPRI1,CUSTUP1,900,ANY"],
            ["2026-04-04 closed"],
            ["REEF,true,bad", "SHARK,true,4", "VIP,true"],
            [],
            [],
            dated=False,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["tour_type"] == "SHARK"
        assert summary["matched_amount_cents"] == 900

    def test_any_latest_date_beats_config_priority(self):
        """For dated ANY actions, latest source date should rank before configured type priority."""
        write_inputs(
            [
                "ANYDATE1,CUSTAD1,1750,ACTIVE,SHARK,2026-04-08",
                "ANYDATE1,CUSTAD1,1750,ACTIVE,VIP,2026-04-11",
            ],
            ["ANYDATE1,CUSTAD1,1750,ANY,2026-04-04"],
            ["2026-04-04 open"],
            ["SHARK,true,1", "VIP,true,9"],
            ["CUSTAD1,VIP,2026-04-01,3000,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["tour_type"] == "VIP"
        assert summary["matched_amount_cents"] == 1750
