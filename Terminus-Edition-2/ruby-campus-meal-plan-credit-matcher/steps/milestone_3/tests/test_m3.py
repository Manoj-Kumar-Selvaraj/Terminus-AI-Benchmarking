
"""Verifier tests for the Ruby campus reconciliation CLI."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "plans.csv"
ACTIONS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"
CONSUMPTION = APP / "out" / "plan_consumption.csv"


def write_inputs(source_rows, action_rows, calendar_rows=None, dated=False):
    """Replace CSV inputs and optional calendar with a focused scenario."""
    source_header = "plan_id,student_id,amount_cents,status,location" + (",cycle_end" if dated else "")
    action_header = "plan_id,student_id,amount_cents,location" + (",credit_date" if dated else "")
    SOURCE.write_text(source_header + "\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text(action_header + "\n" + "\n".join(action_rows) + "\n")
    if calendar_rows is not None:
        CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)
    CONSUMPTION.unlink(missing_ok=True)


def run_program():
    """Run the Ruby batch and return parsed report and summary outputs."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


def read_consumption():
    """Return the physical plan-row selections emitted for matched credits."""
    with CONSUMPTION.open(newline="") as handle:
        return list(csv.DictReader(handle))


def test_middle_value_matches_and_counts_positive_amount():
    """The middle allowed value should match and matched totals should be positive."""
    write_inputs(
        ["SRC1001,CUST1001,1200,ACTIVE,DINING", "SRC1002,CUST1002,2300,ACTIVE,CAFE"],
        ["SRC1001,CUST1001,1200,DINING", "SRC1002,CUST1002,2300,CAFE"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["location"] == "CAFE"
    assert summary["matched_amount_cents"] == 3500


def test_full_identifier_matching_rejects_prefix_collision():
    """Only full plan_id equality should match; shared prefixes are not enough."""
    write_inputs(
        ["PREFIX770001,CUST2001,3300,ACTIVE,DINING", "PREFIX770002,CUST2001,3300,ACTIVE,DINING"],
        ["PREFIX770003,CUST2001,3300,DINING", "PREFIX770002,CUST2001,3300,DINING"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["location"] == ""
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_dimension_all_gate_matching():
    """Customer, amount, status, and allowed dimension must all gate matching."""
    write_inputs(
        [
            "SRC3001,CUST3001,1000,ACTIVE,DINING",
            "SRC3002,CUST3002,2000,ACTIVE,CAFE",
            "SRC3003,CUST3003,3000,DRAFT,MARKET",
            "SRC3004,CUST3004,4000,ACTIVE,CHECK",
            "SRC3005,CUST3005,5000,ACTIVE,MARKET",
        ],
        [
            "SRC3001,CUST9999,1000,DINING",
            "SRC3002,CUST3002,2100,CAFE",
            "SRC3003,CUST3003,3000,MARKET",
            "SRC3004,CUST3004,4000,CHECK",
            "SRC3005,CUST3005,5000,MARKET",
        ],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["location"] == "MARKET"
    assert summary["matched_count"] == 1
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_actions_do_not_reuse_consumed_source_row():
    """Duplicate actions should not consume the same source row twice."""
    write_inputs(
        ["SRC4001,CUST4001,5500,ACTIVE,CAFE"],
        ["SRC4001,CUST4001,5500,CAFE", "SRC4001,CUST4001,5500,CAFE"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert summary["matched_count"] == 1
    assert summary["unmatched_count"] == 1


def test_trimming_and_case_normalization_are_applied():
    """Fields should be trimmed and status/dimension comparisons should be case-insensitive."""
    write_inputs(
        [" SRC5001 , CUST5001 , 6600 , active , cafe "],
        [" SRC5001 , CUST5001 , 6600 , CAFE "],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["location"] == "CAFE"
    assert summary["matched_amount_cents"] == 6600


def test_report_schema_order_and_blank_unmatched_dimension():
    """Report schema, action input order, and blank unmatched dimension should be stable."""
    write_inputs(
        ["SRC6002,CUST6002,1200,ACTIVE,DINING", "SRC6001,CUST6001,1100,ACTIVE,CAFE"],
        ["SRC6001,CUST6001,1100,CAFE", "NO_MATCH,CUST9999,9900,DINING", "SRC6002,CUST6002,1200,DINING"],
    )
    rows, summary = run_program()
    assert list(rows[0].keys()) == ["plan_id", "student_id", "location", "amount_cents", "status"]
    assert [row["plan_id"] for row in rows] == ["SRC6001", "NO_MATCH", "SRC6002"]
    assert rows[1]["location"] == ""
    assert summary == {"matched_count": 2, "matched_amount_cents": 2300, "unmatched_count": 1, "unmatched_amount_cents": 9900}


def test_all_legacy_aliases_match_and_emit_canonical_values():
    """Every documented legacy alias should normalize and emit canonical values."""
    write_inputs(
        [
            "ALIAS7001,CUST7001,3100,ACTIVE,DINING",
            "ALIAS7002,CUST7002,3200,ACTIVE,CAFE",
            "ALIAS7003,CUST7003,3300,ACTIVE,MARKET",
            "ALIAS7004,CUST7004,3400,ACTIVE,CHECK",
        ],
        [
            "ALIAS7001,CUST7001,3100,din",
            "ALIAS7002,CUST7002,3200,CAF",
            "ALIAS7003,CUST7003,3300,MKT",
            "ALIAS7004,CUST7004,3400,UNKNOWN",
        ],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["location"] for row in rows] == ["DINING", "CAFE", "MARKET", ""]
    assert summary["matched_amount_cents"] == 9600
    assert summary["unmatched_amount_cents"] == 3400


class TestMilestone3:
    """Date gates, latest source-date selection, aliases, and row consumption."""

    def test_undated_inputs_apply_milestone_2_matching_without_calendar_gates(self):
        """Without date columns, matching must follow milestone 2 rules and ignore the calendar."""
        write_inputs(
            [
                "UND8001,CUST8001,1000,ACTIVE,CAFE",
                "UND8002,CUST8002,2000,ACTIVE,DINING",
            ],
            [
                "UND8001,CUST8001,1000,CAF",
                "UND8002,CUST8002,2000,DIN",
            ],
            calendar_rows=["2026-04-01 closed"],
            dated=False,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["location"] for row in rows] == ["CAFE", "DINING"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 3000,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_open_action_date_and_latest_due_date_win(self):
        """Open action dates should gate matching and latest eligible due date should win."""
        write_inputs(
            [
                "DATE9001,CUST9001,1000,ACTIVE,DINING,2026-04-03",
                "DATE9001,CUST9001,1000,ACTIVE,CAFE,2026-04-08",
                "DATE9002,CUST9002,2000,ACTIVE,CAFE,2026-04-02",
            ],
            [
                "DATE9001,CUST9001,1000,CAF,2026-04-02",
                "DATE9002,CUST9002,2000,CAF,2026-04-04",
            ],
            ["2026-04-02 open", "2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[0]["location"] == "CAFE"
        assert summary["matched_amount_cents"] == 1000
        assert summary["unmatched_amount_cents"] == 2000

    def test_latest_cycle_end_wins_even_when_latest_row_appears_later(self):
        """The latest cycle_end must win even when an older candidate appears first."""
        write_inputs(
            [
                "DATE9101,CUST9101,850,ACTIVE,CAFE,2026-04-05",
                "DATE9101,CUST9101,850,ACTIVE,CAFE,2026-04-08",
            ],
            ["DATE9101,CUST9101,850,CAF,2026-04-04"],
            ["2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["location"] == "CAFE"
        assert summary["matched_count"] == 1
        assert read_consumption() == [{"credit_row": "0", "plan_row": "1", "cycle_end": "2026-04-08"}]

    def test_latest_cycle_end_wins_before_older_plan_row_is_used(self):
        """Latest cycle_end must win even when an older plan row appears first in the file."""
        write_inputs(
            [
                "DATE9151,CUST9151,800,ACTIVE,CAFE,2026-04-05",
                "DATE9151,CUST9151,800,ACTIVE,CAFE,2026-04-08",
            ],
            [
                "DATE9151,CUST9151,800,CAF,2026-04-04",
                "DATE9151,CUST9151,800,CAF,2026-04-06",
            ],
            ["2026-04-04 open", "2026-04-06 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[0]["location"] == "CAFE"
        assert rows[1]["location"] == ""
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }
        assert read_consumption() == [{"credit_row": "0", "plan_row": "1", "cycle_end": "2026-04-08"}]

    def test_latest_cycle_end_wins_among_same_location_rows_and_preserves_consumption(self):
        """Among same-location rows, latest cycle_end wins and each row is consumed once."""
        write_inputs(
            [
                "LAT9001,CUST9001,500,ACTIVE,CAFE,2026-04-05",
                "LAT9001,CUST9001,500,ACTIVE,CAFE,2026-04-08",
                "LAT9001,CUST9001,500,ACTIVE,CAFE,2026-04-06",
            ],
            [
                "LAT9001,CUST9001,500,CAF,2026-04-04",
                "LAT9001,CUST9001,500,CAF,2026-04-04",
                "LAT9001,CUST9001,500,CAF,2026-04-04",
            ],
            ["2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert summary["matched_count"] == 3
        assert summary["unmatched_count"] == 0
        assert [row["plan_row"] for row in read_consumption()] == ["1", "2", "0"]

    def test_same_cycle_end_tie_break_uses_earliest_plan_row(self):
        """When cycle_end ties, earliest plan row must be consumed before later duplicates."""
        write_inputs(
            [
                "TIE9001,CUST9001,500,ACTIVE,CAFE,2026-04-05",
                "TIE9001,CUST9001,500,ACTIVE,CAFE,2026-04-05",
            ],
            [
                "TIE9001,CUST9001,500,CAF,2026-04-04",
                "TIE9001,CUST9001,500,CAF,2026-04-04",
            ],
            ["2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["location"] for row in rows] == ["CAFE", "CAFE"]
        assert summary["matched_count"] == 2
        assert summary["unmatched_count"] == 0
        assert [row["plan_row"] for row in read_consumption()] == ["0", "1"]

    def test_closed_unlisted_and_missing_action_dates_are_ineligible(self):
        """Closed, unlisted, and blank action dates should not match."""
        write_inputs(
            [
                "DATE9301,CUST9301,100,ACTIVE,DINING,2026-04-10",
                "DATE9302,CUST9302,200,ACTIVE,DINING,2026-04-10",
                "DATE9303,CUST9303,300,ACTIVE,DINING,2026-04-10",
            ],
            [
                "DATE9301,CUST9301,100,DINING,2026-04-05",
                "DATE9302,CUST9302,200,DINING,2026-04-06",
                "DATE9303,CUST9303,300,DINING,",
            ],
            ["2026-04-05 closed"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 600

    def test_missing_due_date_and_action_after_due_date_are_ineligible(self):
        """Missing source due dates and action dates after due date should reject matching."""
        write_inputs(
            [
                "DATE9401,CUST9401,700,ACTIVE,CAFE,",
                "DATE9402,CUST9402,800,ACTIVE,CAFE,2026-04-03",
            ],
            [
                "DATE9401,CUST9401,700,CAF,2026-04-02",
                "DATE9402,CUST9402,800,CAF,2026-04-04",
            ],
            ["2026-04-02 open", "2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert summary["unmatched_amount_cents"] == 1500

    def test_first_alias_still_works_with_dated_matching(self):
        """The first documented alias should still normalize under dated matching."""
        write_inputs(
            ["DATE9501,CUST9501,650,ACTIVE,DINING,2026-04-10"],
            ["DATE9501,CUST9501,650,DIN,2026-04-05"],
            ["2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["location"] == "DINING"
        assert summary == {"matched_count": 1, "matched_amount_cents": 650, "unmatched_count": 0, "unmatched_amount_cents": 0}
