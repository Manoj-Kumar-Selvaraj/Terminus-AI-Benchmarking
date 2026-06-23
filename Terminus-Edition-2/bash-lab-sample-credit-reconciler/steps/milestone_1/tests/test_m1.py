"""Verifier tests for the lab credit reconciliation CLI."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCES = APP / "data" / "samples.csv"
ACTIONS = APP / "data" / "credits.csv"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"


def write_inputs(source_rows, action_rows):
    """Replace input CSV files with a focused scenario and clear previous outputs."""
    SOURCES.write_text("sample_id,patient_id,amount_cents,status,payer\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text("sample_id,patient_id,amount_cents,payer\n" + "\n".join(action_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the reconciliation script and return parsed outputs."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone1:
    def test_insurance_credit_matches_and_counts_positive_amount(self):
        """INSURANCE credits should match eligible samples and add positive cents."""
        write_inputs(
            ["SAMPLE100000001,PATIENT_ID01,0000001200,FINAL,CASH", "SAMPLE100000002,PATIENT_ID02,0000002300,FINAL,INSURANCE"],
            ["SAMPLE100000001,PATIENT_ID01,0000001200,CASH", "SAMPLE100000002,PATIENT_ID02,0000002300,INSURANCE"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["payer"] == "INSURANCE"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 3500

    def test_sample_id_match_uses_full_identifier(self):
        """A credit must not match a sample sharing only the leading id prefix."""
        write_inputs(
            ["SAMPLE777770001,PATIENT_ID01,0000003300,FINAL,CASH", "SAMPLE777770002,PATIENT_ID01,0000003300,FINAL,CASH"],
            ["SAMPLE777770003,PATIENT_ID01,0000003300,CASH", "SAMPLE777770002,PATIENT_ID01,0000003300,CASH"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300

    def test_customer_amount_status_and_payer_all_gate_matching(self):
        """Customer, amount, status, and payer must all gate matching."""
        write_inputs(
            [
                "SAMPLE300000001,PATIENT_ID01,0000001000,FINAL,CASH",
                "SAMPLE300000002,PATIENT_ID02,0000002000,FINAL,CARD",
                "SAMPLE300000003,PATIENT_ID03,0000003000,PENDING,INSURANCE",
                "SAMPLE300000004,PATIENT_ID04,0000004000,FINAL,OTHER",
            ],
            [
                "SAMPLE300000001,WRONG001,0000001000,CASH",
                "SAMPLE300000002,PATIENT_ID02,0000002100,CARD",
                "SAMPLE300000003,PATIENT_ID03,0000003000,INSURANCE",
                "SAMPLE300000004,PATIENT_ID04,0000004000,OTHER",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 10100

    def test_duplicate_credits_do_not_reuse_consumed_sample(self):
        """Duplicate credits must not reuse the same consumed sample."""
        write_inputs(
            ["SAMPLE400000001,PATIENT_ID01,0000005500,FINAL,CARD"],
            ["SAMPLE400000001,PATIENT_ID01,0000005500,CARD", "SAMPLE400000001,PATIENT_ID01,0000005500,CARD"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 1
        assert summary["unmatched_count"] == 1

    def test_matching_trims_fields_and_normalizes_payer_status_case(self):
        """Matching should trim fields and compare status/payer case-insensitively."""
        write_inputs(
            ["  SAMPLE500000001  ,  PATIENT_ID01  , 0000006600 , final , card "],
            [" SAMPLE500000001 , PATIENT_ID01 , 0000006600 , CARD "],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["payer"] == "CARD"
        assert summary["matched_amount_cents"] == 6600

    def test_report_schema_and_credit_input_order_are_stable(self):
        """Report schema and credit input order should be stable."""
        write_inputs(
            ["SAMPLE600000002,PATIENT_ID02,0000001200,FINAL,CASH", "SAMPLE600000001,PATIENT_ID01,0000001100,FINAL,CARD"],
            ["SAMPLE600000001,PATIENT_ID01,0000001100,CARD", "SAMPLENO_MATCH,PATIENT_ID09,0000009900,CASH", "SAMPLE600000002,PATIENT_ID02,0000001200,CASH"],
        )
        rows, summary = run_program()
        assert list(rows[0].keys()) == ["sample_id", "patient_id", "payer", "amount_cents", "status"]
        assert [row["sample_id"] for row in rows] == ["SAMPLE600000001", "SAMPLENO_MATCH", "SAMPLE600000002"]
        assert rows[1]["payer"] == ""
        assert summary == {"matched_count": 2, "matched_amount_cents": 2300, "unmatched_count": 1, "unmatched_amount_cents": 9900}
