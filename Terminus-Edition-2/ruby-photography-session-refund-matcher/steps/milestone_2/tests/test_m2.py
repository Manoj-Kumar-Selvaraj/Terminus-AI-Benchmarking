
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






class TestMilestone2:
    """Verify M2 alias normalization while preserving exact M1 gates and consumption."""

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


    def test_all_legacy_aliases_match_and_emit_canonical_values(self):
        """Every documented legacy alias should normalize and emit canonical values."""
        write_inputs(
            [
                "ALIAS7001,CUST7001,3100,SHOT,MINI",
                "ALIAS7002,CUST7002,3200,SHOT,STANDARD",
                "ALIAS7003,CUST7003,3300,SHOT,PREMIUM",
                "ALIAS7004,CUST7004,3400,SHOT,CHECK",
            ],
            [
                "ALIAS7001,CUST7001,3100,min",
                "ALIAS7002,CUST7002,3200,STD",
                "ALIAS7003,CUST7003,3300,PRM",
                "ALIAS7004,CUST7004,3400,UNKNOWN",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["package"] for row in rows] == ["MINI", "STANDARD", "PREMIUM", ""]
        assert summary["matched_amount_cents"] == 9600
        assert summary["unmatched_amount_cents"] == 3400


    def test_trimmed_lowercase_alias_on_refund_normalizes(self):
        """Refund-side aliases should trim and normalize case-insensitively."""
        write_inputs(
            ["ALIAS8001,CUST8001,3700,SHOT,STANDARD"],
            [" ALIAS8001 , CUST8001 , 3700 , std "],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["package"] == "STANDARD"
        assert summary["matched_amount_cents"] == 3700


    def test_alias_on_session_side_also_normalizes(self):
        """Session-side aliases should normalize before matching refund canonical values."""
        write_inputs(
            ["ALIAS8101,CUST8101,3800,SHOT,prm"],
            ["ALIAS8101,CUST8101,3800,PREMIUM"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["package"] == "PREMIUM"
        assert summary["matched_count"] == 1


    def test_mixed_canonical_and_alias_batch_preserves_consumption(self):
        """Canonical and aliased rows in one batch should consume only matching physical sessions."""
        write_inputs(
            [
                "ALIAS8101,CUST8101,1000,SHOT,MINI",
                "ALIAS8101,CUST8101,1000,SHOT,STANDARD",
            ],
            [
                "ALIAS8101,CUST8101,1000,MIN",
                "ALIAS8101,CUST8101,1000,STANDARD",
                "ALIAS8101,CUST8101,1000,MIN",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["package"] for row in rows] == ["MINI", "STANDARD", ""]
        assert summary == {"matched_count": 2, "matched_amount_cents": 2000, "unmatched_count": 1, "unmatched_amount_cents": 1000}
