"""Milestone 4 verifier tests for methods, ANY, patient limits, and blackouts."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
SOURCES = APP / "data" / "appointments.csv"
CREDITS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
METHODS = APP / "config" / "methods.csv"
LIMITS = APP / "config" / "patient_limits.csv"
BLACKOUTS = APP / "config" / "blackouts.csv"
REPORT = APP / "out" / "copay_credit_report.csv"
SUMMARY = APP / "out" / "copay_credit_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")
DEFAULT_METHODS = "service_type,enabled,priority\nCLEAN,true,2\nXRAY,true,1\nSURG,true,3\n"


def build_program():
    """Compile the Go appointment credit reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 4 tests."""
    build_program()


def write_inputs(
    appointment_rows,
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
        CLASSES.write_text("appointment_id,patient_id,amount_cents,status,service_type,appointment_date\n" + "\n".join(appointment_rows) + "\n")
        CREDITS.write_text("appointment_id,patient_id,amount_cents,service_type,credit_date\n" + "\n".join(credit_rows) + "\n")
    else:
        CLASSES.write_text("appointment_id,patient_id,amount_cents,status,service_type\n" + "\n".join(appointment_rows) + "\n")
        CREDITS.write_text("appointment_id,patient_id,amount_cents,service_type\n" + "\n".join(credit_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    if method_rows is not None:
        METHODS.write_text("service_type,enabled,priority\n" + "\n".join(method_rows) + "\n")
    else:
        METHODS.write_text(DEFAULT_METHODS)
    limit_body = "" if limit_rows is None else "\n".join(limit_rows) + ("\n" if limit_rows else "")
    LIMITS.write_text("patient_id,service_type,effective_date,max_daily_amount,status\n" + limit_body)
    blackout_body = "" if blackout_rows is None else "\n".join(blackout_rows) + ("\n" if blackout_rows else "")
    BLACKOUTS.write_text("service_type,start_date,end_date,state\n" + blackout_body)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse its CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone4:
    """Methods config, ANY credits, patient limits, and blackouts interact with prior matching gates."""

    def test_disabled_configured_service_type_rejects_otherwise_valid_credit(self):
        """Disabled methods.csv service types must not match even with valid ids, dates, and aliases."""
        write_inputs(
            ["CFG1001,CUST1001,1200,ACTIVE,XRAY,2026-04-10"],
            ["CFG1001,CUST1001,1200,XR,2026-04-05"],
            ["2026-04-05 open"],
            ["CLEAN,true,2", "XRAY,false,1", "SURG,true,3"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["service_type"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1200,
        }

    def test_any_same_date_uses_config_priority_before_appointment_order(self):
        """ANY ties on visit date should use configured priority before appointment row order."""
        write_inputs(
            [
                "ANY2001,CUST2001,700,ACTIVE,CLEAN,2026-04-08",
                "ANY2001,CUST2001,700,ACTIVE,SURG,2026-04-08",
                "ANY2001,CUST2001,700,ACTIVE,XRAY,2026-04-08",
            ],
            ["ANY2001,CUST2001,700,ANY,2026-04-04"],
            ["2026-04-04 open"],
            ["CLEAN,true,5", "XRAY,true,1", "SURG,true,3"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_type"] == "XRAY"
        assert summary["matched_count"] == 1

    def test_any_equal_priority_tie_uses_earliest_appointment_row(self):
        """ANY ties on date and priority should choose the earliest appointment input row."""
        write_inputs(
            [
                "ANY3001,CUST3001,800,ACTIVE,CLEAN,2026-04-09",
                "ANY3001,CUST3001,800,ACTIVE,XRAY,2026-04-09",
            ],
            ["ANY3001,CUST3001,800,ANY,2026-04-04"],
            ["2026-04-04 open"],
            ["CLEAN,true,1", "XRAY,true,1", "SURG,true,9"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_type"] == "CLEAN"
        assert summary["matched_amount_cents"] == 800

    def test_any_consumes_selected_row_and_reranks_remaining_candidates(self):
        """ANY matching should consume by row position and rerank remaining candidates."""
        write_inputs(
            [
                "ANY4001,CUST4001,500,ACTIVE,CLEAN,2026-04-07",
                "ANY4001,CUST4001,500,ACTIVE,XRAY,2026-04-07",
            ],
            [
                "ANY4001,CUST4001,500,ANY,2026-04-04",
                "ANY4001,CUST4001,500,ANY,2026-04-04",
                "ANY4001,CUST4001,500,ANY,2026-04-04",
            ],
            ["2026-04-04 open"],
            ["CLEAN,true,1", "XRAY,true,2", "SURG,true,3"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["service_type"] for row in rows] == ["CLEAN", "XRAY", ""]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1000,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_non_any_still_requires_exact_canonical_service_type(self):
        """Config policy must not turn named class-type credits into wildcard matches."""
        write_inputs(
            ["CFG5001,CUST5001,900,ACTIVE,CLEAN,2026-04-10"],
            ["CFG5001,CUST5001,900,XR,2026-04-05"],
            ["2026-04-05 open"],
            ["CLEAN,true,1", "XRAY,true,2", "SURG,true,3"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["service_type"] == ""
        assert summary["unmatched_amount_cents"] == 900

    def test_missing_and_malformed_methods_do_not_enable_service_type(self):
        """Missing, blank, malformed, and non-true method rows should leave types ineligible."""
        write_inputs(
            [
                "BILLM411,CUSTM411,1100,ACTIVE,CLEAN,2026-05-12",
                "BILLM412,CUSTM412,1200,ACTIVE,XRAY,2026-05-12",
                "BILLM413,CUSTM413,1300,ACTIVE,SURG,2026-05-12",
            ],
            [
                "BILLM411,CUSTM411,1100,CLEAN,2026-05-06",
                "BILLM412,CUSTM412,1200,XR,2026-05-06",
                "BILLM413,CUSTM413,1300,SG,2026-05-06",
            ],
            ["2026-05-06 open"],
            [
                "CLEAN,maybe,2",
                "XRAY",
                ",true,1",
                "SURG,TRUE,3",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "MATCHED"]
        assert [row["service_type"] for row in rows] == ["", "", "SURG"]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1300,
            "unmatched_count": 2,
            "unmatched_amount_cents": 2300,
        }

    def test_methods_alias_normalization_enables_xr_entry(self):
        """Method service_type aliases such as XR should normalize before enabled checks."""
        write_inputs(
            ["CFG6001,CUST6001,750,ACTIVE,XRAY,2026-04-10"],
            ["CFG6001,CUST6001,750,XR,2026-04-05"],
            ["2026-04-05 open"],
            ["XR,true,1", "CLEAN,true,2"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_type"] == "XRAY"
        assert summary["matched_count"] == 1

    def test_any_undated_inputs_rank_by_priority_then_appointment_order(self):
        """Without date columns, ANY should rank only by priority then earliest appointment row."""
        write_inputs(
            [
                "UND7001,CUST7001,600,ACTIVE,SURG",
                "UND7001,CUST7001,600,ACTIVE,CLEAN",
                "UND7001,CUST7001,600,ACTIVE,XRAY",
            ],
            ["UND7001,CUST7001,600,ANY"],
            ["2026-04-01 closed"],
            ["CLEAN,true,3", "XRAY,true,1", "SURG,true,2"],
            dated=False,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_type"] == "XRAY"
        assert summary["matched_amount_cents"] == 600

    def test_enabled_method_does_not_bypass_closed_calendar_date(self):
        """An enabled service type must still fail when the credit date is not open."""
        write_inputs(
            ["BILLM431,CUSTM431,1500,ACTIVE,CLEAN,2026-05-15"],
            ["BILLM431,CUSTM431,1500,CL,2026-05-09"],
            ["2026-05-09 closed"],
            ["CLEAN,true,1"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["service_type"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1500,
        }

    def test_methods_gate_preserves_latest_appointment_date_selection(self):
        """Enabled methods should not weaken latest appointment_date selection or consumption."""
        write_inputs(
            [
                "BILLM421,CUSTM421,1400,ACTIVE,CLEAN,2026-05-08",
                "BILLM421,CUSTM421,1400,ACTIVE,CLEAN,2026-05-14",
                "BILLM421,CUSTM421,1400,ACTIVE,CLEAN,2026-05-14",
            ],
            [
                "BILLM421,CUSTM421,1400,CL,2026-05-07",
                "BILLM421,CUSTM421,1400,CL,2026-05-07",
                "BILLM421,CUSTM421,1400,CL,2026-05-07",
                "BILLM421,CUSTM421,1400,CL,2026-05-07",
            ],
            ["2026-05-07 open"],
            ["CLEAN,true,1"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["service_type"] for row in rows] == ["CLEAN", "CLEAN", "CLEAN", ""]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 4200,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1400,
        }

    def test_latest_effective_limit_caps_daily_credits_in_credit_order(self):
        """The latest active limit should cap same patient/access/date credits cumulatively."""
        write_inputs(
            [
                "LIM5001,CUST5001,600,ACTIVE,CLEAN,2026-06-10",
                "LIM5002,CUST5001,500,ACTIVE,CLEAN,2026-06-10",
                "LIM5003,CUST5001,400,ACTIVE,CLEAN,2026-06-10",
            ],
            [
                "LIM5001,CUST5001,600,CL,2026-06-05",
                "LIM5002,CUST5001,500,CL,2026-06-05",
                "LIM5003,CUST5001,400,CL,2026-06-05",
            ],
            ["2026-06-05 open"],
            ["CLEAN,true,1"],
            [
                "CUST5001,CLEAN,2026-05-01,900,ACTIVE",
                "CUST5001,CL,2026-06-01,1100,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["service_type"] for row in rows] == ["CLEAN", "CLEAN", ""]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1100,
            "unmatched_count": 1,
            "unmatched_amount_cents": 400,
        }

    def test_budget_is_partitioned_by_patient_selected_service_type_and_credit_date(self):
        """Budget consumption should be keyed by patient, selected service type, and credit_date."""
        write_inputs(
            [
                "LIM5101,CUST5101,700,ACTIVE,CLEAN,2026-06-10",
                "LIM5102,CUST5101,700,ACTIVE,SURG,2026-06-10",
                "LIM5103,CUST5101,700,ACTIVE,CLEAN,2026-06-11",
                "LIM5104,CUST5102,700,ACTIVE,CLEAN,2026-06-10",
            ],
            [
                "LIM5101,CUST5101,700,CL,2026-06-05",
                "LIM5102,CUST5101,700,SG,2026-06-05",
                "LIM5103,CUST5101,700,CL,2026-06-06",
                "LIM5104,CUST5102,700,CL,2026-06-05",
            ],
            ["2026-06-05 open", "2026-06-06 open"],
            ["CLEAN,true,1", "SURG,true,2"],
            [
                "CUST5101,CLEAN,2026-06-01,700,ACTIVE",
                "CUST5101,SURG,2026-06-01,700,ACTIVE",
                "CUST5102,CLEAN,2026-06-01,700,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "MATCHED"]
        assert [row["service_type"] for row in rows] == ["CLEAN", "SURG", "CLEAN", "CLEAN"]
        assert summary["matched_count"] == 4
        assert summary["matched_amount_cents"] == 2800

    def test_any_credit_uses_selected_candidate_service_type_for_limit(self):
        """ANY credits should look up budget against the service type of the selected appointment."""
        write_inputs(
            [
                "LIM5201,CUST5201,800,ACTIVE,CLEAN,2026-06-10",
                "LIM5201,CUST5201,800,ACTIVE,SURG,2026-06-10",
            ],
            [
                "LIM5201,CUST5201,800,ANY,2026-06-05",
                "LIM5201,CUST5201,800,ANY,2026-06-05",
            ],
            ["2026-06-05 open"],
            ["CLEAN,true,1", "SURG,true,2"],
            [
                "CUST5201,CLEAN,2026-06-01,800,ACTIVE",
                "CUST5201,SURG,2026-06-01,700,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["service_type"] for row in rows] == ["CLEAN", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_inactive_future_unknown_and_nonnumeric_limits_are_ignored(self):
        """Only active, effective, numeric limits for known service types should enable budget matching."""
        write_inputs(
            [
                "LIM5301,CUST5301,300,ACTIVE,CLEAN,2026-06-10",
                "LIM5302,CUST5302,300,ACTIVE,CLEAN,2026-06-10",
                "LIM5303,CUST5303,300,ACTIVE,CLEAN,2026-06-10",
                "LIM5304,CUST5304,300,ACTIVE,CLEAN,2026-06-10",
                "LIM5305,CUST5305,300,ACTIVE,CLEAN,2026-06-10",
            ],
            [
                "LIM5301,CUST5301,300,CL,2026-06-05",
                "LIM5302,CUST5302,300,CL,2026-06-05",
                "LIM5303,CUST5303,300,CL,2026-06-05",
                "LIM5304,CUST5304,300,CL,2026-06-05",
                "LIM5305,CUST5305,300,CL,2026-06-05",
            ],
            ["2026-06-05 open"],
            ["CLEAN,true,1"],
            [
                "CUST5301,CLEAN,2026-06-01,300,INACTIVE",
                "CUST5302,CLEAN,2026-06-06,300,ACTIVE",
                "CUST5303,CLEAN,2026-06-01,not-number,ACTIVE",
                "CUST5304,BAD,2026-06-01,300,ACTIVE",
                "CUST5305,CL,2026-06-01,300,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert [row["service_type"] for row in rows] == ["", "", "", "", "CLEAN"]
        assert summary["matched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1200

    def test_budget_rejection_does_not_consume_appointment_row_needed_by_later_credit(self):
        """An over-limit credit must not consume a appointment row needed by a later eligible credit."""
        write_inputs(
            [
                "LIM5401,CUST5401,900,ACTIVE,CLEAN,2026-06-10",
                "LIM5401,CUST5401,400,ACTIVE,CLEAN,2026-06-10",
            ],
            [
                "LIM5401,CUST5401,900,CL,2026-06-05",
                "LIM5401,CUST5401,400,CL,2026-06-05",
            ],
            ["2026-06-05 open"],
            ["CLEAN,true,1"],
            ["CUST5401,CL,2026-06-01,500,ACTIVE"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert [row["service_type"] for row in rows] == ["", "CLEAN"]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 400,
            "unmatched_count": 1,
            "unmatched_amount_cents": 900,
        }

    def test_undated_inputs_keep_methods_and_any_behavior_without_limits(self):
        """When credit_date is absent, patient_limits.csv should not gate matching."""
        write_inputs(
            ["LIM5501,CUST5501,1000,ACTIVE,CLEAN"],
            ["LIM5501,CUST5501,1000,CL"],
            ["2026-06-05 closed"],
            ["CLEAN,true,1"],
            [],
            dated=False,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_type"] == "CLEAN"
        assert summary["matched_count"] == 1

    def test_named_credit_is_blocked_by_active_blackout_range(self):
        """A matching appointment should be ineligible when its service type is blacked out on credit_date."""
        write_inputs(
            ["BLK6001,CUST6001,600,ACTIVE,SURG,2026-07-10"],
            ["BLK6001,CUST6001,600,SG,2026-07-05"],
            ["2026-07-05 open"],
            ["SURG,true,1"],
            ["CUST6001,SURG,2026-07-01,600,ACTIVE"],
            ["SURG,2026-07-01,2026-07-06,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["service_type"] == ""
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
                "BLK6101,CUST6101,700,ACTIVE,XRAY,2026-07-10",
                "BLK6101,CUST6101,700,ACTIVE,CLEAN,2026-07-10",
            ],
            ["BLK6101,CUST6101,700,ANY,2026-07-05"],
            ["2026-07-05 open"],
            ["XRAY,true,1", "CLEAN,true,2"],
            [
                "CUST6101,XRAY,2026-07-01,700,ACTIVE",
                "CUST6101,CLEAN,2026-07-01,700,ACTIVE",
            ],
            ["XR,2026-07-01,2026-07-06,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_type"] == "CLEAN"
        assert summary["matched_count"] == 1

    def test_blackout_filter_happens_before_budget_consumption(self):
        """A blacked-out candidate should not consume appointment rows or patient budget."""
        write_inputs(
            [
                "BLK6201,CUST6201,900,ACTIVE,SURG,2026-07-10",
                "BLK6201,CUST6201,400,ACTIVE,SURG,2026-07-10",
            ],
            [
                "BLK6201,CUST6201,900,SG,2026-07-05",
                "BLK6201,CUST6201,400,SG,2026-07-07",
            ],
            ["2026-07-05 open", "2026-07-07 open"],
            ["SURG,true,1"],
            ["CUST6201,SURG,2026-07-01,500,ACTIVE"],
            ["SURG,2026-07-01,2026-07-06,ACTIVE"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert [row["service_type"] for row in rows] == ["", "SURG"]
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
                "BLK6301,CUST6301,300,ACTIVE,CLEAN,2026-07-10",
                "BLK6302,CUST6302,300,ACTIVE,CLEAN,2026-07-10",
                "BLK6303,CUST6303,300,ACTIVE,CLEAN,2026-07-10",
                "BLK6304,CUST6304,300,ACTIVE,CLEAN,2026-07-10",
            ],
            [
                "BLK6301,CUST6301,300,CL,2026-07-05",
                "BLK6302,CUST6302,300,CL,2026-07-05",
                "BLK6303,CUST6303,300,CL,2026-07-05",
                "BLK6304,CUST6304,300,CL,2026-07-05",
            ],
            ["2026-07-05 open"],
            ["CLEAN,true,1"],
            [
                "CUST6301,CLEAN,2026-07-01,300,ACTIVE",
                "CUST6302,CLEAN,2026-07-01,300,ACTIVE",
                "CUST6303,CLEAN,2026-07-01,300,ACTIVE",
                "CUST6304,CLEAN,2026-07-01,300,ACTIVE",
            ],
            [
                "CLEAN,2026-07-01,2026-07-06,INACTIVE",
                "CLEAN,bad-date,2026-07-06,ACTIVE",
                "CLEAN,2026-07-06,2026-07-10,ACTIVE",
                "BAD,2026-07-01,2026-07-06,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "MATCHED"]
        assert summary["matched_count"] == 4

    def test_undated_inputs_skip_blackouts_and_limits_but_keep_methods_and_any(self):
        """Without credit_date, blackout and limit gates should be skipped while methods and ANY behavior remains."""
        write_inputs(
            ["BLK6401,CUST6401,500,ACTIVE,SURG"],
            ["BLK6401,CUST6401,500,ANY"],
            ["2026-07-05 closed"],
            ["SURG,true,1"],
            [],
            ["SURG,2026-01-01,2026-12-31,ACTIVE"],
            dated=False,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_type"] == "SURG"
        assert summary["matched_amount_cents"] == 500

    def test_malformed_policy_rows_are_ignored_without_blocking_valid_rows(self):
        """Malformed method, limit, and blackout rows should be skipped while valid policy rows still allow a match."""
        write_inputs(
            ["POLICY1,CUSTPOL1,1600,ACTIVE,SURG,2026-04-10"],
            ["POLICY1,CUSTPOL1,1600,SURG,2026-04-04"],
            ["2026-04-04 open"],
            ["SHORTMETHOD", ",true,1", "SURG,true,1"],
            [
                ", SURG,2026-04-01,9999,ACTIVE",
                "CUSTPOL1,SURG",
                "CUSTPOL1,SURG,not-a-date,9999,ACTIVE",
                "CUSTPOL1,SURG,2026-04-01,2000,ACTIVE",
            ],
            [
                ",2026-04-01,2026-04-09,ACTIVE",
                "SURG,2026-04-01",
                "SURG,not-a-date,2026-04-09,ACTIVE",
                "SURG,2026-04-01,also-bad,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_type"] == "SURG"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 1600

    def test_malformed_and_missing_priorities_rank_after_numeric_priority(self):
        """Malformed or missing method priorities should rank after configured numeric priorities."""
        write_inputs(
            [
                "PRIORITY1,CUSTPRI1,1800,ACTIVE,CLEAN,2026-04-10",
                "PRIORITY1,CUSTPRI1,1800,ACTIVE,XRAY,2026-04-10",
                "PRIORITY1,CUSTPRI1,1800,ACTIVE,SURG,2026-04-10",
            ],
            ["PRIORITY1,CUSTPRI1,1800,ANY,2026-04-04"],
            ["2026-04-04 open"],
            ["CLEAN,true,notnum", "XRAY,true,2", "SURG,true"],
            ["CUSTPRI1,XRAY,2026-04-01,3000,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_type"] == "XRAY"
        assert summary["matched_amount_cents"] == 1800

    def test_equal_effective_limit_dates_prefer_earliest_limit_row(self):
        """When limit effective dates tie, the earliest limit row should decide the daily cap."""
        write_inputs(
            ["LIMITTIE1,CUSTLIM1,1500,ACTIVE,CLEAN,2026-04-10"],
            ["LIMITTIE1,CUSTLIM1,1500,CLEAN,2026-04-04"],
            ["2026-04-04 open"],
            ["CLEAN,true,1"],
            [
                "CUSTLIM1,CLEAN,2026-04-01,1000,ACTIVE",
                "CUSTLIM1,CLEAN,2026-04-01,2000,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["service_type"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 1500

    def test_malformed_method_rows_alone_do_not_enable_matching(self):
        """Malformed methods.csv rows must not make an otherwise valid type eligible."""
        write_inputs(
            ["METHBAD1,CUSTMET1,1300,ACTIVE,SURG,2026-04-10"],
            ["METHBAD1,CUSTMET1,1300,SURG,2026-04-04"],
            ["2026-04-04 open"],
            ["SHORTMETHOD", ",true,1", "SURG,,1"],
            ["CUSTMET1,SURG,2026-04-01,3000,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["service_type"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 1300

    def test_short_limit_rows_are_ignored_without_blocking_valid_limit(self):
        """Short limit rows should be ignored while a later valid limit can still allow matching."""
        write_inputs(
            ["SHORTLIM1,CUSTSL1,1400,ACTIVE,SURG,2026-04-10"],
            ["SHORTLIM1,CUSTSL1,1400,SURG,2026-04-04"],
            ["2026-04-04 open"],
            ["SURG,true,1"],
            ["CUSTSL1,SURG", "CUSTSL1,SURG,2026-04-01,2000,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_type"] == "SURG"
        assert summary["matched_amount_cents"] == 1400


    def test_short_blackout_rows_are_ignored_without_blocking_match(self):
        """Short blackout rows should be ignored instead of blocking an otherwise valid match."""
        write_inputs(
            ["SHORTBLK1,CUSTSB1,1450,ACTIVE,SURG,2026-04-10"],
            ["SHORTBLK1,CUSTSB1,1450,SURG,2026-04-04"],
            ["2026-04-04 open"],
            ["SURG,true,1"],
            ["CUSTSB1,SURG,2026-04-01,2000,ACTIVE"],
            ["SURG,2026-04-01"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_type"] == "SURG"
        assert summary["matched_amount_cents"] == 1450


    def test_undated_any_priorities_treat_missing_and_malformed_as_late(self):
        """Undated ANY ranking should put missing and malformed priorities after numeric priorities."""
        write_inputs(
            [
                "UNDPRI1,CUSTUP1,900,ACTIVE,CLEAN",
                "UNDPRI1,CUSTUP1,900,ACTIVE,XRAY",
                "UNDPRI1,CUSTUP1,900,ACTIVE,SURG",
            ],
            ["UNDPRI1,CUSTUP1,900,ANY"],
            ["2026-04-04 closed"],
            ["CLEAN,true,bad", "XRAY,true,4", "SURG,true"],
            [],
            [],
            dated=False,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_type"] == "XRAY"
        assert summary["matched_amount_cents"] == 900

    def test_any_latest_date_beats_config_priority(self):
        """For dated ANY actions, latest source date should rank before configured type priority."""
        write_inputs(
            [
                "ANYDATE1,CUSTAD1,1750,ACTIVE,XRAY,2026-04-08",
                "ANYDATE1,CUSTAD1,1750,ACTIVE,SURG,2026-04-11",
            ],
            ["ANYDATE1,CUSTAD1,1750,ANY,2026-04-04"],
            ["2026-04-04 open"],
            ["XRAY,true,1", "SURG,true,9"],
            ["CUSTAD1,SURG,2026-04-01,3000,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_type"] == "SURG"
        assert summary["matched_amount_cents"] == 1750
