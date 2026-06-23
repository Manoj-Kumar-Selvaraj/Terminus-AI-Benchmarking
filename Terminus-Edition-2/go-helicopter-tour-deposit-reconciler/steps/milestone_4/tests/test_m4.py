"""Milestone 4 tests for policy-aware tour deposit reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
SOURCE_FILE = APP / "data" / "tours.csv"
ACTION_FILE = APP / "data" / "deposits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
FLEET_POLICY = APP / "config" / "fleet_policy.csv"
PASSENGER_LIMITS = APP / "config" / "passenger_limits.csv"
WEATHER_BLACKOUTS = APP / "config" / "weather_blackouts.csv"
REPORT = APP / "out" / "tour_deposit_report.csv"
SUMMARY = APP / "out" / "tour_deposit_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 4 tests."""
    build_program()


def write_inputs(tour_rows, deposit_rows, calendar_rows, policy_rows, limit_rows, blackout_rows):
    """Replace all input and policy files for one policy-aware scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_FILE.write_text("tour_id,passenger_id,amount_cents,status,cabin_tier,tour_date\n" + "\n".join(tour_rows) + "\n")
    ACTION_FILE.write_text(
        "tour_id,passenger_id,amount_cents,cabin_tier,deposit_date\n" + "\n".join(deposit_rows) + "\n"
    )
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    FLEET_POLICY.write_text("cabin_tier,enabled,priority\n" + "\n".join(policy_rows) + "\n")
    PASSENGER_LIMITS.write_text(
        "passenger_id,effective_date,max_daily_amount_cents\n" + "\n".join(limit_rows) + "\n"
    )
    WEATHER_BLACKOUTS.write_text("tour_id,start_date,end_date\n" + "\n".join(blackout_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_legacy_inputs(tour_rows, deposit_rows, policy_rows):
    """Pre-date schema should skip M4 date-only policy gates but still use enabled cabin tiers."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_FILE.write_text("tour_id,passenger_id,amount_cents,status,cabin_tier\n" + "\n".join(tour_rows) + "\n")
    ACTION_FILE.write_text("tour_id,passenger_id,amount_cents,cabin_tier\n" + "\n".join(deposit_rows) + "\n")
    FLEET_POLICY.write_text("cabin_tier,enabled,priority\n" + "\n".join(policy_rows) + "\n")
    PASSENGER_LIMITS.write_text("passenger_id,effective_date,max_daily_amount_cents\n")
    WEATHER_BLACKOUTS.write_text("tour_id,start_date,end_date\n")
    CALENDAR.write_text("")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse report and summary artifacts."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone4:
    """Policy gates, ANY matching, daily caps, and blackout checks."""

    def test_disabled_cabin_tier_rejects_otherwise_valid_deposit(self):
        """A disabled canonical cabin_tier cannot match even when every prior gate passes."""
        write_inputs(
            ["HEL4001,CUST4001,800,COMPLETED,LUX,2026-04-10"],
            ["HEL4001,CUST4001,800,LX,2026-04-04"],
            ["2026-04-04 open"],
            ["STD,true,30", "PREM,true,20", "LUX,false,10"],
            ["CUST4001,2026-04-01,2000"],
            [],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["cabin_tier"] == ""
        assert summary["unmatched_amount_cents"] == 800

    def test_any_wildcard_uses_latest_tour_date_before_fleet_priority(self):
        """ANY should first prefer the latest eligible tour_date, not the best cabin priority."""
        write_inputs(
            [
                "HEL4101,CUST4101,900,COMPLETED,LUX,2026-04-08",
                "HEL4101,CUST4101,900,COMPLETED,STD,2026-04-11",
            ],
            ["HEL4101,CUST4101,900,ANY,2026-04-05"],
            ["2026-04-05 open"],
            ["STD,true,30", "PREM,true,20", "LUX,true,10"],
            ["CUST4101,2026-04-01,2000"],
            [],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["cabin_tier"] == "STD"
        assert summary["matched_amount_cents"] == 900

    def test_any_same_tour_date_uses_priority_then_source_row_order(self):
        """When dates tie, ANY chooses smaller policy priority, then earliest source row."""
        write_inputs(
            [
                "HEL4201,CUST4201,700,COMPLETED,STD,2026-04-10",
                "HEL4201,CUST4201,700,COMPLETED,LUX,2026-04-10",
                "HEL4201,CUST4201,700,COMPLETED,LUX,2026-04-10",
            ],
            [
                "HEL4201,CUST4201,700,ANY,2026-04-05",
                "HEL4201,CUST4201,700,ANY,2026-04-05",
            ],
            ["2026-04-05 open"],
            ["STD,true,30", "PREM,true,20", "LUX,true,10"],
            ["CUST4201,2026-04-01,2000"],
            [],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["cabin_tier"] for row in rows] == ["LUX", "LUX"]
        assert summary["matched_count"] == 2

    def test_malformed_priorities_sort_after_numeric_priorities(self):
        """Enabled tiers with malformed priorities remain enabled but lose priority tie-breaks."""
        write_inputs(
            [
                "HEL4251,CUST4251,600,COMPLETED,PREM,2026-04-09",
                "HEL4251,CUST4251,600,COMPLETED,LUX,2026-04-09",
            ],
            ["HEL4251,CUST4251,600,ANY,2026-04-04"],
            ["2026-04-04 open"],
            ["PREM,true,20", "LUX,true,not-a-number"],
            ["CUST4251,2026-04-01,2000"],
            [],
        )
        rows, _ = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["cabin_tier"] == "PREM"

    def test_malformed_fleet_policy_row_is_ignored(self):
        """Blank or malformed fleet-policy rows must not disable otherwise enabled tiers."""
        write_inputs(
            ["HEL4801,CUST4801,500,COMPLETED,STD,2026-04-10"],
            ["HEL4801,CUST4801,500,ST,2026-04-05"],
            ["2026-04-05 open"],
            [",true,10", "STD,true,30", "PREM,true,20"],
            ["CUST4801,2026-04-01,1000"],
            [],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["cabin_tier"] == "STD"
        assert summary["matched_count"] == 1

    def test_fleet_policy_normalizes_alias_case_trim_and_enabled_case(self):
        """Policy cabin_tier aliases and mixed-case enabled=true values must be normalized."""
        write_inputs(
            [
                "HEL4821,CUST4821,500,COMPLETED,STD,2026-04-10",
                "HEL4821,CUST4821,500,COMPLETED,LUX,2026-04-10",
            ],
            [
                "HEL4821,CUST4821,500,ST,2026-04-05",
                "HEL4821,CUST4821,500,LX,2026-04-05",
            ],
            ["2026-04-05 open"],
            [" st ,TrUe,30", " lx ,FALSE,10"],
            ["CUST4821,2026-04-01,2000"],
            [],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["cabin_tier"] for row in rows] == ["STD", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 500,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_passenger_daily_limit_caps_matches_in_deposit_order(self):
        """Daily caps apply by passenger and deposit_date without consuming rejected tours."""
        write_inputs(
            [
                "HEL4301,CUST4301,700,COMPLETED,STD,2026-04-10",
                "HEL4302,CUST4301,600,COMPLETED,PREM,2026-04-10",
                "HEL4303,CUST4301,400,COMPLETED,LUX,2026-04-10",
            ],
            [
                "HEL4301,CUST4301,700,STD,2026-04-05",
                "HEL4302,CUST4301,600,PM,2026-04-05",
                "HEL4303,CUST4301,400,LX,2026-04-05",
            ],
            ["2026-04-05 open"],
            ["STD,true,30", "PREM,true,20", "LUX,true,10"],
            ["CUST4301,2026-04-01,1100"],
            [],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["cabin_tier"] for row in rows] == ["STD", "", "LUX"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1100,
            "unmatched_count": 1,
            "unmatched_amount_cents": 600,
        }

    def test_latest_effective_limit_wins_and_same_date_uses_later_limit_row(self):
        """Limit rows choose latest effective_date, then later row on the same date."""
        write_inputs(
            [
                "HEL4351,CUST4351,1000,COMPLETED,STD,2026-04-10",
                "HEL4352,CUST4351,800,COMPLETED,PREM,2026-04-10",
            ],
            [
                "HEL4351,CUST4351,1000,STD,2026-04-06",
                "HEL4352,CUST4351,800,PM,2026-04-06",
            ],
            ["2026-04-06 open"],
            ["STD,true,30", "PREM,true,20"],
            [
                "CUST4351,2026-04-01,1000",
                "CUST4351,2026-04-05,1200",
                "CUST4351,2026-04-05,2000",
            ],
            [],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert summary["matched_amount_cents"] == 1800

    def test_missing_applicable_passenger_limit_blocks_dated_match(self):
        """Dated deposits require an applicable numeric passenger limit."""
        write_inputs(
            ["HEL4401,CUST4401,500,COMPLETED,STD,2026-04-10"],
            ["HEL4401,CUST4401,500,STD,2026-04-05"],
            ["2026-04-05 open"],
            ["STD,true,30"],
            ["CUST-OTHER,2026-04-01,9999", "CUST4401,2026-04-06,9999"],
            [],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_weather_blackout_blocks_exact_tour_id_and_date_range(self):
        """A blackout row blocks matching only for the exact tour_id and inclusive date range."""
        write_inputs(
            [
                "HEL4501,CUST4501,500,COMPLETED,PREM,2026-04-10",
                "HEL4502,CUST4502,500,COMPLETED,PREM,2026-04-10",
            ],
            [
                "HEL4501,CUST4501,500,PM,2026-04-05",
                "HEL4502,CUST4502,500,PM,2026-04-05",
            ],
            ["2026-04-05 open"],
            ["PREM,true,20"],
            ["CUST4501,2026-04-01,1000", "CUST4502,2026-04-01,1000"],
            ["HEL4501,2026-04-09,2026-04-10"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert summary["matched_amount_cents"] == 500

    def test_invalid_blackout_range_is_ignored(self):
        """A blackout with start_date after end_date must not block the source."""
        write_inputs(
            ["HEL4551,CUST4551,500,COMPLETED,LUX,2026-04-10"],
            ["HEL4551,CUST4551,500,LX,2026-04-05"],
            ["2026-04-05 open"],
            ["LUX,true,10"],
            ["CUST4551,2026-04-01,1000"],
            ["HEL4551,2026-04-11,2026-04-10"],
        )
        rows, _ = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["cabin_tier"] == "LUX"

    def test_any_skips_blacked_out_best_candidate(self):
        """ANY should ignore a blacked-out best candidate and choose the next eligible source."""
        write_inputs(
            [
                "HEL4601,CUST4601,700,COMPLETED,LUX,2026-04-12",
                "HEL4601,CUST4601,700,COMPLETED,PREM,2026-04-11",
            ],
            ["HEL4601,CUST4601,700,ANY,2026-04-05"],
            ["2026-04-05 open"],
            ["PREM,true,20", "LUX,true,10"],
            ["CUST4601,2026-04-01,1000"],
            ["HEL4601,2026-04-12,2026-04-12"],
        )
        rows, _ = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["cabin_tier"] == "PREM"

    def test_legacy_undated_any_uses_enabled_fleet_policy(self):
        """Undated ANY deposits should match enabled cabin tiers and still reject disabled tiers."""
        write_legacy_inputs(
            [
                "HEL4651,CUST4651,750,COMPLETED,LUX",
                "HEL4651,CUST4651,750,COMPLETED,PREM",
                "HEL4652,CUST4652,500,COMPLETED,LUX",
                "HEL4653,CUST4653,400,COMPLETED,STD",
            ],
            [
                "HEL4651,CUST4651,750,ANY",
                "HEL4652,CUST4652,500,ANY",
                "HEL4653,CUST4653,400,ST",
            ],
            ["STD,true,30", "PREM,true,20", "LUX,false,10"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["cabin_tier"] for row in rows] == ["PREM", "", "STD"]
        assert [row["tour_id"] for row in rows] == ["HEL4651", "HEL4652", "HEL4653"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1150,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_legacy_undated_inputs_skip_limits_and_blackouts_but_keep_fleet_policy(self):
        """Undated input keeps prior matching and enabled-tier checks, without daily caps or blackouts."""
        write_legacy_inputs(
            [
                "HEL4701,CUST4701,900,COMPLETED,STD",
                "HEL4702,CUST4702,900,COMPLETED,LUX",
            ],
            [
                "HEL4701,CUST4701,900,ST",
                "HEL4702,CUST4702,900,LX",
            ],
            ["STD,true,30", "LUX,false,10"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["cabin_tier"] for row in rows] == ["STD", ""]
        assert summary["matched_amount_cents"] == 900
