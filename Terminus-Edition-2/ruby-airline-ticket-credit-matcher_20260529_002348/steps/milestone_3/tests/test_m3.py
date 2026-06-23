
"""Verifier tests for the Ruby airline reconciliation CLI."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "tickets.csv"
ACTIONS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"


def write_inputs(source_rows, action_rows, calendar_rows=None, dated=False, source_dated=None, action_dated=None):
    """Replace CSV inputs and optional calendar with a focused scenario."""
    source_has_date = dated if source_dated is None else source_dated
    action_has_date = dated if action_dated is None else action_dated
    source_header = "ticket_id,traveler_id,amount_cents,status,fare_class" + (",flight_date" if source_has_date else "")
    action_header = "ticket_id,traveler_id,amount_cents,fare_class" + (",credit_date" if action_has_date else "")
    SOURCE.write_text(source_header + "\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text(action_header + "\n" + "\n".join(action_rows) + "\n")
    if calendar_rows is not None:
        CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the Ruby batch and return parsed report and summary outputs."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


def test_middle_value_matches_and_counts_positive_amount():
    """The middle allowed value should match and matched totals should be positive."""
    write_inputs(
        ["SRC1001,CUST1001,1200,FLOWN,ECONOMY", "SRC1002,CUST1002,2300,FLOWN,BUSINESS"],
        ["SRC1001,CUST1001,1200,ECONOMY", "SRC1002,CUST1002,2300,BUSINESS"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["fare_class"] == "BUSINESS"
    assert summary["matched_amount_cents"] == 3500


def test_allowed_fare_classes_must_match_exactly():
    """Two different allowed fare classes on the same ticket should not match."""
    write_inputs(
        ["SRC8001,CUST8001,1500,FLOWN,ECONOMY"],
        ["SRC8001,CUST8001,1500,BUSINESS"],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["fare_class"] == ""
    assert summary["matched_count"] == 0
    assert summary["unmatched_amount_cents"] == 1500


def test_full_identifier_matching_rejects_prefix_collision():
    """Only full ticket_id equality should match; shared prefixes are not enough."""
    write_inputs(
        ["PREFIX770001,CUST2001,3300,FLOWN,ECONOMY", "PREFIX770002,CUST2001,3300,FLOWN,ECONOMY"],
        ["PREFIX770003,CUST2001,3300,ECONOMY", "PREFIX770002,CUST2001,3300,ECONOMY"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["fare_class"] == ""
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_customer_amount_status_and_dimension_all_gate_matching():
    """Customer, amount, status, and allowed dimension must all gate matching."""
    write_inputs(
        [
            "SRC3001,CUST3001,1000,FLOWN,ECONOMY",
            "SRC3002,CUST3002,2000,FLOWN,BUSINESS",
            "SRC3003,CUST3003,3000,DRAFT,FIRST",
            "SRC3004,CUST3004,4000,FLOWN,CHECK",
            "SRC3005,CUST3005,5000,FLOWN,FIRST",
        ],
        [
            "SRC3001,CUST9999,1000,ECONOMY",
            "SRC3002,CUST3002,2100,BUSINESS",
            "SRC3003,CUST3003,3000,FIRST",
            "SRC3004,CUST3004,4000,CHECK",
            "SRC3005,CUST3005,5000,FIRST",
        ],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["fare_class"] == "FIRST"
    assert summary["matched_count"] == 1
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_actions_do_not_reuse_consumed_source_row():
    """Duplicate actions should not consume the same source row twice."""
    write_inputs(
        ["SRC4001,CUST4001,5500,FLOWN,BUSINESS"],
        ["SRC4001,CUST4001,5500,BUSINESS", "SRC4001,CUST4001,5500,BUSINESS"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert summary["matched_count"] == 1
    assert summary["unmatched_count"] == 1


def test_trimming_and_case_normalization_are_applied():
    """Fields should be trimmed and status/dimension comparisons should be case-insensitive."""
    write_inputs(
        [" SRC5001 , CUST5001 , 6600 , flown , business "],
        [" SRC5001 , CUST5001 , 6600 , BUSINESS "],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["fare_class"] == "BUSINESS"
    assert summary["matched_amount_cents"] == 6600


def test_report_schema_order_and_blank_unmatched_dimension():
    """Report schema, action input order, and blank unmatched dimension should be stable."""
    write_inputs(
        ["SRC6002,CUST6002,1200,FLOWN,ECONOMY", "SRC6001,CUST6001,1100,FLOWN,BUSINESS"],
        ["SRC6001,CUST6001,1100,BUSINESS", "NO_MATCH,CUST9999,9900,ECONOMY", "SRC6002,CUST6002,1200,ECONOMY"],
    )
    rows, summary = run_program()
    assert list(rows[0].keys()) == ["ticket_id", "traveler_id", "fare_class", "amount_cents", "status"]
    assert [row["ticket_id"] for row in rows] == ["SRC6001", "NO_MATCH", "SRC6002"]
    assert rows[1]["fare_class"] == ""
    assert summary == {"matched_count": 2, "matched_amount_cents": 2300, "unmatched_count": 1, "unmatched_amount_cents": 9900}


def test_all_legacy_aliases_match_and_emit_canonical_values():
    """Every documented legacy alias should normalize and emit canonical values."""
    write_inputs(
        [
            "ALIAS7001,CUST7001,3100,FLOWN,ECONOMY",
            "ALIAS7002,CUST7002,3200,FLOWN,BUSINESS",
            "ALIAS7003,CUST7003,3300,FLOWN,FIRST",
            "ALIAS7004,CUST7004,3400,FLOWN,CHECK",
        ],
        [
            "ALIAS7001,CUST7001,3100,eco",
            "ALIAS7002,CUST7002,3200,BIZ",
            "ALIAS7003,CUST7003,3300,FST",
            "ALIAS7004,CUST7004,3400,UNKNOWN",
        ],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["fare_class"] for row in rows] == ["ECONOMY", "BUSINESS", "FIRST", ""]
    assert summary["matched_amount_cents"] == 9600
    assert summary["unmatched_amount_cents"] == 3400


class TestMilestone3:
    """Date gates, latest source-date selection, aliases, and row consumption."""

    def test_open_action_date_and_latest_due_date_win(self):
        """Open action dates should gate matching and latest eligible due date should win."""
        write_inputs(
            [
                "DATE9001,CUST9001,1000,FLOWN,ECONOMY,2026-04-03",
                "DATE9001,CUST9001,1000,FLOWN,BUSINESS,2026-04-08",
                "DATE9002,CUST9002,2000,FLOWN,BUSINESS,2026-04-02",
            ],
            [
                "DATE9001,CUST9001,1000,BIZ,2026-04-02",
                "DATE9002,CUST9002,2000,BIZ,2026-04-04",
            ],
            ["2026-04-02 open", "2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[0]["fare_class"] == "BUSINESS"
        assert summary["matched_amount_cents"] == 1000
        assert summary["unmatched_amount_cents"] == 2000

    def test_same_fare_class_latest_flight_date_wins(self):
        """Latest flight_date must win when an older-dated ticket row appears first."""
        write_inputs(
            [
                "DATE9051,CUST9051,1000,FLOWN,BUSINESS,2026-04-03",
                "DATE9051,CUST9051,1000,FLOWN,BUSINESS,2026-04-08",
            ],
            [
                "DATE9051,CUST9051,1000,BIZ,2026-04-02",
                "DATE9051,CUST9051,1000,BIZ,2026-04-04",
            ],
            ["2026-04-02 open", "2026-04-04 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[0]["fare_class"] == "BUSINESS"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1000,
        }

    def test_credit_date_equal_to_flight_date_is_eligible(self):
        """A credit on the same calendar day as flight_date should match when the date is open."""
        write_inputs(
            ["DATE9061,CUST9061,1250,FLOWN,FIRST,2026-04-05"],
            ["DATE9061,CUST9061,1250,FST,2026-04-05"],
            ["2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["fare_class"] == "FIRST"
        assert summary["matched_count"] == 1

    def test_latest_flight_date_wins_before_older_record_is_used(self):
        """Latest flight_date must beat first-in-file-order when both rows share fare_class."""
        write_inputs(
            [
                "DATE9101,CUST9101,850,FLOWN,BUSINESS,2026-04-05",
                "DATE9101,CUST9101,850,FLOWN,BUSINESS,2026-04-08",
            ],
            [
                "DATE9101,CUST9101,850,BIZ,2026-04-02",
                "DATE9101,CUST9101,850,BIZ,2026-04-06",
            ],
            ["2026-04-02 open", "2026-04-06 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[0]["fare_class"] == "BUSINESS"
        assert summary["matched_count"] == 1
        assert summary["unmatched_count"] == 1

    def test_undated_inputs_skip_date_gating(self):
        """Without flight_date or credit_date columns, milestone 1-2 matching still applies."""
        write_inputs(
            ["DATE9151,CUST9151,900,FLOWN,ECONOMY", "DATE9152,CUST9152,1100,FLOWN,FIRST"],
            ["DATE9151,CUST9151,900,ECO", "DATE9152,CUST9152,1100,FST"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["fare_class"] for row in rows] == ["ECONOMY", "FIRST"]
        assert summary["matched_amount_cents"] == 2000

    def test_source_date_column_without_action_date_activates_dated_mode(self):
        """A lone source flight_date column should activate dated mode and reject missing credit_date."""
        write_inputs(
            ["DATE9161,CUST9161,900,FLOWN,ECONOMY,2026-04-10"],
            ["DATE9161,CUST9161,900,ECO"],
            ["2026-04-05 open"],
            source_dated=True,
            action_dated=False,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["fare_class"] == ""
        assert summary["matched_count"] == 0

    def test_action_date_column_without_source_date_activates_dated_mode(self):
        """A lone credit_date column should activate dated mode and reject missing flight_date."""
        write_inputs(
            ["DATE9162,CUST9162,950,FLOWN,FIRST"],
            ["DATE9162,CUST9162,950,FST,2026-04-05"],
            ["2026-04-05 open"],
            source_dated=False,
            action_dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["fare_class"] == ""
        assert summary["matched_count"] == 0

    def test_same_flight_date_tie_prefers_earliest_ticket_input_row(self):
        """When flight_date ties, distinct amounts must match the earliest ticket row first."""
        write_inputs(
            [
                "TIE9201,CUST9201,500,FLOWN,FIRST,2026-04-05",
                "TIE9201,CUST9201,600,FLOWN,FIRST,2026-04-05",
                "TIE9201,CUST9201,700,FLOWN,FIRST,2026-04-08",
            ],
            [
                "TIE9201,CUST9201,700,FST,2026-04-06",
                "TIE9201,CUST9201,500,FST,2026-04-04",
                "TIE9201,CUST9201,600,FST,2026-04-04",
            ],
            ["2026-04-04 open", "2026-04-06 open", "2026-04-08 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1800

    def test_same_flight_date_tie_leaves_later_duplicate_row_unmatched(self):
        """After the earliest tied row is consumed, a third credit for that date must stay unmatched."""
        write_inputs(
            [
                "TIE9211,CUST9211,500,FLOWN,FIRST,2026-04-05",
                "TIE9211,CUST9211,600,FLOWN,FIRST,2026-04-05",
            ],
            [
                "TIE9211,CUST9211,500,FST,2026-04-04",
                "TIE9211,CUST9211,600,FST,2026-04-04",
                "TIE9211,CUST9211,500,FST,2026-04-04",
            ],
            ["2026-04-04 open", "2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 2
        assert summary["unmatched_count"] == 1

    def test_closed_unlisted_and_missing_action_dates_are_ineligible(self):
        """Closed, unlisted, and blank action dates should not match."""
        write_inputs(
            [
                "DATE9301,CUST9301,100,FLOWN,ECONOMY,2026-04-10",
                "DATE9302,CUST9302,200,FLOWN,ECONOMY,2026-04-10",
                "DATE9303,CUST9303,300,FLOWN,ECONOMY,2026-04-10",
            ],
            [
                "DATE9301,CUST9301,100,ECONOMY,2026-04-05",
                "DATE9302,CUST9302,200,ECONOMY,2026-04-06",
                "DATE9303,CUST9303,300,ECONOMY,",
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
                "DATE9401,CUST9401,700,FLOWN,BUSINESS,",
                "DATE9402,CUST9402,800,FLOWN,BUSINESS,2026-04-03",
            ],
            [
                "DATE9401,CUST9401,700,BIZ,2026-04-02",
                "DATE9402,CUST9402,800,BIZ,2026-04-04",
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
            ["DATE9501,CUST9501,650,FLOWN,ECONOMY,2026-04-10"],
            ["DATE9501,CUST9501,650,ECO,2026-04-05"],
            ["2026-04-05 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["fare_class"] == "ECONOMY"
        assert summary == {"matched_count": 1, "matched_amount_cents": 650, "unmatched_count": 0, "unmatched_amount_cents": 0}
