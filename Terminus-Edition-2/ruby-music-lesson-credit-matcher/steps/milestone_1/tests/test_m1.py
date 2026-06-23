
"""Verifier tests for the Ruby music reconciliation CLI."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "lessons.csv"
ACTIONS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"


def write_inputs(source_rows, action_rows, calendar_rows=None, dated=False):
    """Replace CSV inputs and optional calendar with a focused scenario."""
    source_header = "lesson_id,student_id,amount_cents,status,instrument" + (",lesson_date" if dated else "")
    action_header = "lesson_id,student_id,amount_cents,instrument" + (",credit_date" if dated else "")
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






class TestMilestone1:
    """Milestone 1 verifier scenarios."""

    def test_middle_value_matches_and_counts_positive_amount(self):
        """The middle allowed value should match and matched totals should be positive."""
        write_inputs(
            ["SRC1001,CUST1001,1200,TAUGHT,PIANO", "SRC1002,CUST1002,2300,TAUGHT,GUITAR"],
            ["SRC1001,CUST1001,1200,PIANO", "SRC1002,CUST1002,2300,GUITAR"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["instrument"] == "GUITAR"
        assert summary["matched_amount_cents"] == 3500


    def test_full_identifier_matching_rejects_prefix_collision(self):
        """Only full lesson_id equality should match; shared prefixes are not enough."""
        write_inputs(
            ["PREFIX770001,CUST2001,3300,TAUGHT,PIANO", "PREFIX770002,CUST2001,3300,TAUGHT,PIANO"],
            ["PREFIX770003,CUST2001,3300,PIANO", "PREFIX770002,CUST2001,3300,PIANO"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["instrument"] == ""
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300


    def test_customer_amount_status_and_dimension_all_gate_matching(self):
        """Customer, amount, status, and allowed dimension must all gate matching."""
        write_inputs(
            [
                "SRC3001,CUST3001,1000,TAUGHT,PIANO",
                "SRC3002,CUST3002,2000,TAUGHT,GUITAR",
                "SRC3003,CUST3003,3000,DRAFT,VIOLIN",
                "SRC3004,CUST3004,4000,TAUGHT,CHECK",
                "SRC3005,CUST3005,5000,TAUGHT,VIOLIN",
            ],
            [
                "SRC3001,CUST9999,1000,PIANO",
                "SRC3002,CUST3002,2100,GUITAR",
                "SRC3003,CUST3003,3000,VIOLIN",
                "SRC3004,CUST3004,4000,CHECK",
                "SRC3005,CUST3005,5000,VIOLIN",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["instrument"] == "VIOLIN"
        assert summary["matched_count"] == 1
        assert summary["unmatched_amount_cents"] == 10100


    def test_duplicate_actions_do_not_reuse_consumed_source_row(self):
        """Duplicate actions should not consume the same source row twice."""
        write_inputs(
            ["SRC4001,CUST4001,5500,TAUGHT,GUITAR"],
            ["SRC4001,CUST4001,5500,GUITAR", "SRC4001,CUST4001,5500,GUITAR"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 1
        assert summary["unmatched_count"] == 1


    def test_trimming_and_case_normalization_are_applied(self):
        """Fields should be trimmed and status/dimension comparisons should be case-insensitive."""
        write_inputs(
            [" SRC5001 , CUST5001 , 6600 , taught , guitar "],
            [" SRC5001 , CUST5001 , 6600 , GUITAR "],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["instrument"] == "GUITAR"
        assert summary["matched_amount_cents"] == 6600


    def test_report_schema_order_and_blank_unmatched_dimension(self):
        """Report schema, action input order, and blank unmatched dimension should be stable."""
        write_inputs(
            ["SRC6002,CUST6002,1200,TAUGHT,PIANO", "SRC6001,CUST6001,1100,TAUGHT,GUITAR"],
            ["SRC6001,CUST6001,1100,GUITAR", "NO_MATCH,CUST9999,9900,PIANO", "SRC6002,CUST6002,1200,PIANO"],
        )
        rows, summary = run_program()
        assert list(rows[0].keys()) == ["lesson_id", "student_id", "instrument", "amount_cents", "status"]
        assert [row["lesson_id"] for row in rows] == ["SRC6001", "NO_MATCH", "SRC6002"]
        assert rows[1]["instrument"] == ""
        assert summary == {"matched_count": 2, "matched_amount_cents": 2300, "unmatched_count": 1, "unmatched_amount_cents": 9900}
