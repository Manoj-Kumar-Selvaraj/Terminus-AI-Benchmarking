
"""Milestone 3 tests for the Ruby charity reconciliation CLI."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "pledges.csv"
ACTIONS = APP / "data" / "adjustments.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "adjustment_report.csv"
SUMMARY = APP / "out" / "adjustment_summary.json"


def write_inputs(source_rows, action_rows, calendar_rows=None, dated=False):
    """Replace CSV inputs and optional calendar with a focused scenario."""
    source_header = "pledge_id,donor_id,amount_cents,status,fund" + (",pledge_due" if dated else "")
    action_header = "pledge_id,donor_id,amount_cents,fund" + (",adjustment_date" if dated else "")
    SOURCE.write_text(source_header + "\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text(action_header + "\n" + "\n".join(action_rows) + "\n")
    if calendar_rows is not None:
        CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the Ruby batch and return parsed report and summary outputs."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone3:
    """Milestone 3 verifies dated matching, open calendar gating, latest due-date selection, and row-position consumption."""

    def test_middle_value_matches_and_counts_positive_amount(self):
        """The middle allowed value should match and matched totals should be positive."""
        write_inputs(
            ["SRC1001,CUST1001,1200,BOOKED,GENERAL", "SRC1002,CUST1002,2300,BOOKED,CAPITAL"],
            ["SRC1001,CUST1001,1200,GENERAL", "SRC1002,CUST1002,2300,CAPITAL"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["fund"] == "CAPITAL"
        assert summary["matched_amount_cents"] == 3500


    def test_full_identifier_matching_rejects_prefix_collision(self):
        """Only full pledge_id equality should match; shared prefixes are not enough."""
        write_inputs(
            ["PREFIX770001,CUST2001,3300,BOOKED,GENERAL", "PREFIX770002,CUST2001,3300,BOOKED,GENERAL"],
            ["PREFIX770003,CUST2001,3300,GENERAL", "PREFIX770002,CUST2001,3300,GENERAL"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["fund"] == ""
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300


    def test_customer_amount_status_and_dimension_all_gate_matching(self):
        """Customer, amount, status, and allowed dimension must all gate matching."""
        write_inputs(
            [
                "SRC3001,CUST3001,1000,BOOKED,GENERAL",
                "SRC3002,CUST3002,2000,BOOKED,CAPITAL",
                "SRC3003,CUST3003,3000,DRAFT,RELIEF",
                "SRC3004,CUST3004,4000,BOOKED,CHECK",
                "SRC3005,CUST3005,5000,BOOKED,RELIEF",
            ],
            [
                "SRC3001,CUST9999,1000,GENERAL",
                "SRC3002,CUST3002,2100,CAPITAL",
                "SRC3003,CUST3003,3000,RELIEF",
                "SRC3004,CUST3004,4000,CHECK",
                "SRC3005,CUST3005,5000,RELIEF",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["fund"] == "RELIEF"
        assert summary["matched_count"] == 1
        assert summary["unmatched_amount_cents"] == 10100


    def test_duplicate_actions_do_not_reuse_consumed_source_row(self):
        """Duplicate actions should not consume the same source row twice."""
        write_inputs(
            ["SRC4001,CUST4001,5500,BOOKED,CAPITAL"],
            ["SRC4001,CUST4001,5500,CAPITAL", "SRC4001,CUST4001,5500,CAPITAL"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 1
        assert summary["unmatched_count"] == 1


    def test_trimming_and_case_normalization_are_applied(self):
        """Fields should be trimmed and status/dimension comparisons should be case-insensitive."""
        write_inputs(
            [" SRC5001 , CUST5001 , 6600 , booked , capital "],
            [" SRC5001 , CUST5001 , 6600 , CAPITAL "],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["fund"] == "CAPITAL"
        assert summary["matched_amount_cents"] == 6600


    def test_report_schema_order_and_blank_unmatched_dimension(self):
        """Report schema, action input order, and blank unmatched dimension should be stable."""
        write_inputs(
            ["SRC6002,CUST6002,1200,BOOKED,GENERAL", "SRC6001,CUST6001,1100,BOOKED,CAPITAL"],
            ["SRC6001,CUST6001,1100,CAPITAL", "NO_MATCH,CUST9999,9900,GENERAL", "SRC6002,CUST6002,1200,GENERAL"],
        )
        rows, summary = run_program()
        assert list(rows[0].keys()) == ["pledge_id", "donor_id", "fund", "amount_cents", "status"]
        assert [row["pledge_id"] for row in rows] == ["SRC6001", "NO_MATCH", "SRC6002"]
        assert rows[1]["fund"] == ""
        assert summary == {"matched_count": 2, "matched_amount_cents": 2300, "unmatched_count": 1, "unmatched_amount_cents": 9900}


    def test_all_legacy_aliases_match_and_emit_canonical_values(self):
        """Every documented legacy alias should normalize and emit canonical values."""
        write_inputs(
            [
                "ALIAS7001,CUST7001,3100,BOOKED,GENERAL",
                "ALIAS7002,CUST7002,3200,BOOKED,CAPITAL",
                "ALIAS7003,CUST7003,3300,BOOKED,RELIEF",
                "ALIAS7004,CUST7004,3400,BOOKED,CHECK",
            ],
            [
                "ALIAS7001,CUST7001,3100,gen",
                "ALIAS7002,CUST7002,3200,CAP",
                "ALIAS7003,CUST7003,3300,REL",
                "ALIAS7004,CUST7004,3400,UNKNOWN",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["fund"] for row in rows] == ["GENERAL", "CAPITAL", "RELIEF", ""]
        assert summary["matched_amount_cents"] == 9600
        assert summary["unmatched_amount_cents"] == 3400


    def test_open_action_date_and_latest_due_date_win(self):
        """Open action dates should gate matching and latest eligible due date should win."""
        write_inputs(
            [
                "DATE9001,CUST9001,1000,BOOKED,GENERAL,2026-04-03",
                "DATE9001,CUST9001,1000,BOOKED,CAPITAL,2026-04-08",
                "DATE9002,CUST9002,2000,BOOKED,CAPITAL,2026-04-02",
            ],
            [
                "DATE9001,CUST9001,1000,CAP,2026-04-02",
                "DATE9002,CUST9002,2000,CAP,2026-04-04",
            ],
            ["2026-04-02 open", "2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[0]["fund"] == "CAPITAL"
        assert summary["matched_amount_cents"] == 1000
        assert summary["unmatched_amount_cents"] == 2000

    def test_latest_pledge_due_wins_among_multiple_same_fund_candidates(self):
        """Latest pledge_due selection must be observable through later consumption."""
        write_inputs(
            [
                "TIE01,D01,1000,BOOKED,CAPITAL,2026-04-05",
                "TIE01,D01,1000,BOOKED,CAPITAL,2026-04-10",
                "TIE01,D01,1000,BOOKED,CAPITAL,2026-04-07",
            ],
            [
                "TIE01,D01,1000,CAP,2026-04-04",
                "TIE01,D01,1000,CAP,2026-04-08",
            ],
            ["2026-04-04 open", "2026-04-08 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["fund"] for row in rows] == ["CAPITAL", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1000,
        }

    def test_latest_pledge_due_consumption_is_observable_when_later_adjustment_depends_on_it(self):
        """The latest eligible pledge_due must be consumed first, or the second adjustment outcome changes."""
        write_inputs(
            [
                "LATE01,D01,1000,BOOKED,CAPITAL,2026-04-05",
                "LATE01,D01,1000,BOOKED,CAPITAL,2026-04-07",
                "LATE01,D01,1000,BOOKED,CAPITAL,2026-04-10",
            ],
            [
                "LATE01,D01,1000,CAP,2026-04-04",
                "LATE01,D01,1000,CAP,2026-04-08",
            ],
            ["2026-04-04 open", "2026-04-08 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["fund"] for row in rows] == ["CAPITAL", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1000,
        }

    def test_same_due_date_tie_prefers_earliest_pledge_input_row(self):
        """When pledge_due ties across different funds, each adjustment still matches its canonical fund."""
        write_inputs(
            [
                "TIE02,D02,1000,BOOKED,RELIEF,2026-04-05",
                "TIE02,D02,1000,BOOKED,CAPITAL,2026-04-05",
                "TIE02,D02,2000,BOOKED,RELIEF,2026-04-10",
            ],
            [
                "TIE02,D02,1000,REL,2026-04-04",
                "TIE02,D02,1000,CAP,2026-04-04",
                "TIE02,D02,2000,REL,2026-04-04",
            ],
            ["2026-04-04 open", "2026-04-05 open", "2026-04-10 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["fund"] for row in rows] == ["RELIEF", "CAPITAL", "RELIEF"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 4000,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_same_due_date_tie_consumes_earliest_identical_pledge_row(self):
        """Identical pledge rows with the same pledge_due must consume earliest input row first."""
        write_inputs(
            [
                "DUP-TIE,D01,1000,BOOKED,GENERAL,2026-04-05",
                "DUP-TIE,D01,1000,BOOKED,GENERAL,2026-04-05",
            ],
            [
                "DUP-TIE,D01,1000,GENERAL,2026-04-04",
                "DUP-TIE,D01,1000,GENERAL,2026-04-04",
            ],
            ["2026-04-04 open", "2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 2000,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_closed_unlisted_and_missing_action_dates_are_ineligible(self):
        """Closed, unlisted, and blank action dates should not match."""
        write_inputs(
            [
                "DATE9301,CUST9301,100,BOOKED,GENERAL,2026-04-10",
                "DATE9302,CUST9302,200,BOOKED,GENERAL,2026-04-10",
                "DATE9303,CUST9303,300,BOOKED,GENERAL,2026-04-10",
            ],
            [
                "DATE9301,CUST9301,100,GENERAL,2026-04-05",
                "DATE9302,CUST9302,200,GENERAL,2026-04-06",
                "DATE9303,CUST9303,300,GENERAL,",
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
                "DATE9401,CUST9401,700,BOOKED,CAPITAL,",
                "DATE9402,CUST9402,800,BOOKED,CAPITAL,2026-04-03",
            ],
            [
                "DATE9401,CUST9401,700,CAP,2026-04-02",
                "DATE9402,CUST9402,800,CAP,2026-04-04",
            ],
            ["2026-04-02 open", "2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert summary["unmatched_amount_cents"] == 1500

    def test_undated_inputs_skip_calendar_gating(self):
        """When neither CSV has date columns, matching must follow undated alias-aware rules only."""
        write_inputs(
            ["UND9001,CUST9001,900,BOOKED,GENERAL", "UND9002,CUST9002,1100,BOOKED,CAPITAL"],
            ["UND9001,CUST9001,900,GEN", "UND9002,CUST9002,1100,CAP"],
            dated=False,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["fund"] for row in rows] == ["GENERAL", "CAPITAL"]
        assert summary["matched_amount_cents"] == 2000

    def test_adjustment_date_equal_to_pledge_due_is_eligible(self):
        """Equal calendar days for adjustment_date and pledge_due must remain eligible when open."""
        write_inputs(
            ["DATE9601,CUST9601,450,BOOKED,RELIEF,2026-04-12"],
            ["DATE9601,CUST9601,450,REL,2026-04-12"],
            ["2026-04-12 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["fund"] == "RELIEF"
        assert summary["matched_count"] == 1

    def test_first_alias_still_works_with_dated_matching(self):
        """The first documented alias should still normalize under dated matching."""
        write_inputs(
            ["DATE9501,CUST9501,650,BOOKED,GENERAL,2026-04-10"],
            ["DATE9501,CUST9501,650,GEN,2026-04-05"],
            ["2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["fund"] == "GENERAL"
        assert summary == {"matched_count": 1, "matched_amount_cents": 650, "unmatched_count": 0, "unmatched_amount_cents": 0}
