"""Milestone 4 tests for policy-driven lease deposit reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
LEASES = APP / "data" / "leases.csv"
DEPOSITS = APP / "data" / "deposits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
METHODS = APP / "config" / "methods.csv"
LIMITS = APP / "config" / "customer_limits.csv"
BLACKOUTS = APP / "config" / "blackouts.csv"
REPORT = APP / "out" / "deposit_report.csv"
SUMMARY = APP / "out" / "deposit_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")
DEFAULT_METHODS = "channel,enabled,priority\nACH,true,2\nCARD,true,1\nWIRE,true,3\n"


def build_program():
    """Compile the Go deposit reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 4 tests."""
    build_program()


def write_inputs(
    lease_rows,
    deposit_rows,
    calendar_rows,
    method_rows=None,
    limit_rows=None,
    blackout_rows=None,
    dated=True,
):
    """Replace data and policy files with one test scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    if dated:
        LEASES.write_text("lease_id,customer_id,amount_cents,status,channel,due_date\n" + "\n".join(lease_rows) + "\n")
        DEPOSITS.write_text("lease_id,customer_id,amount_cents,channel,deposit_date\n" + "\n".join(deposit_rows) + "\n")
    else:
        LEASES.write_text("lease_id,customer_id,amount_cents,status,channel\n" + "\n".join(lease_rows) + "\n")
        DEPOSITS.write_text("lease_id,customer_id,amount_cents,channel\n" + "\n".join(deposit_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    METHODS.write_text(DEFAULT_METHODS if method_rows is None else "channel,enabled,priority\n" + "\n".join(method_rows) + "\n")
    limit_body = "" if limit_rows is None else "\n".join(limit_rows) + ("\n" if limit_rows else "")
    LIMITS.write_text("customer_id,channel,effective_date,max_daily_amount,status\n" + limit_body)
    blackout_body = "" if blackout_rows is None else "\n".join(blackout_rows) + ("\n" if blackout_rows else "")
    BLACKOUTS.write_text("channel,start_date,end_date,state\n" + blackout_body)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse its outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone4:
    """Configured channels, wildcard deposits, limits, and blackout gates."""

    def test_disabled_channel_rejects_otherwise_valid_deposit(self):
        """A disabled methods.csv channel must not match even when all prior gates pass."""
        write_inputs(
            ["POL1001,CUST1001,1200,POSTED,CARD,2026-04-10"],
            ["POL1001,CUST1001,1200,CC,2026-04-04"],
            ["2026-04-04 open"],
            ["ACH,true,2", "CARD,false,1", "WIRE,true,3"],
            ["CUST1001,CARD,2026-04-01,5000,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1200,
        }

    def test_non_any_still_requires_channel_equality(self):
        """Enabled channels do not let a CARD deposit match an ACH lease."""
        write_inputs(
            ["POL1101,CUST1101,1300,POSTED,ACH,2026-04-10"],
            ["POL1101,CUST1101,1300,CARD,2026-04-04"],
            ["2026-04-04 open"],
            ["ACH,true,2", "CARD,true,1", "WIRE,true,3"],
            ["CUST1101,CARD,2026-04-01,5000,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["unmatched_amount_cents"] == 1300

    def test_any_latest_due_date_beats_channel_priority(self):
        """For dated ANY deposits, latest due_date ranks before configured channel priority."""
        write_inputs(
            [
                "ANY2001,CUST2001,700,POSTED,CARD,2026-04-08",
                "ANY2001,CUST2001,700,POSTED,ACH,2026-04-11",
            ],
            ["ANY2001,CUST2001,700,ANY,2026-04-04"],
            ["2026-04-04 open"],
            ["CARD,true,1", "ACH,true,9", "WIRE,true,3"],
            [
                "CUST2001,CARD,2026-04-01,1000,ACTIVE",
                "CUST2001,ACH,2026-04-01,1000,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["channel"] == "ACH"
        assert summary["matched_amount_cents"] == 700

    def test_any_same_due_date_uses_priority_then_lease_order(self):
        """ANY ties on due_date should use priority, then earliest lease row."""
        write_inputs(
            [
                "ANY3001,CUST3001,800,POSTED,WIRE,2026-04-09",
                "ANY3001,CUST3001,800,POSTED,CARD,2026-04-09",
                "ANY3001,CUST3001,800,POSTED,ACH,2026-04-09",
            ],
            ["ANY3001,CUST3001,800,ANY,2026-04-04"],
            ["2026-04-04 open"],
            ["WIRE,true,5", "CARD,true,1", "ACH,true,1"],
            [
                "CUST3001,WIRE,2026-04-01,1000,ACTIVE",
                "CUST3001,CARD,2026-04-01,1000,ACTIVE",
                "CUST3001,ACH,2026-04-01,1000,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["channel"] == "CARD"
        assert summary["matched_count"] == 1

    def test_malformed_and_missing_priorities_rank_after_numeric_priority(self):
        """Malformed or missing method priorities should rank after configured numeric priorities."""
        write_inputs(
            [
                "ANY3101,CUST3101,850,POSTED,CARD,2026-04-09",
                "ANY3101,CUST3101,850,POSTED,ACH,2026-04-09",
                "ANY3101,CUST3101,850,POSTED,WIRE,2026-04-09",
            ],
            ["ANY3101,CUST3101,850,ANY,2026-04-04"],
            ["2026-04-04 open"],
            ["CARD,true,bad", "ACH,true,2", "WIRE,true"],
            [
                "CUST3101,CARD,2026-04-01,1200,ACTIVE",
                "CUST3101,ACH,2026-04-01,1200,ACTIVE",
                "CUST3101,WIRE,2026-04-01,1200,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["channel"] == "ACH"
        assert summary["matched_amount_cents"] == 850

    def test_customer_limit_caps_daily_deposits_in_input_order(self):
        """Matched deposits consume the selected channel's daily customer cap."""
        write_inputs(
            [
                "CAP4001,CUST4001,600,POSTED,CARD,2026-04-10",
                "CAP4002,CUST4001,500,POSTED,CARD,2026-04-11",
                "CAP4003,CUST4001,400,POSTED,CARD,2026-04-12",
            ],
            [
                "CAP4001,CUST4001,600,CARD,2026-04-04",
                "CAP4002,CUST4001,500,CARD,2026-04-04",
                "CAP4003,CUST4001,400,CARD,2026-04-04",
            ],
            ["2026-04-04 open"],
            ["CARD,true,1"],
            ["CUST4001,CARD,2026-04-01,1000,ACTIVE"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["channel"] for row in rows] == ["CARD", "", "CARD"]
        assert summary["matched_amount_cents"] == 1000
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_effective_limit_wins_with_row_order_tie(self):
        """Limits use latest effective_date, then earliest limit input row when dates tie."""
        write_inputs(
            ["LIM5001,CUST5001,1500,POSTED,WIRE,2026-04-10"],
            ["LIM5001,CUST5001,1500,WIR,2026-04-04"],
            ["2026-04-04 open"],
            ["WIRE,true,1"],
            [
                "CUST5001,WIRE,2026-04-01,1000,ACTIVE",
                "CUST5001,WIRE,2026-04-01,2000,ACTIVE",
                "CUST5001,WIRE,2026-04-02,3000,INACTIVE",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["unmatched_amount_cents"] == 1500

    def test_active_blackout_blocks_named_deposit(self):
        """A valid active blackout range should make that channel ineligible."""
        write_inputs(
            ["BLK6001,CUST6001,900,POSTED,WIRE,2026-04-10"],
            ["BLK6001,CUST6001,900,WIR,2026-04-04"],
            ["2026-04-04 open"],
            ["WIRE,true,1"],
            ["CUST6001,WIRE,2026-04-01,2000,ACTIVE"],
            ["WIRE,2026-04-01,2026-04-09,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["matched_count"] == 0

    def test_invalid_blackout_range_is_ignored(self):
        """Malformed or reversed blackout date ranges must not block a valid deposit."""
        write_inputs(
            ["BLK6101,CUST6101,950,POSTED,CARD,2026-04-10"],
            ["BLK6101,CUST6101,950,CC,2026-04-04"],
            ["2026-04-04 open"],
            ["CARD,true,1"],
            ["CUST6101,CARD,2026-04-01,2000,ACTIVE"],
            ["CARD,2026-04-09,2026-04-01,ACTIVE", "CARD,bad,2026-04-09,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["channel"] == "CARD"
        assert summary["matched_amount_cents"] == 950

    def test_any_skips_blacked_out_best_candidate(self):
        """Blackout filtering happens before ANY candidate ranking and budget consumption."""
        write_inputs(
            [
                "BLK7001,CUST7001,1000,POSTED,CARD,2026-04-12",
                "BLK7001,CUST7001,1000,POSTED,ACH,2026-04-10",
            ],
            ["BLK7001,CUST7001,1000,ANY,2026-04-04"],
            ["2026-04-04 open"],
            ["CARD,true,1", "ACH,true,5"],
            ["CUST7001,ACH,2026-04-01,2000,ACTIVE"],
            ["CARD,2026-04-01,2026-04-09,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["channel"] == "ACH"
        assert summary["matched_amount_cents"] == 1000

    def test_malformed_policy_rows_are_ignored_without_blocking_valid_rows(self):
        """Short, blank, malformed, inactive, and nonnumeric policy rows should not crash or apply."""
        write_inputs(
            ["BAD8001,CUST8001,1100,POSTED,CARD,2026-04-10"],
            ["BAD8001,CUST8001,1100,CC,2026-04-04"],
            ["2026-04-04 open"],
            ["SHORT", ",true,1", "CARD,,1", "CARD,true,bad"],
            [
                "CUST8001,CARD",
                ",CARD,2026-04-01,2000,ACTIVE",
                "CUST8001,CARD,not-a-date,2000,ACTIVE",
                "CUST8001,CARD,2026-04-01,nope,ACTIVE",
                "CUST8001,CARD,2026-04-01,2000,INACTIVE",
                "CUST8001,CARD,2026-04-01,2000,ACTIVE",
            ],
            [",2026-04-01,2026-04-09,ACTIVE", "CARD,2026-04-01", "CARD,bad,2026-04-09,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["channel"] == "CARD"
        assert summary["matched_amount_cents"] == 1100

    def test_no_active_limit_row_blocks_deposit(self):
        """Dated mode requires an ACTIVE limit row for the selected customer and channel."""
        write_inputs(
            ["LIM001,CUST001,500,POSTED,CARD,2026-04-10"],
            ["LIM001,CUST001,500,CC,2026-04-04"],
            ["2026-04-04 open"],
            ["CARD,true,1"],
            [],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["matched_count"] == 0

    def test_config_methods_and_limits_use_channel_aliases_only(self):
        """methods.csv and customer_limits.csv must normalize CC/WIR aliases, not only input rows."""
        write_inputs(
            ["ALIAS01,CUSTA1,1000,POSTED,CARD,2026-04-10"],
            ["ALIAS01,CUSTA1,1000,CC,2026-04-04"],
            ["2026-04-04 open"],
            ["CC,true,1"],
            ["CUSTA1,CC,2026-04-01,2000,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["channel"] == "CARD"
        assert summary["matched_amount_cents"] == 1000

    def test_config_blackout_channel_alias_blocks_deposit(self):
        """blackouts.csv must normalize WIR to WIRE when deciding channel blackout eligibility."""
        write_inputs(
            ["ALIAS02,CUSTA2,900,POSTED,WIRE,2026-04-10"],
            ["ALIAS02,CUSTA2,900,WIR,2026-04-04"],
            ["2026-04-04 open"],
            ["WIR,true,1"],
            ["CUSTA2,WIR,2026-04-01,2000,ACTIVE"],
            ["WIR,2026-04-01,2026-04-09,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["matched_count"] == 0

    def test_any_uses_limit_lookup_channel_not_priority_only(self):
        """ANY deposits must look up limits on the selected channel, not just configured priority."""
        write_inputs(
            [
                "ANY2101,CUST2101,100,POSTED,CARD,2026-04-09",
                "ANY2101,CUST2101,100,POSTED,ACH,2026-04-09",
            ],
            ["ANY2101,CUST2101,100,ANY,2026-04-04"],
            ["2026-04-04 open"],
            ["CARD,true,1", "ACH,true,2"],
            ["CUST2101,ACH,2026-04-01,500,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["channel"] == "ACH"
        assert summary["matched_amount_cents"] == 100

    def test_inactive_blackout_does_not_block(self):
        """Valid blackout date ranges with INACTIVE state must not block matching."""
        write_inputs(
            ["B1,CUSTB1,900,POSTED,WIRE,2026-04-10"],
            ["B1,CUSTB1,900,WIR,2026-04-04"],
            ["2026-04-04 open"],
            ["WIRE,true,1"],
            ["CUSTB1,WIRE,2026-04-01,2000,ACTIVE"],
            ["WIRE,2026-04-01,2026-04-09,INACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["channel"] == "WIRE"
        assert summary["matched_amount_cents"] == 900

    def test_undated_inputs_skip_limits_and_blackouts_but_keep_methods_and_any(self):
        """Without date columns, limits and blackouts are skipped while methods and ANY still apply."""
        write_inputs(
            ["UND9001,CUST9001,500,POSTED,WIRE"],
            ["UND9001,CUST9001,500,ANY"],
            ["2026-04-04 closed"],
            ["WIRE,true,1"],
            [],
            ["WIRE,2026-01-01,2026-12-31,ACTIVE"],
            dated=False,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["channel"] == "WIRE"
        assert summary["matched_amount_cents"] == 500

    def test_single_date_column_activates_dated_mode(self):
        """A due_date column alone activates date validation instead of undated fallback."""
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        LEASES.write_text(
            "lease_id,customer_id,amount_cents,status,channel,due_date\n"
            "ONE9001,CUST9001,500,POSTED,WIRE,2026-04-10\n"
        )
        DEPOSITS.write_text(
            "lease_id,customer_id,amount_cents,channel\n"
            "ONE9001,CUST9001,500,WIRE\n"
        )
        CALENDAR.write_text("2026-04-04 open\n")
        METHODS.write_text("channel,enabled,priority\nWIRE,true,1\n")
        LIMITS.write_text(
            "customer_id,channel,effective_date,max_daily_amount,status\n"
            "CUST9001,WIRE,2026-04-01,1000,ACTIVE\n"
        )
        BLACKOUTS.write_text("channel,start_date,end_date,state\n")
        REPORT.unlink(missing_ok=True)
        SUMMARY.unlink(missing_ok=True)

        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["unmatched_amount_cents"] == 500

    def test_deposit_date_column_alone_activates_dated_mode(self):
        """A deposit_date column alone activates date validation instead of undated fallback."""
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        LEASES.write_text(
            "lease_id,customer_id,amount_cents,status,channel\n"
            "ONE9002,CUST9002,600,POSTED,CARD\n"
        )
        DEPOSITS.write_text(
            "lease_id,customer_id,amount_cents,channel,deposit_date\n"
            "ONE9002,CUST9002,600,CARD,2026-04-04\n"
        )
        CALENDAR.write_text("2026-04-04 open\n")
        METHODS.write_text("channel,enabled,priority\nCARD,true,1\n")
        LIMITS.write_text(
            "customer_id,channel,effective_date,max_daily_amount,status\n"
            "CUST9002,CARD,2026-04-01,1000,ACTIVE\n"
        )
        BLACKOUTS.write_text("channel,start_date,end_date,state\n")
        REPORT.unlink(missing_ok=True)
        SUMMARY.unlink(missing_ok=True)

        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["unmatched_amount_cents"] == 600

    def test_unmatched_any_never_leaks_wildcard_channel(self):
        """An unmatched ANY deposit must emit a blank channel rather than the wildcard token."""
        write_inputs(
            ["ANYNONE,CUSTNONE,700,POSTED,WIRE,2026-04-10"],
            ["ANYNONE,CUSTNONE,700,ANY,2026-04-04"],
            ["2026-04-04 open"],
            ["WIRE,false,1"],
            ["CUSTNONE,WIRE,2026-04-01,1000,ACTIVE"],
        )

        rows, summary = run_program()

        assert rows[0] == {
            "lease_id": "ANYNONE",
            "customer_id": "CUSTNONE",
            "channel": "",
            "amount_cents": "700",
            "status": "UNMATCHED",
        }
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_any_skips_disabled_high_priority_channel_for_next_enabled_candidate(self):
        """ANY deposits should ignore disabled high-priority channels and match the next eligible candidate."""
        write_inputs(
            [
                "ANYD100,CUSTD100,600,POSTED,CARD,2026-04-09",
                "ANYD100,CUSTD100,600,POSTED,ACH,2026-04-09",
            ],
            ["ANYD100,CUSTD100,600,ANY,2026-04-04"],
            ["2026-04-04 open"],
            ["CARD,false,1", "ACH,true,2"],
            ["CUSTD100,ACH,2026-04-01,1000,ACTIVE"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["channel"] == "ACH"
        assert summary["matched_amount_cents"] == 600

    def test_undated_any_ranks_by_priority_then_row_order(self):
        """Undated ANY deposits should use method priority before lease row order."""
        write_inputs(
            [
                "UND101,CUST101,500,POSTED,WIRE",
                "UND101,CUST101,500,POSTED,CARD",
                "UND101,CUST101,500,POSTED,ACH",
            ],
            ["UND101,CUST101,500,ANY"],
            ["2026-04-04 closed"],
            ["WIRE,true,5", "CARD,true,1", "ACH,true,1"],
            dated=False,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["channel"] == "CARD"
        assert summary["matched_count"] == 1

    def test_customer_limit_resets_per_deposit_date(self):
        """Customer daily limits should be independent for each deposit date."""
        write_inputs(
            [
                "CAPD01,CUSTD01,800,POSTED,CARD,2026-04-10",
                "CAPD01,CUSTD01,800,POSTED,CARD,2026-04-11",
            ],
            [
                "CAPD01,CUSTD01,800,CARD,2026-04-04",
                "CAPD01,CUSTD01,800,CARD,2026-04-05",
            ],
            ["2026-04-04 open", "2026-04-05 open"],
            ["CARD,true,1"],
            ["CUSTD01,CARD,2026-04-01,1000,ACTIVE"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert summary["matched_amount_cents"] == 1600
        assert summary["unmatched_count"] == 0

    def test_future_effective_limit_is_excluded_from_limit_selection(self):
        """Limit rows with effective_date after the deposit date should not be considered."""
        write_inputs(
            ["FUTLIM,CUSTFUT,500,POSTED,CARD,2026-04-10"],
            ["FUTLIM,CUSTFUT,500,CARD,2026-04-04"],
            ["2026-04-04 open"],
            ["CARD,true,1"],
            [
                "CUSTFUT,CARD,2026-04-05,0,ACTIVE",
                "CUSTFUT,CARD,2026-04-03,1000,ACTIVE",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["channel"] == "CARD"
        assert summary["matched_amount_cents"] == 500
