
"""Verifier tests for the Ruby cooking reconciliation CLI."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "classes.csv"
ACTIONS = APP / "data" / "vouchers.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "voucher_report.csv"
SUMMARY = APP / "out" / "voucher_summary.json"


def write_inputs(source_rows, action_rows, calendar_rows=None, dated=False):
    """Replace CSV inputs and optional calendar with a focused scenario."""
    source_header = "class_id,student_id,amount_cents,status,cuisine" + (",class_date" if dated else "")
    action_header = "class_id,student_id,amount_cents,cuisine" + (",voucher_date" if dated else "")
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
            ["SRC1001,CUST1001,1200,HELD,ITALIAN", "SRC1002,CUST1002,2300,HELD,THAI"],
            ["SRC1001,CUST1001,1200,ITALIAN", "SRC1002,CUST1002,2300,THAI"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["cuisine"] == "THAI"
        assert summary["matched_amount_cents"] == 3500


    def test_full_identifier_matching_rejects_prefix_collision(self):
        """Only full class_id equality should match; shared prefixes are not enough."""
        write_inputs(
            ["PREFIX770001,CUST2001,3300,HELD,ITALIAN", "PREFIX770002,CUST2001,3300,HELD,ITALIAN"],
            ["PREFIX770003,CUST2001,3300,ITALIAN", "PREFIX770002,CUST2001,3300,ITALIAN"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["cuisine"] == ""
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300


    def test_customer_amount_status_and_dimension_all_gate_matching(self):
        """Customer, amount, status, and allowed dimension must all gate matching."""
        write_inputs(
            [
                "SRC3001,CUST3001,1000,HELD,ITALIAN",
                "SRC3002,CUST3002,2000,HELD,THAI",
                "SRC3003,CUST3003,3000,DRAFT,PASTRY",
                "SRC3004,CUST3004,4000,HELD,CHECK",
                "SRC3005,CUST3005,5000,HELD,PASTRY",
            ],
            [
                "SRC3001,CUST9999,1000,ITALIAN",
                "SRC3002,CUST3002,2100,THAI",
                "SRC3003,CUST3003,3000,PASTRY",
                "SRC3004,CUST3004,4000,CHECK",
                "SRC3005,CUST3005,5000,PASTRY",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["cuisine"] == "PASTRY"
        assert summary["matched_count"] == 1
        assert summary["unmatched_amount_cents"] == 10100


    def test_duplicate_actions_do_not_reuse_consumed_source_row(self):
        """Duplicate actions should not consume the same source row twice."""
        write_inputs(
            ["SRC4001,CUST4001,5500,HELD,THAI"],
            ["SRC4001,CUST4001,5500,THAI", "SRC4001,CUST4001,5500,THAI"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 1
        assert summary["unmatched_count"] == 1


    def test_trimming_and_case_normalization_are_applied(self):
        """Fields should be trimmed and status/dimension comparisons should be case-insensitive."""
        write_inputs(
            [" SRC5001 , CUST5001 , 6600 , held , thai "],
            [" SRC5001 , CUST5001 , 6600 , THAI "],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["cuisine"] == "THAI"
        assert summary["matched_amount_cents"] == 6600


    def test_report_schema_order_and_blank_unmatched_dimension(self):
        """Report schema, action input order, and blank unmatched dimension should be stable."""
        write_inputs(
            ["SRC6002,CUST6002,1200,HELD,ITALIAN", "SRC6001,CUST6001,1100,HELD,THAI"],
            ["SRC6001,CUST6001,1100,THAI", "NO_MATCH,CUST9999,9900,ITALIAN", "SRC6002,CUST6002,1200,ITALIAN"],
        )
        rows, summary = run_program()
        assert list(rows[0].keys()) == ["class_id", "student_id", "cuisine", "amount_cents", "status"]
        assert [row["class_id"] for row in rows] == ["SRC6001", "NO_MATCH", "SRC6002"]
        assert rows[1]["cuisine"] == ""
        assert summary == {"matched_count": 2, "matched_amount_cents": 2300, "unmatched_count": 1, "unmatched_amount_cents": 9900}
