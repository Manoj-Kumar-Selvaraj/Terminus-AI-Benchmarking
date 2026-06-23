
"""Verifier tests for the Ruby auto-service reconciliation CLI."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "invoices.csv"
ACTIONS = APP / "data" / "rebates.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "rebate_report.csv"
SUMMARY = APP / "out" / "rebate_summary.json"


def write_inputs(source_rows, action_rows, calendar_rows=None, dated=False):
    """Replace CSV inputs and optional calendar with a focused scenario."""
    source_header = "invoice_id,vehicle_id,amount_cents,status,bay" + (",service_date" if dated else "")
    action_header = "invoice_id,vehicle_id,amount_cents,bay" + (",rebate_date" if dated else "")
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


def test_middle_value_matches_and_counts_positive_amount():
    """The middle allowed value should match and matched totals should be positive."""
    write_inputs(
        ["SRC1001,CUST1001,1200,CLOSED,EXPRESS", "SRC1002,CUST1002,2300,CLOSED,STANDARD"],
        ["SRC1001,CUST1001,1200,EXPRESS", "SRC1002,CUST1002,2300,STANDARD"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["bay"] == "STANDARD"
    assert summary["matched_amount_cents"] == 3500


def test_full_identifier_matching_rejects_prefix_collision():
    """Only full invoice_id equality should match; shared prefixes are not enough."""
    write_inputs(
        ["PREFIX770001,CUST2001,3300,CLOSED,EXPRESS", "PREFIX770002,CUST2001,3300,CLOSED,EXPRESS"],
        ["PREFIX770003,CUST2001,3300,EXPRESS", "PREFIX770002,CUST2001,3300,EXPRESS"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["bay"] == ""
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_dimension_all_gate_matching():
    """Customer, amount, status, and allowed dimension must all gate matching."""
    write_inputs(
        [
            "SRC3001,CUST3001,1000,CLOSED,EXPRESS",
            "SRC3002,CUST3002,2000,CLOSED,STANDARD",
            "SRC3003,CUST3003,3000,DRAFT,DETAIL",
            "SRC3004,CUST3004,4000,CLOSED,CHECK",
            "SRC3005,CUST3005,5000,CLOSED,DETAIL",
        ],
        [
            "SRC3001,CUST9999,1000,EXPRESS",
            "SRC3002,CUST3002,2100,STANDARD",
            "SRC3003,CUST3003,3000,DETAIL",
            "SRC3004,CUST3004,4000,CHECK",
            "SRC3005,CUST3005,5000,DETAIL",
        ],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["bay"] == "DETAIL"
    assert summary["matched_count"] == 1
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_actions_do_not_reuse_consumed_source_row():
    """Duplicate actions should not consume the same source row twice."""
    write_inputs(
        ["SRC4001,CUST4001,5500,CLOSED,STANDARD"],
        ["SRC4001,CUST4001,5500,STANDARD", "SRC4001,CUST4001,5500,STANDARD"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert summary["matched_count"] == 1
    assert summary["unmatched_count"] == 1


def test_trimming_and_case_normalization_are_applied():
    """Fields should be trimmed and status/dimension comparisons should be case-insensitive."""
    write_inputs(
        [" SRC5001 , CUST5001 , 6600 , closed , standard "],
        [" SRC5001 , CUST5001 , 6600 , STANDARD "],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["bay"] == "STANDARD"
    assert summary["matched_amount_cents"] == 6600


def test_report_schema_order_and_blank_unmatched_dimension():
    """Report schema, action input order, and blank unmatched dimension should be stable."""
    write_inputs(
        ["SRC6002,CUST6002,1200,CLOSED,EXPRESS", "SRC6001,CUST6001,1100,CLOSED,STANDARD"],
        ["SRC6001,CUST6001,1100,STANDARD", "NO_MATCH,CUST9999,9900,EXPRESS", "SRC6002,CUST6002,1200,EXPRESS"],
    )
    rows, summary = run_program()
    assert list(rows[0].keys()) == ["invoice_id", "vehicle_id", "bay", "amount_cents", "status"]
    assert [row["invoice_id"] for row in rows] == ["SRC6001", "NO_MATCH", "SRC6002"]
    assert rows[1]["bay"] == ""
    assert summary == {"matched_count": 2, "matched_amount_cents": 2300, "unmatched_count": 1, "unmatched_amount_cents": 9900}


def test_all_legacy_aliases_match_and_emit_canonical_values():
    """Every documented legacy alias should normalize and emit canonical values."""
    write_inputs(
        [
            "ALIAS7001,CUST7001,3100,CLOSED,EXPRESS",
            "ALIAS7002,CUST7002,3200,CLOSED,STANDARD",
            "ALIAS7003,CUST7003,3300,CLOSED,DETAIL",
            "ALIAS7004,CUST7004,3400,CLOSED,CHECK",
        ],
        [
            "ALIAS7001,CUST7001,3100,exp",
            "ALIAS7002,CUST7002,3200,STD",
            "ALIAS7003,CUST7003,3300,DTL",
            "ALIAS7004,CUST7004,3400,UNKNOWN",
        ],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["bay"] for row in rows] == ["EXPRESS", "STANDARD", "DETAIL", ""]
    assert summary["matched_amount_cents"] == 9600
    assert summary["unmatched_amount_cents"] == 3400


class TestMilestone3:
    """Date gates, latest source-date selection, aliases, and row consumption."""

    def test_undated_inputs_apply_milestone_2_matching_without_calendar_gates(self):
        """Without date columns, matching must follow milestone 2 rules and ignore the calendar."""
        write_inputs(
            [
                "UND8001,CUST8001,1000,CLOSED,STANDARD",
                "UND8002,CUST8002,2000,CLOSED,EXPRESS",
            ],
            [
                "UND8001,CUST8001,1000,STD",
                "UND8002,CUST8002,2000,EXP",
            ],
            calendar_rows=["2026-04-01 closed"],
            dated=False,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["bay"] for row in rows] == ["STANDARD", "EXPRESS"]
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
                "DATE9001,CUST9001,1000,CLOSED,EXPRESS,2026-04-03",
                "DATE9001,CUST9001,1000,CLOSED,STANDARD,2026-04-08",
                "DATE9002,CUST9002,2000,CLOSED,STANDARD,2026-04-02",
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
        assert rows[0]["bay"] == "STANDARD"
        assert summary["matched_amount_cents"] == 1000
        assert summary["unmatched_amount_cents"] == 2000

    def test_latest_service_date_wins_before_older_invoice_row_is_used(self):
        """Latest service_date must win; consuming the older row leaves the second rebate ineligible."""
        write_inputs(
            [
                "SEL9501,CUST9501,800,CLOSED,STANDARD,2026-04-03",
                "SEL9501,CUST9501,800,CLOSED,STANDARD,2026-04-06",
            ],
            [
                "SEL9501,CUST9501,800,STD,2026-04-02",
                "SEL9501,CUST9501,800,STD,2026-04-04",
            ],
            ["2026-04-02 open", "2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[0]["bay"] == "STANDARD"
        assert rows[1]["bay"] == ""
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_latest_service_date_wins_even_when_later_dated_row_appears_first(self):
        """Among same-bay rows, latest service_date wins even when it appears earlier in the file."""
        write_inputs(
            [
                "SEL9051,CUST9051,1000,CLOSED,STANDARD,2026-04-08",
                "SEL9051,CUST9051,1000,CLOSED,STANDARD,2026-04-03",
            ],
            [
                "SEL9051,CUST9051,1000,STD,2026-04-02",
                "SEL9051,CUST9051,1000,STD,2026-04-04",
            ],
            ["2026-04-02 open", "2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[0]["bay"] == "STANDARD"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1000,
        }

    def test_same_service_date_tie_uses_earliest_invoice_row_and_consumption(self):
        """When service_date ties, earliest invoice row wins and only two of three rebates can match."""
        write_inputs(
            [
                "TIE9401,CUST9401,500,CLOSED,STANDARD,2026-04-05",
                "TIE9401,CUST9401,500,CLOSED,STANDARD,2026-04-05",
                "TIE9402,CUST9402,700,CLOSED,DETAIL,2026-04-05",
            ],
            [
                "TIE9401,CUST9401,500,STD,2026-04-04",
                "TIE9401,CUST9401,500,STD,2026-04-04",
                "TIE9401,CUST9401,500,STD,2026-04-04",
                "TIE9402,CUST9402,700,DTL,2026-04-05",
            ],
            ["2026-04-04 open", "2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["bay"] for row in rows] == ["STANDARD", "STANDARD", "", "DETAIL"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 1700,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_closed_unlisted_and_missing_action_dates_are_ineligible(self):
        """Closed, unlisted, and blank action dates should not match."""
        write_inputs(
            [
                "DATE9301,CUST9301,100,CLOSED,EXPRESS,2026-04-10",
                "DATE9302,CUST9302,200,CLOSED,EXPRESS,2026-04-10",
                "DATE9303,CUST9303,300,CLOSED,EXPRESS,2026-04-10",
            ],
            [
                "DATE9301,CUST9301,100,EXPRESS,2026-04-05",
                "DATE9302,CUST9302,200,EXPRESS,2026-04-06",
                "DATE9303,CUST9303,300,EXPRESS,",
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
                "DATE9401,CUST9401,700,CLOSED,STANDARD,",
                "DATE9402,CUST9402,800,CLOSED,STANDARD,2026-04-03",
            ],
            [
                "DATE9401,CUST9401,700,STD,2026-04-02",
                "DATE9402,CUST9402,800,STD,2026-04-04",
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
            ["DATE9501,CUST9501,650,CLOSED,EXPRESS,2026-04-10"],
            ["DATE9501,CUST9501,650,EXP,2026-04-05"],
            ["2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["bay"] == "EXPRESS"
        assert summary == {"matched_count": 1, "matched_amount_cents": 650, "unmatched_count": 0, "unmatched_amount_cents": 0}
