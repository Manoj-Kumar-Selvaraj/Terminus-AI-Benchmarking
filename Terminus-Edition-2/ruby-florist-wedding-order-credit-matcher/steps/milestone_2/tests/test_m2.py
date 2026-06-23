
"""Verifier tests for the Ruby florist reconciliation CLI."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "orders.csv"
ACTIONS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"


def write_inputs(source_rows, action_rows, calendar_rows=None, dated=False):
    """Replace CSV inputs and optional calendar with a focused scenario."""
    source_header = "order_id,couple_id,amount_cents,status,arrangement" + (",delivery_date" if dated else "")
    action_header = "order_id,couple_id,amount_cents,arrangement" + (",credit_date" if dated else "")
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






class TestMilestone2:
    """Milestone 2 verifier scenarios."""

    def test_middle_value_matches_and_counts_positive_amount(self):
        """The middle allowed value should match and matched totals should be positive."""
        write_inputs(
            ["SRC1001,CUST1001,1200,DELIVERED,BOUQUET", "SRC1002,CUST1002,2300,DELIVERED,CENTERPIECE"],
            ["SRC1001,CUST1001,1200,BOUQUET", "SRC1002,CUST1002,2300,CENTERPIECE"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["arrangement"] == "CENTERPIECE"
        assert summary["matched_amount_cents"] == 3500


    def test_full_identifier_matching_rejects_prefix_collision(self):
        """Only full order_id equality should match; shared prefixes are not enough."""
        write_inputs(
            ["PREFIX770001,CUST2001,3300,DELIVERED,BOUQUET", "PREFIX770002,CUST2001,3300,DELIVERED,BOUQUET"],
            ["PREFIX770003,CUST2001,3300,BOUQUET", "PREFIX770002,CUST2001,3300,BOUQUET"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["arrangement"] == ""
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300


    def test_customer_amount_status_and_dimension_all_gate_matching(self):
        """Customer, amount, status, and allowed dimension must all gate matching."""
        write_inputs(
            [
                "SRC3001,CUST3001,1000,DELIVERED,BOUQUET",
                "SRC3002,CUST3002,2000,DELIVERED,CENTERPIECE",
                "SRC3003,CUST3003,3000,DRAFT,ARCH",
                "SRC3004,CUST3004,4000,DELIVERED,CHECK",
                "SRC3005,CUST3005,5000,DELIVERED,ARCH",
            ],
            [
                "SRC3001,CUST9999,1000,BOUQUET",
                "SRC3002,CUST3002,2100,CENTERPIECE",
                "SRC3003,CUST3003,3000,ARCH",
                "SRC3004,CUST3004,4000,CHECK",
                "SRC3005,CUST3005,5000,ARCH",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["arrangement"] == "ARCH"
        assert summary["matched_count"] == 1
        assert summary["unmatched_amount_cents"] == 10100


    def test_duplicate_actions_do_not_reuse_consumed_source_row(self):
        """Duplicate actions should not consume the same source row twice."""
        write_inputs(
            ["SRC4001,CUST4001,5500,DELIVERED,CENTERPIECE"],
            ["SRC4001,CUST4001,5500,CENTERPIECE", "SRC4001,CUST4001,5500,CENTERPIECE"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 1
        assert summary["unmatched_count"] == 1


    def test_trimming_and_case_normalization_are_applied(self):
        """Fields should be trimmed and status/dimension comparisons should be case-insensitive."""
        write_inputs(
            [" SRC5001 , CUST5001 , 6600 , delivered , centerpiece "],
            [" SRC5001 , CUST5001 , 6600 , CENTERPIECE "],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["arrangement"] == "CENTERPIECE"
        assert summary["matched_amount_cents"] == 6600


    def test_report_schema_order_and_blank_unmatched_dimension(self):
        """Report schema, action input order, and blank unmatched dimension should be stable."""
        write_inputs(
            ["SRC6002,CUST6002,1200,DELIVERED,BOUQUET", "SRC6001,CUST6001,1100,DELIVERED,CENTERPIECE"],
            ["SRC6001,CUST6001,1100,CENTERPIECE", "NO_MATCH,CUST9999,9900,BOUQUET", "SRC6002,CUST6002,1200,BOUQUET"],
        )
        rows, summary = run_program()
        assert list(rows[0].keys()) == ["order_id", "couple_id", "arrangement", "amount_cents", "status"]
        assert [row["order_id"] for row in rows] == ["SRC6001", "NO_MATCH", "SRC6002"]
        assert rows[1]["arrangement"] == ""
        assert summary == {"matched_count": 2, "matched_amount_cents": 2300, "unmatched_count": 1, "unmatched_amount_cents": 9900}


    def test_all_legacy_aliases_match_and_emit_canonical_values(self):
        """Every documented legacy alias should normalize and emit canonical values."""
        write_inputs(
            [
                "ALIAS7001,CUST7001,3100,DELIVERED,BOUQUET",
                "ALIAS7002,CUST7002,3200,DELIVERED,CENTERPIECE",
                "ALIAS7003,CUST7003,3300,DELIVERED,ARCH",
                "ALIAS7004,CUST7004,3400,DELIVERED,CHECK",
            ],
            [
                "ALIAS7001,CUST7001,3100,bqt",
                "ALIAS7002,CUST7002,3200,CTR",
                "ALIAS7003,CUST7003,3300,ARC",
                "ALIAS7004,CUST7004,3400,UNKNOWN",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["arrangement"] for row in rows] == ["BOUQUET", "CENTERPIECE", "ARCH", ""]
        assert summary["matched_amount_cents"] == 9600
        assert summary["unmatched_amount_cents"] == 3400
