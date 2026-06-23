"""Verifier tests for package policy and ANY refunds in the Ruby photography CLI."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "sessions.csv"
ACTIONS = APP / "data" / "refunds.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
METHODS = APP / "config" / "methods.csv"
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


def run_program():
    """Run the Ruby batch and return parsed report and summary outputs."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone3RegressionFromPriorMilestone:
    """Intentional M3 regression copy: date gates, audit row output, aliases, and consumption."""

    def test_open_action_date_and_latest_due_date_win(self):
        write_methods(["MINI,true,2", "STANDARD,true,1", "PREMIUM,true,3"])
        write_inputs(
            [
                "DATE9001,CUST9001,1000,SHOT,MINI,2026-04-03",
                "DATE9001,CUST9001,1000,SHOT,STANDARD,2026-04-08",
                "DATE9002,CUST9002,2000,SHOT,STANDARD,2026-04-02",
            ],
            [
                "DATE9001,CUST9001,1000,STD,2026-04-02",
                "DATE9002,CUST9002,2000,STD,2026-04-04",
            ],
            ["2026-04-02 open", "2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[0]["package"] == "STANDARD"
        assert rows[0]["matched_session_row"] == "2"
        assert summary["matched_amount_cents"] == 1000
        assert summary["unmatched_amount_cents"] == 2000

    def test_same_due_date_tie_uses_source_order_and_consumption_is_audited(self):
        write_methods(["MINI,true,1", "STANDARD,true,2", "PREMIUM,true,3"])
        write_inputs(
            [
                "DATE9201,CUST9201,500,SHOT,MINI,2026-04-05",
                "DATE9201,CUST9201,500,SHOT,MINI,2026-04-05",
            ],
            [
                "DATE9201,CUST9201,500,MIN,2026-04-04",
                "DATE9201,CUST9201,500,MIN,2026-04-04",
                "DATE9201,CUST9201,500,MIN,2026-04-04",
            ],
            ["2026-04-04 open", "2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["matched_session_row"] for row in rows] == ["1", "2", ""]
        assert summary["matched_count"] == 2


class TestMilestone4:
    """Verify methods.csv package policy, ANY matching, priority fallback, and regression gates."""

    def test_disabled_configured_package_rejects_otherwise_valid_refund(self):
        """Disabled methods.csv packages must not match even with valid ids, dates, and aliases."""
        write_methods(["MINI,true,2", "STANDARD,false,1", "PREMIUM,true,3"])
        write_inputs(
            ["CFG1001,CUST1001,1200,SHOT,STANDARD,2026-04-10"],
            ["CFG1001,CUST1001,1200,STD,2026-04-05"],
            ["2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["package"] == ""
        assert rows[0]["matched_session_row"] == ""
        assert summary == {"matched_count": 0, "matched_amount_cents": 0, "unmatched_count": 1, "unmatched_amount_cents": 1200}

    def test_enabled_flag_case_and_trim_normalization(self):
        """Enabled=true should be parsed after trimming and case normalization."""
        write_methods(["MINI, True ,1", "STANDARD, FALSE ,2", "PREMIUM,true,3"])
        write_inputs(
            [
                "CFG8801,CUST8801,300,SHOT,MINI,2026-04-10",
                "CFG8802,CUST8802,300,SHOT,STANDARD,2026-04-10",
            ],
            [
                "CFG8801,CUST8801,300,MIN,2026-04-05",
                "CFG8802,CUST8802,300,STD,2026-04-05",
            ],
            ["2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[0]["package"] == "MINI"
        assert summary == {"matched_count": 1, "matched_amount_cents": 300, "unmatched_count": 1, "unmatched_amount_cents": 300}

    def test_any_picks_latest_session_date_over_priority(self):
        """ANY selection must apply latest session_date before lower package priority."""
        write_methods(["MINI,true,1", "STANDARD,true,2", "PREMIUM,true,3"])
        write_inputs(
            [
                "ANY8001,CUST8001,500,SHOT,MINI,2026-04-05",
                "ANY8001,CUST8001,500,SHOT,STANDARD,2026-04-09",
            ],
            ["ANY8001,CUST8001,500,ANY,2026-04-04"],
            ["2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["package"] == "STANDARD"
        assert rows[0]["matched_session_row"] == "2"
        assert summary["matched_count"] == 1

    def test_any_same_date_uses_config_priority_before_source_order(self):
        """ANY ties on session date should use configured priority before source row order."""
        write_methods(["MINI,true,5", "STANDARD,true,1", "PREMIUM,true,3"])
        write_inputs(
            [
                "ANY2001,CUST2001,700,SHOT,MINI,2026-04-08",
                "ANY2001,CUST2001,700,SHOT,PREMIUM,2026-04-08",
                "ANY2001,CUST2001,700,SHOT,STANDARD,2026-04-08",
            ],
            ["ANY2001,CUST2001,700,ANY,2026-04-04"],
            ["2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["package"] == "STANDARD"
        assert rows[0]["matched_session_row"] == "3"
        assert summary["matched_count"] == 1

    def test_methods_without_priority_column_falls_to_source_order(self):
        """When priority column is absent, enabled packages tie and source row order decides."""
        write_methods(["STANDARD,true", "MINI,true"], include_priority=False)
        write_inputs(
            [
                "ANY9001,CUST9001,400,SHOT,MINI,2026-04-09",
                "ANY9001,CUST9001,400,SHOT,STANDARD,2026-04-09",
            ],
            ["ANY9001,CUST9001,400,ANY,2026-04-04"],
            ["2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["package"] == "MINI"
        assert rows[0]["matched_session_row"] == "1"
        assert summary["matched_amount_cents"] == 400

    def test_any_equal_priority_tie_uses_earliest_visible_source_row(self):
        """ANY ties on date and priority should visibly choose the earliest source row."""
        write_methods(["MINI,true,1", "STANDARD,true,1", "PREMIUM,true,9"])
        write_inputs(
            [
                "ANY3001,CUST3001,800,SHOT,MINI,2026-04-09",
                "ANY3001,CUST3001,800,SHOT,STANDARD,2026-04-09",
            ],
            ["ANY3001,CUST3001,800,ANY,2026-04-04"],
            ["2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["package"] == "MINI"
        assert rows[0]["matched_session_row"] == "1"
        assert summary["matched_amount_cents"] == 800

    def test_any_consumes_selected_row_and_next_refund_uses_next_best_candidate(self):
        """ANY matching should consume by row position and rerank remaining candidates."""
        write_methods(["MINI,true,1", "STANDARD,true,2", "PREMIUM,true,3"])
        write_inputs(
            [
                "ANY4001,CUST4001,500,SHOT,MINI,2026-04-07",
                "ANY4001,CUST4001,500,SHOT,STANDARD,2026-04-07",
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
        assert [row["package"] for row in rows] == ["MINI", "STANDARD", ""]
        assert [row["matched_session_row"] for row in rows] == ["1", "2", ""]
        assert summary == {"matched_count": 2, "matched_amount_cents": 1000, "unmatched_count": 1, "unmatched_amount_cents": 500}

    def test_non_any_still_requires_exact_canonical_package_under_config_policy(self):
        """Config policy must not turn named package refunds into wildcard matches."""
        write_methods(["MINI,true,1", "STANDARD,true,2", "PREMIUM,true,3"])
        write_inputs(
            ["CFG5001,CUST5001,900,SHOT,MINI,2026-04-10"],
            ["CFG5001,CUST5001,900,STD,2026-04-05"],
            ["2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["package"] == ""
        assert summary["unmatched_amount_cents"] == 900

    def test_malformed_priority_ranks_after_numeric_priorities(self):
        """Malformed priority values should rank after configured numeric priorities."""
        write_methods(["MINI,true,fast", "STANDARD,true,1", "PREMIUM,true,3"])
        write_inputs(
            [
                "ANY6001,CUST6001,640,SHOT,MINI,2026-04-09",
                "ANY6001,CUST6001,640,SHOT,STANDARD,2026-04-09",
            ],
            ["ANY6001,CUST6001,640,ANY,2026-04-04"],
            ["2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["package"] == "STANDARD"
        assert summary["matched_count"] == 1

    def test_old_schema_without_dates_honors_disabled_package_policy(self):
        """Undated CSVs should still honor methods.csv enabled flags."""
        write_methods(["MINI,true,1", "STANDARD,false,2", "PREMIUM,true,3"])
        write_inputs(
            ["OLD9701,CUST9701,450,SHOT,STANDARD"],
            ["OLD9701,CUST9701,450,STD"],
            dated=False,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["unmatched_amount_cents"] == 450

    def test_any_with_closed_refund_date_is_ineligible(self):
        """ANY must still respect open refund_date gates together with package policy."""
        write_methods(["MINI,true,1", "STANDARD,true,2", "PREMIUM,true,3"])
        write_inputs(
            [
                "ANY7001,CUST7001,550,SHOT,MINI,2026-04-10",
                "ANY7001,CUST7001,550,SHOT,STANDARD,2026-04-10",
            ],
            ["ANY7001,CUST7001,550,ANY,2026-04-05"],
            ["2026-04-05 closed"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0
