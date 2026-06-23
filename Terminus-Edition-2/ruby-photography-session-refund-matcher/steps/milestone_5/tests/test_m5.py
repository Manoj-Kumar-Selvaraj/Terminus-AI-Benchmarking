"""Verifier tests for client-specific refund limits in the Ruby photography CLI."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "sessions.csv"
ACTIONS = APP / "data" / "refunds.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
METHODS = APP / "config" / "methods.csv"
LIMITS = APP / "config" / "client_limits.csv"
REPORT = APP / "out" / "refund_report.csv"
SUMMARY = APP / "out" / "refund_summary.json"


def write_inputs(source_rows, action_rows, calendar_rows=None, dated=False):
    """Replace session, refund, and optional calendar inputs for one scenario."""
    source_header = "session_id,client_id,amount_cents,status,package" + (",session_date" if dated else "")
    action_header = "session_id,client_id,amount_cents,package" + (",refund_date" if dated else "")
    SOURCE.write_text(source_header + "\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text(action_header + "\n" + "\n".join(action_rows) + "\n")
    if calendar_rows is not None:
        CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_methods(rows, include_priority=True):
    """Replace methods.csv with optional priority column coverage."""
    header = "package,enabled,priority" if include_priority else "package,enabled"
    METHODS.write_text(header + "\n" + "\n".join(rows) + "\n")


def write_limits(rows):
    """Replace client_limits.csv with the required milestone 5 schema."""
    LIMITS.write_text("client_id,package,max_refund_cents,enabled\n" + "\n".join(rows) + "\n")


def run_program():
    """Run the Ruby batch and return parsed report and summary outputs."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone5:
    """Verify client_limits.csv gates, last-row authority, ANY filtering, and prior regressions."""

    def test_limit_allows_under_cap_for_dated_any_after_methods(self):
        """ANY should match only after methods and client-limit gates both allow the selected package."""
        write_methods(["MINI,true,1", "STANDARD,true,2", "PREMIUM,true,3"])
        write_limits(["CUST5101,MINI,1000,true", "CUST5101,STANDARD,1000,true"])
        write_inputs(
            [
                "LIM5101,CUST5101,700,SHOT,MINI,2026-04-08",
                "LIM5101,CUST5101,700,SHOT,STANDARD,2026-04-10",
            ],
            ["LIM5101,CUST5101,700,ANY,2026-04-05"],
            ["2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert list(rows[0].keys()) == ["session_id", "client_id", "package", "amount_cents", "matched_session_row", "status"]
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["package"] == "STANDARD"
        assert rows[0]["matched_session_row"] == "2"
        assert summary == {"matched_count": 1, "matched_amount_cents": 700, "unmatched_count": 0, "unmatched_amount_cents": 0}

    def test_any_filters_out_over_limit_candidate_before_ranking_next_best(self):
        """A higher-ranked ANY candidate over the client limit should be skipped before tie-break ranking."""
        write_methods(["MINI,true,1", "STANDARD,true,2", "PREMIUM,true,3"])
        write_limits(["CUST5201,MINI,100,true", "CUST5201,STANDARD,900,true"])
        write_inputs(
            [
                "LIM5201,CUST5201,800,SHOT,MINI,2026-04-09",
                "LIM5201,CUST5201,800,SHOT,STANDARD,2026-04-09",
            ],
            ["LIM5201,CUST5201,800,ANY,2026-04-05"],
            ["2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["package"] == "STANDARD"
        assert rows[0]["matched_session_row"] == "2"
        assert summary["matched_amount_cents"] == 800

    def test_missing_disabled_over_limit_and_invalid_limit_rows_are_ineligible(self):
        """Missing, disabled, over-cap, non-integer, and negative limit rows should reject safely."""
        write_methods(["MINI,true,1", "STANDARD,true,2", "PREMIUM,true,3"])
        write_limits([
            "CUST5301,MINI,100,false",
            "CUST5302,STANDARD,50,true",
            "CUST5303,PREMIUM,abc,true",
            "CUST5304,MINI,-1,true",
        ])
        write_inputs(
            [
                "LIM5301,CUST5301,80,SHOT,MINI",
                "LIM5302,CUST5302,80,SHOT,STANDARD",
                "LIM5303,CUST5303,80,SHOT,PREMIUM",
                "LIM5304,CUST5304,80,SHOT,MINI",
                "LIM5305,CUST5305,80,SHOT,MINI",
            ],
            [
                "LIM5301,CUST5301,80,MINI",
                "LIM5302,CUST5302,80,STD",
                "LIM5303,CUST5303,80,PRM",
                "LIM5304,CUST5304,80,MIN",
                "LIM5305,CUST5305,80,MINI",
            ],
            dated=False,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED"] * 5
        assert summary == {"matched_count": 0, "matched_amount_cents": 0, "unmatched_count": 5, "unmatched_amount_cents": 400}

    def test_limit_parser_trims_client_id_and_case_normalizes_enabled_and_alias(self):
        """Limit rows should trim client_id, normalize package aliases, and parse TRUE after trimming."""
        write_methods(["MINI,true,1", "STANDARD,true,2", "PREMIUM,true,3"])
        write_limits([" CUST5401 , std , 900 , TRUE "])
        write_inputs(
            ["LIM5401,CUST5401,900,SHOT,STANDARD"],
            ["LIM5401,CUST5401,900,STD"],
            dated=False,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["package"] == "STANDARD"
        assert rows[0]["matched_session_row"] == "1"
        assert summary["matched_amount_cents"] == 900

    def test_last_limit_row_is_authoritative_even_when_it_disables_earlier_allowance(self):
        """The last row for a client/package should override earlier enabled rows."""
        write_methods(["MINI,true,1", "STANDARD,true,2", "PREMIUM,true,3"])
        write_limits(["CUST5501,MINI,1000,true", "CUST5501,MIN,1000,false"])
        write_inputs(
            ["LIM5501,CUST5501,700,SHOT,MINI"],
            ["LIM5501,CUST5501,700,MIN"],
            dated=False,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["package"] == ""
        assert summary["unmatched_amount_cents"] == 700

    def test_later_invalid_limit_row_overrides_and_makes_pair_ineligible(self):
        """A later invalid max for the same client/package should be authoritative and reject."""
        write_methods(["MINI,true,1", "STANDARD,true,2", "PREMIUM,true,3"])
        write_limits(["CUST5601,PREMIUM,2000,true", "CUST5601,PRM,not_int,true"])
        write_inputs(
            ["LIM5601,CUST5601,1200,SHOT,PREMIUM,2026-04-09"],
            ["LIM5601,CUST5601,1200,PRM,2026-04-05"],
            ["2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["matched_session_row"] == ""
        assert summary["matched_count"] == 0

    def test_client_limits_apply_after_disabled_methods_policy(self):
        """Client limits must not bypass a disabled methods.csv package."""
        write_methods(["MINI,true,1", "STANDARD,false,2", "PREMIUM,true,3"])
        write_limits(["CUST5701,STANDARD,5000,true"])
        write_inputs(
            ["LIM5701,CUST5701,600,SHOT,STANDARD"],
            ["LIM5701,CUST5701,600,STD"],
            dated=False,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary == {"matched_count": 0, "matched_amount_cents": 0, "unmatched_count": 1, "unmatched_amount_cents": 600}

    def test_regression_full_matching_and_date_rules_still_apply_with_limits(self):
        """Limits should not bypass exact client ids, package equality, dates, or consumption."""
        write_methods(["MINI,true,1", "STANDARD,true,2", "PREMIUM,true,3"])
        write_limits(["CUST5801,MINI,1000,true", "CUST5802,STANDARD,1000,true"])
        write_inputs(
            [
                "LIM5801,CUST5801,500,SHOT,MINI,2026-04-06",
                "LIM5801,CUST5801,500,SHOT,MINI,2026-04-10",
                "LIM5802,CUST5802,500,SHOT,MINI,2026-04-10",
            ],
            [
                "LIM5801,CUST5801X,500,MIN,2026-04-05",
                "LIM5801,CUST5801,500,MIN,2026-04-11",
                "LIM5801,CUST5801,500,MIN,2026-04-05",
                "LIM5801,CUST5801,500,MIN,2026-04-05",
                "LIM5802,CUST5802,500,STD,2026-04-05",
            ],
            ["2026-04-05 open", "2026-04-11 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["matched_session_row"] for row in rows] == ["", "", "2", "1", ""]
        assert summary == {"matched_count": 2, "matched_amount_cents": 1000, "unmatched_count": 3, "unmatched_amount_cents": 1500}
