
"""Verifier tests for the Ruby photography reconciliation CLI."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "sessions.csv"
ACTIONS = APP / "data" / "refunds.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "refund_report.csv"
SUMMARY = APP / "out" / "refund_summary.json"


def write_inputs(source_rows, action_rows, calendar_rows=None, dated=False):
    """Replace CSV inputs and optional calendar with a focused scenario."""
    source_header = "session_id,client_id,amount_cents,status,package" + (",session_date" if dated else "")
    action_header = "session_id,client_id,amount_cents,package" + (",refund_date" if dated else "")
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
    """Verify M1 exact ids, positive totals, canonical package output, and single-use matching."""

    def test_middle_value_matches_and_counts_positive_amount(self):
        """The middle allowed value should match and matched totals should be positive."""
        write_inputs(
            ["SRC1001,CUST1001,1200,SHOT,MINI", "SRC1002,CUST1002,2300,SHOT,STANDARD"],
            ["SRC1001,CUST1001,1200,MINI", "SRC1002,CUST1002,2300,STANDARD"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["package"] == "STANDARD"
        assert summary["matched_amount_cents"] == 3500


    def test_full_identifier_matching_rejects_prefix_collision(self):
        """Only full session_id equality should match; shared prefixes are not enough."""
        write_inputs(
            ["PREFIX770001,CUST2001,3300,SHOT,MINI", "PREFIX770002,CUST2001,3300,SHOT,MINI"],
            ["PREFIX770003,CUST2001,3300,MINI", "PREFIX770002,CUST2001,3300,MINI"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["package"] == ""
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300


    def test_customer_amount_status_and_dimension_all_gate_matching(self):
        """Customer, amount, status, and allowed dimension must all gate matching."""
        write_inputs(
            [
                "SRC3001,CUST3001,1000,SHOT,MINI",
                "SRC3002,CUST3002,2000,SHOT,STANDARD",
                "SRC3003,CUST3003,3000,DRAFT,PREMIUM",
                "SRC3004,CUST3004,4000,SHOT,CHECK",
                "SRC3005,CUST3005,5000,SHOT,PREMIUM",
            ],
            [
                "SRC3001,CUST9999,1000,MINI",
                "SRC3002,CUST3002,2100,STANDARD",
                "SRC3003,CUST3003,3000,PREMIUM",
                "SRC3004,CUST3004,4000,CHECK",
                "SRC3005,CUST3005,5000,PREMIUM",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["package"] == "PREMIUM"
        assert summary["matched_count"] == 1
        assert summary["unmatched_amount_cents"] == 10100


    def test_duplicate_actions_do_not_reuse_consumed_source_row(self):
        """Duplicate actions should not consume the same source row twice."""
        write_inputs(
            ["SRC4001,CUST4001,5500,SHOT,STANDARD"],
            ["SRC4001,CUST4001,5500,STANDARD", "SRC4001,CUST4001,5500,STANDARD"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 1
        assert summary["unmatched_count"] == 1


    def test_trimming_and_case_normalization_are_applied(self):
        """Fields should be trimmed and status/dimension comparisons should be case-insensitive."""
        write_inputs(
            [" SRC5001 , CUST5001 , 6600 , shot , standard "],
            [" SRC5001 , CUST5001 , 6600 , STANDARD "],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["package"] == "STANDARD"
        assert summary["matched_amount_cents"] == 6600


    def test_report_schema_order_and_blank_unmatched_dimension(self):
        """Report schema, action input order, and blank unmatched dimension should be stable."""
        write_inputs(
            ["SRC6002,CUST6002,1200,SHOT,MINI", "SRC6001,CUST6001,1100,SHOT,STANDARD"],
            ["SRC6001,CUST6001,1100,STANDARD", "NO_MATCH,CUST9999,9900,MINI", "SRC6002,CUST6002,1200,MINI"],
        )
        rows, summary = run_program()
        assert list(rows[0].keys()) == ["session_id", "client_id", "package", "amount_cents", "status"]
        assert [row["session_id"] for row in rows] == ["SRC6001", "NO_MATCH", "SRC6002"]
        assert rows[1]["package"] == ""
        assert summary == {"matched_count": 2, "matched_amount_cents": 2300, "unmatched_count": 1, "unmatched_amount_cents": 9900}


    def test_premium_package_matches_when_all_fields_align(self):
        """Premium package rows should match when every gate passes."""
        write_inputs(
            ["SRC7101,CUST7101,4100,SHOT,PREMIUM"],
            ["SRC7101,CUST7101,4100,PREMIUM"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["package"] == "PREMIUM"
        assert summary["matched_amount_cents"] == 4100


    def test_action_package_must_match_source_exactly_without_alias(self):
        """Milestone 1 should not normalize aliases before matching."""
        write_inputs(
            ["SRC7201,CUST7201,4200,SHOT,STANDARD"],
            ["SRC7201,CUST7201,4200,STD"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["package"] == ""
        assert summary["matched_count"] == 0


    def test_client_identifier_must_match_full_trimmed_value(self):
        """Full client_id equality should independently reject otherwise valid rows."""
        write_inputs(
            ["CLT1001,CUST-ALPHA-01,1750,SHOT,MINI"],
            ["CLT1001,CUST-ALPHA,1750,MINI", "CLT1001,CUST-ALPHA-01,1750,MINI"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["package"] == ""
        assert summary == {"matched_count": 1, "matched_amount_cents": 1750, "unmatched_count": 1, "unmatched_amount_cents": 1750}


    def test_matched_report_emits_canonical_source_package_not_alias(self):
        """Matched rows should emit the canonical session package value."""
        write_inputs(
            ["SRC7301,CUST7301,4300,SHOT,MINI"],
            ["SRC7301,CUST7301,4300,MINI"],
        )
        rows, summary = run_program()
        assert rows[0]["package"] == "MINI"
        assert summary["matched_amount_cents"] == 4300
