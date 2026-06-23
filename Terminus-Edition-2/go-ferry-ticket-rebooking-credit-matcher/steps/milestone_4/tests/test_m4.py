"""Milestone 4 verifier tests for methods, ANY, rider limits, and blackouts."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
SOURCES = APP / "data" / "tickets.csv"
CREDITS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
METHODS = APP / "config" / "methods.csv"
LIMITS = APP / "config" / "rider_limits.csv"
BLACKOUTS = APP / "config" / "blackouts.csv"
REPORT = APP / "out" / "ticket_credit_report.csv"
SUMMARY = APP / "out" / "ticket_credit_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")
DEFAULT_METHODS = "fare_type,enabled,priority\nECON,true,2\nBIKE,true,1\nCABIN,true,3\n"


def build_program():
    """Compile the Go ticket credit reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 4 tests."""
    build_program()


def write_inputs(
    ticket_rows,
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
        CLASSES.write_text("ticket_id,rider_id,amount_cents,status,fare_type,travel_date\n" + "\n".join(ticket_rows) + "\n")
        CREDITS.write_text("ticket_id,rider_id,amount_cents,fare_type,credit_date\n" + "\n".join(credit_rows) + "\n")
    else:
        CLASSES.write_text("ticket_id,rider_id,amount_cents,status,fare_type\n" + "\n".join(ticket_rows) + "\n")
        CREDITS.write_text("ticket_id,rider_id,amount_cents,fare_type\n" + "\n".join(credit_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    if method_rows is not None:
        METHODS.write_text("fare_type,enabled,priority\n" + "\n".join(method_rows) + "\n")
    else:
        METHODS.write_text(DEFAULT_METHODS)
    limit_body = "" if limit_rows is None else "\n".join(limit_rows) + ("\n" if limit_rows else "")
    LIMITS.write_text("rider_id,fare_type,effective_date,max_daily_amount,status\n" + limit_body)
    blackout_body = "" if blackout_rows is None else "\n".join(blackout_rows) + ("\n" if blackout_rows else "")
    BLACKOUTS.write_text("fare_type,start_date,end_date,state\n" + blackout_body)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse its CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone4:
    """Methods config, ANY credits, rider limits, and blackouts interact with prior matching gates."""

    def test_disabled_configured_fare_type_rejects_otherwise_valid_credit(self):
        """Disabled methods.csv fare types must not match even with valid ids, dates, and aliases."""
        write_inputs(
            ["CFG1001,CUST1001,1200,ACTIVE,BIKE,2026-04-10"],
            ["CFG1001,CUST1001,1200,BK,2026-04-05"],
            ["2026-04-05 open"],
            ["ECON,true,2", "BIKE,false,1", "CABIN,true,3"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["fare_type"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1200,
        }

    def test_any_same_date_uses_config_priority_before_ticket_order(self):
        """ANY ties on visit date should use configured priority before ticket row order."""
        write_inputs(
            [
                "ANY2001,CUST2001,700,ACTIVE,ECON,2026-04-08",
                "ANY2001,CUST2001,700,ACTIVE,CABIN,2026-04-08",
                "ANY2001,CUST2001,700,ACTIVE,BIKE,2026-04-08",
            ],
            ["ANY2001,CUST2001,700,ANY,2026-04-04"],
            ["2026-04-04 open"],
            ["ECON,true,5", "BIKE,true,1", "CABIN,true,3"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["fare_type"] == "BIKE"
        assert summary["matched_count"] == 1

    def test_any_equal_priority_tie_uses_earliest_ticket_row(self):
        """ANY ties on date and priority should choose the earliest ticket input row."""
        write_inputs(
            [
                "ANY3001,CUST3001,800,ACTIVE,ECON,2026-04-09",
                "ANY3001,CUST3001,800,ACTIVE,BIKE,2026-04-09",
            ],
            ["ANY3001,CUST3001,800,ANY,2026-04-04"],
            ["2026-04-04 open"],
            ["ECON,true,1", "BIKE,true,1", "CABIN,true,9"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["fare_type"] == "ECON"
        assert summary["matched_amount_cents"] == 800

    def test_any_consumes_selected_row_and_reranks_remaining_candidates(self):
        """ANY matching should consume by row position and rerank remaining candidates."""
        write_inputs(
            [
                "ANY4001,CUST4001,500,ACTIVE,ECON,2026-04-07",
                "ANY4001,CUST4001,500,ACTIVE,BIKE,2026-04-07",
            ],
            [
                "ANY4001,CUST4001,500,ANY,2026-04-04",
                "ANY4001,CUST4001,500,ANY,2026-04-04",
                "ANY4001,CUST4001,500,ANY,2026-04-04",
            ],
            ["2026-04-04 open"],
            ["ECON,true,1", "BIKE,true,2", "CABIN,true,3"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["fare_type"] for row in rows] == ["ECON", "BIKE", ""]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1000,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_non_any_still_requires_exact_canonical_fare_type(self):
        """Config policy must not turn named class-type credits into wildcard matches."""
        write_inputs(
            ["CFG5001,CUST5001,900,ACTIVE,ECON,2026-04-10"],
            ["CFG5001,CUST5001,900,BK,2026-04-05"],
            ["2026-04-05 open"],
            ["ECON,true,1", "BIKE,true,2", "CABIN,true,3"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["fare_type"] == ""
        assert summary["unmatched_amount_cents"] == 900

    def test_missing_and_malformed_methods_do_not_enable_fare_type(self):
        """Missing, blank, malformed, and non-true method rows should leave types ineligible."""
        write_inputs(
            [
                "BILLM411,CUSTM411,1100,ACTIVE,ECON,2026-05-12",
                "BILLM412,CUSTM412,1200,ACTIVE,BIKE,2026-05-12",
                "BILLM413,CUSTM413,1300,ACTIVE,CABIN,2026-05-12",
            ],
            [
                "BILLM411,CUSTM411,1100,ECON,2026-05-06",
                "BILLM412,CUSTM412,1200,BK,2026-05-06",
                "BILLM413,CUSTM413,1300,CB,2026-05-06",
            ],
            ["2026-05-06 open"],
            [
                "ECON,maybe,2",
                "BIKE",
                ",true,1",
                "CABIN,TRUE,3",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "MATCHED"]
        assert [row["fare_type"] for row in rows] == ["", "", "CABIN"]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1300,
            "unmatched_count": 2,
            "unmatched_amount_cents": 2300,
        }

    def test_methods_alias_normalization_enables_bk_entry(self):
        """Method fare_type aliases such as BK should normalize before enabled checks."""
        write_inputs(
            ["CFG6001,CUST6001,750,ACTIVE,BIKE,2026-04-10"],
            ["CFG6001,CUST6001,750,BK,2026-04-05"],
            ["2026-04-05 open"],
            ["BK,true,1", "ECON,true,2"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["fare_type"] == "BIKE"
        assert summary["matched_count"] == 1

    def test_any_undated_inputs_rank_by_priority_then_ticket_order(self):
        """Without date columns, ANY should rank only by priority then earliest ticket row."""
        write_inputs(
            [
                "UND7001,CUST7001,600,ACTIVE,CABIN",
                "UND7001,CUST7001,600,ACTIVE,ECON",
                "UND7001,CUST7001,600,ACTIVE,BIKE",
            ],
            ["UND7001,CUST7001,600,ANY"],
            ["2026-04-01 closed"],
            ["ECON,true,3", "BIKE,true,1", "CABIN,true,2"],
            dated=False,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["fare_type"] == "BIKE"
        assert summary["matched_amount_cents"] == 600

    def test_enabled_method_does_not_bypass_closed_calendar_date(self):
        """An enabled fare type must still fail when the credit date is not open."""
        write_inputs(
            ["BILLM431,CUSTM431,1500,ACTIVE,ECON,2026-05-15"],
            ["BILLM431,CUSTM431,1500,EC,2026-05-09"],
            ["2026-05-09 closed"],
            ["ECON,true,1"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["fare_type"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1500,
        }

    def test_methods_gate_preserves_latest_travel_date_selection(self):
        """Enabled methods should not weaken latest travel_date selection or consumption."""
        write_inputs(
            [
                "BILLM421,CUSTM421,1400,ACTIVE,ECON,2026-05-08",
                "BILLM421,CUSTM421,1400,ACTIVE,ECON,2026-05-14",
                "BILLM421,CUSTM421,1400,ACTIVE,ECON,2026-05-14",
            ],
            [
                "BILLM421,CUSTM421,1400,EC,2026-05-07",
                "BILLM421,CUSTM421,1400,EC,2026-05-07",
                "BILLM421,CUSTM421,1400,EC,2026-05-07",
                "BILLM421,CUSTM421,1400,EC,2026-05-07",
            ],
            ["2026-05-07 open"],
            ["ECON,true,1"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["fare_type"] for row in rows] == ["ECON", "ECON", "ECON", ""]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 4200,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1400,
        }

    def test_latest_effective_limit_caps_daily_credits_in_credit_order(self):
        """The latest active limit should cap same rider/access/date credits cumulatively."""
        write_inputs(
            [
                "LIM5001,CUST5001,600,ACTIVE,ECON,2026-06-10",
                "LIM5002,CUST5001,500,ACTIVE,ECON,2026-06-10",
                "LIM5003,CUST5001,400,ACTIVE,ECON,2026-06-10",
            ],
            [
                "LIM5001,CUST5001,600,EC,2026-06-05",
                "LIM5002,CUST5001,500,EC,2026-06-05",
                "LIM5003,CUST5001,400,EC,2026-06-05",
            ],
            ["2026-06-05 open"],
            ["ECON,true,1"],
            [
                "CUST5001,ECON,2026-05-01,900,ACTIVE",
                "CUST5001,EC,2026-06-01,1100,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["fare_type"] for row in rows] == ["ECON", "ECON", ""]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1100,
            "unmatched_count": 1,
            "unmatched_amount_cents": 400,
        }

    def test_budget_is_partitioned_by_rider_selected_fare_type_and_credit_date(self):
        """Budget consumption should be keyed by rider, selected fare type, and credit_date."""
        write_inputs(
            [
                "LIM5101,CUST5101,700,ACTIVE,ECON,2026-06-10",
                "LIM5102,CUST5101,700,ACTIVE,CABIN,2026-06-10",
                "LIM5103,CUST5101,700,ACTIVE,ECON,2026-06-11",
                "LIM5104,CUST5102,700,ACTIVE,ECON,2026-06-10",
            ],
            [
                "LIM5101,CUST5101,700,EC,2026-06-05",
                "LIM5102,CUST5101,700,CB,2026-06-05",
                "LIM5103,CUST5101,700,EC,2026-06-06",
                "LIM5104,CUST5102,700,EC,2026-06-05",
            ],
            ["2026-06-05 open", "2026-06-06 open"],
            ["ECON,true,1", "CABIN,true,2"],
            [
                "CUST5101,ECON,2026-06-01,700,ACTIVE",
                "CUST5101,CABIN,2026-06-01,700,ACTIVE",
                "CUST5102,ECON,2026-06-01,700,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "MATCHED"]
        assert [row["fare_type"] for row in rows] == ["ECON", "CABIN", "ECON", "ECON"]
        assert summary["matched_count"] == 4
        assert summary["matched_amount_cents"] == 2800

    def test_any_credit_uses_selected_candidate_fare_type_for_limit(self):
        """ANY credits should look up budget against the fare type of the selected ticket."""
        write_inputs(
            [
                "LIM5201,CUST5201,800,ACTIVE,ECON,2026-06-10",
                "LIM5201,CUST5201,800,ACTIVE,CABIN,2026-06-10",
            ],
            [
                "LIM5201,CUST5201,800,ANY,2026-06-05",
                "LIM5201,CUST5201,800,ANY,2026-06-05",
            ],
            ["2026-06-05 open"],
            ["ECON,true,1", "CABIN,true,2"],
            [
                "CUST5201,ECON,2026-06-01,800,ACTIVE",
                "CUST5201,CABIN,2026-06-01,700,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["fare_type"] for row in rows] == ["ECON", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_inactive_future_unknown_and_nonnumeric_limits_are_ignored(self):
        """Only active, effective, numeric limits for known fare types should enable budget matching."""
        write_inputs(
            [
                "LIM5301,CUST5301,300,ACTIVE,ECON,2026-06-10",
                "LIM5302,CUST5302,300,ACTIVE,ECON,2026-06-10",
                "LIM5303,CUST5303,300,ACTIVE,ECON,2026-06-10",
                "LIM5304,CUST5304,300,ACTIVE,ECON,2026-06-10",
                "LIM5305,CUST5305,300,ACTIVE,ECON,2026-06-10",
            ],
            [
                "LIM5301,CUST5301,300,EC,2026-06-05",
                "LIM5302,CUST5302,300,EC,2026-06-05",
                "LIM5303,CUST5303,300,EC,2026-06-05",
                "LIM5304,CUST5304,300,EC,2026-06-05",
                "LIM5305,CUST5305,300,EC,2026-06-05",
            ],
            ["2026-06-05 open"],
            ["ECON,true,1"],
            [
                "CUST5301,ECON,2026-06-01,300,INACTIVE",
                "CUST5302,ECON,2026-06-06,300,ACTIVE",
                "CUST5303,ECON,2026-06-01,not-number,ACTIVE",
                "CUST5304,BAD,2026-06-01,300,ACTIVE",
                "CUST5305,EC,2026-06-01,300,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert [row["fare_type"] for row in rows] == ["", "", "", "", "ECON"]
        assert summary["matched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1200

    def test_budget_rejection_does_not_consume_ticket_row_needed_by_later_credit(self):
        """An over-limit credit must not consume a ticket row needed by a later eligible credit."""
        write_inputs(
            [
                "LIM5401,CUST5401,900,ACTIVE,ECON,2026-06-10",
                "LIM5401,CUST5401,400,ACTIVE,ECON,2026-06-10",
            ],
            [
                "LIM5401,CUST5401,900,EC,2026-06-05",
                "LIM5401,CUST5401,400,EC,2026-06-05",
            ],
            ["2026-06-05 open"],
            ["ECON,true,1"],
            ["CUST5401,EC,2026-06-01,500,ACTIVE"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert [row["fare_type"] for row in rows] == ["", "ECON"]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 400,
            "unmatched_count": 1,
            "unmatched_amount_cents": 900,
        }

    def test_undated_inputs_keep_methods_and_any_behavior_without_limits(self):
        """When credit_date is absent, rider_limits.csv should not gate matching."""
        write_inputs(
            ["LIM5501,CUST5501,1000,ACTIVE,ECON"],
            ["LIM5501,CUST5501,1000,EC"],
            ["2026-06-05 closed"],
            ["ECON,true,1"],
            [],
            dated=False,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["fare_type"] == "ECON"
        assert summary["matched_count"] == 1

    def test_named_credit_is_blocked_by_active_blackout_range(self):
        """A matching ticket should be ineligible when its fare type is blacked out on credit_date."""
        write_inputs(
            ["BLK6001,CUST6001,600,ACTIVE,CABIN,2026-07-10"],
            ["BLK6001,CUST6001,600,CB,2026-07-05"],
            ["2026-07-05 open"],
            ["CABIN,true,1"],
            ["CUST6001,CABIN,2026-07-01,600,ACTIVE"],
            ["CABIN,2026-07-01,2026-07-06,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["fare_type"] == ""
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
                "BLK6101,CUST6101,700,ACTIVE,BIKE,2026-07-10",
                "BLK6101,CUST6101,700,ACTIVE,ECON,2026-07-10",
            ],
            ["BLK6101,CUST6101,700,ANY,2026-07-05"],
            ["2026-07-05 open"],
            ["BIKE,true,1", "ECON,true,2"],
            [
                "CUST6101,BIKE,2026-07-01,700,ACTIVE",
                "CUST6101,ECON,2026-07-01,700,ACTIVE",
            ],
            ["BK,2026-07-01,2026-07-06,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["fare_type"] == "ECON"
        assert summary["matched_count"] == 1

    def test_blackout_filter_happens_before_budget_consumption(self):
        """A blacked-out candidate should not consume ticket rows or rider budget."""
        write_inputs(
            [
                "BLK6201,CUST6201,900,ACTIVE,CABIN,2026-07-10",
                "BLK6201,CUST6201,400,ACTIVE,CABIN,2026-07-10",
            ],
            [
                "BLK6201,CUST6201,900,CB,2026-07-05",
                "BLK6201,CUST6201,400,CB,2026-07-07",
            ],
            ["2026-07-05 open", "2026-07-07 open"],
            ["CABIN,true,1"],
            ["CUST6201,CABIN,2026-07-01,500,ACTIVE"],
            ["CABIN,2026-07-01,2026-07-06,ACTIVE"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert [row["fare_type"] for row in rows] == ["", "CABIN"]
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
                "BLK6301,CUST6301,300,ACTIVE,ECON,2026-07-10",
                "BLK6302,CUST6302,300,ACTIVE,ECON,2026-07-10",
                "BLK6303,CUST6303,300,ACTIVE,ECON,2026-07-10",
                "BLK6304,CUST6304,300,ACTIVE,ECON,2026-07-10",
            ],
            [
                "BLK6301,CUST6301,300,EC,2026-07-05",
                "BLK6302,CUST6302,300,EC,2026-07-05",
                "BLK6303,CUST6303,300,EC,2026-07-05",
                "BLK6304,CUST6304,300,EC,2026-07-05",
            ],
            ["2026-07-05 open"],
            ["ECON,true,1"],
            [
                "CUST6301,ECON,2026-07-01,300,ACTIVE",
                "CUST6302,ECON,2026-07-01,300,ACTIVE",
                "CUST6303,ECON,2026-07-01,300,ACTIVE",
                "CUST6304,ECON,2026-07-01,300,ACTIVE",
            ],
            [
                "ECON,2026-07-01,2026-07-06,INACTIVE",
                "ECON,bad-date,2026-07-06,ACTIVE",
                "ECON,2026-07-06,2026-07-10,ACTIVE",
                "BAD,2026-07-01,2026-07-06,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "MATCHED"]
        assert summary["matched_count"] == 4

    def test_undated_inputs_skip_blackouts_and_limits_but_keep_methods_and_any(self):
        """Without credit_date, blackout and limit gates should be skipped while methods and ANY behavior remains."""
        write_inputs(
            ["BLK6401,CUST6401,500,ACTIVE,CABIN"],
            ["BLK6401,CUST6401,500,ANY"],
            ["2026-07-05 closed"],
            ["CABIN,true,1"],
            [],
            ["CABIN,2026-01-01,2026-12-31,ACTIVE"],
            dated=False,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["fare_type"] == "CABIN"
        assert summary["matched_amount_cents"] == 500

    def test_malformed_policy_rows_are_ignored_without_blocking_valid_rows(self):
        """Malformed method, limit, and blackout rows should be skipped while valid policy rows still allow a match."""
        write_inputs(
            ["POLICY1,CUSTPOL1,1600,ACTIVE,CABIN,2026-04-10"],
            ["POLICY1,CUSTPOL1,1600,CABIN,2026-04-04"],
            ["2026-04-04 open"],
            ["SHORTMETHOD", ",true,1", "CABIN,true,1"],
            [
                ", CABIN,2026-04-01,9999,ACTIVE",
                "CUSTPOL1,CABIN",
                "CUSTPOL1,CABIN,not-a-date,9999,ACTIVE",
                "CUSTPOL1,CABIN,2026-04-01,2000,ACTIVE",
            ],
            [
                ",2026-04-01,2026-04-09,ACTIVE",
                "CABIN,2026-04-01",
                "CABIN,not-a-date,2026-04-09,ACTIVE",
                "CABIN,2026-04-01,also-bad,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["fare_type"] == "CABIN"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 1600

    def test_malformed_and_missing_priorities_rank_after_numeric_priority(self):
        """Malformed or missing method priorities should rank after configured numeric priorities."""
        write_inputs(
            [
                "PRIORITY1,CUSTPRI1,1800,ACTIVE,ECON,2026-04-10",
                "PRIORITY1,CUSTPRI1,1800,ACTIVE,BIKE,2026-04-10",
                "PRIORITY1,CUSTPRI1,1800,ACTIVE,CABIN,2026-04-10",
            ],
            ["PRIORITY1,CUSTPRI1,1800,ANY,2026-04-04"],
            ["2026-04-04 open"],
            ["ECON,true,notnum", "BIKE,true,2", "CABIN,true"],
            ["CUSTPRI1,BIKE,2026-04-01,3000,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["fare_type"] == "BIKE"
        assert summary["matched_amount_cents"] == 1800

    def test_equal_effective_limit_dates_prefer_earliest_limit_row(self):
        """When limit effective dates tie, the earliest limit row should decide the daily cap."""
        write_inputs(
            ["LIMITTIE1,CUSTLIM1,1500,ACTIVE,ECON,2026-04-10"],
            ["LIMITTIE1,CUSTLIM1,1500,ECON,2026-04-04"],
            ["2026-04-04 open"],
            ["ECON,true,1"],
            [
                "CUSTLIM1,ECON,2026-04-01,1000,ACTIVE",
                "CUSTLIM1,ECON,2026-04-01,2000,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["fare_type"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 1500

    def test_malformed_method_rows_alone_do_not_enable_matching(self):
        """Malformed methods.csv rows must not make an otherwise valid type eligible."""
        write_inputs(
            ["METHBAD1,CUSTMET1,1300,ACTIVE,CABIN,2026-04-10"],
            ["METHBAD1,CUSTMET1,1300,CABIN,2026-04-04"],
            ["2026-04-04 open"],
            ["SHORTMETHOD", ",true,1", "CABIN,,1"],
            ["CUSTMET1,CABIN,2026-04-01,3000,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["fare_type"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 1300

    def test_short_limit_rows_are_ignored_without_blocking_valid_limit(self):
        """Short limit rows should be ignored while a later valid limit can still allow matching."""
        write_inputs(
            ["SHORTLIM1,CUSTSL1,1400,ACTIVE,CABIN,2026-04-10"],
            ["SHORTLIM1,CUSTSL1,1400,CABIN,2026-04-04"],
            ["2026-04-04 open"],
            ["CABIN,true,1"],
            ["CUSTSL1,CABIN", "CUSTSL1,CABIN,2026-04-01,2000,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["fare_type"] == "CABIN"
        assert summary["matched_amount_cents"] == 1400


    def test_short_blackout_rows_are_ignored_without_blocking_match(self):
        """Short blackout rows should be ignored instead of blocking an otherwise valid match."""
        write_inputs(
            ["SHORTBLK1,CUSTSB1,1450,ACTIVE,CABIN,2026-04-10"],
            ["SHORTBLK1,CUSTSB1,1450,CABIN,2026-04-04"],
            ["2026-04-04 open"],
            ["CABIN,true,1"],
            ["CUSTSB1,CABIN,2026-04-01,2000,ACTIVE"],
            ["CABIN,2026-04-01"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["fare_type"] == "CABIN"
        assert summary["matched_amount_cents"] == 1450


    def test_undated_any_priorities_treat_missing_and_malformed_as_late(self):
        """Undated ANY ranking should put missing and malformed priorities after numeric priorities."""
        write_inputs(
            [
                "UNDPRI1,CUSTUP1,900,ACTIVE,ECON",
                "UNDPRI1,CUSTUP1,900,ACTIVE,BIKE",
                "UNDPRI1,CUSTUP1,900,ACTIVE,CABIN",
            ],
            ["UNDPRI1,CUSTUP1,900,ANY"],
            ["2026-04-04 closed"],
            ["ECON,true,bad", "BIKE,true,4", "CABIN,true"],
            [],
            [],
            dated=False,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["fare_type"] == "BIKE"
        assert summary["matched_amount_cents"] == 900

    def test_any_latest_date_beats_config_priority(self):
        """For dated ANY actions, latest source date should rank before configured type priority."""
        write_inputs(
            [
                "ANYDATE1,CUSTAD1,1750,ACTIVE,BIKE,2026-04-08",
                "ANYDATE1,CUSTAD1,1750,ACTIVE,CABIN,2026-04-11",
            ],
            ["ANYDATE1,CUSTAD1,1750,ANY,2026-04-04"],
            ["2026-04-04 open"],
            ["BIKE,true,1", "CABIN,true,9"],
            ["CUSTAD1,CABIN,2026-04-01,3000,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["fare_type"] == "CABIN"
        assert summary["matched_amount_cents"] == 1750
