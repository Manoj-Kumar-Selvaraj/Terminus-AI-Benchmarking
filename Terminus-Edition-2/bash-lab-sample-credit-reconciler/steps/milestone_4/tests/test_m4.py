"""Verifier tests for payer clearance caps on the credit reconciliation CLI."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCES = APP / "data" / "samples.csv"
ACTIONS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
CAPS = APP / "config" / "payer_clearance_caps.csv"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"

DEFAULT_CAPS = "payer,cap_cents\nCARD,10000\nCASH,20000\nINSURANCE,15000\n"


def write_inputs(source_rows, action_rows, calendar_rows=None, caps_text=None):
    """Replace input CSV files with a focused scenario and clear previous outputs."""
    SOURCES.write_text("sample_id,patient_id,amount_cents,status,payer,result_date\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text("sample_id,patient_id,amount_cents,payer,credit_date\n" + "\n".join(action_rows) + "\n")
    if calendar_rows is None:
        calendar_rows = ["2026-04-01 open"]
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    CAPS.write_text(caps_text if caps_text is not None else DEFAULT_CAPS)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_undated_inputs(source_rows, action_rows, caps_text=None):
    """Write legacy milestone 2 CSV shapes and clear previous outputs."""
    SOURCES.write_text("sample_id,patient_id,amount_cents,status,payer\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text("sample_id,patient_id,amount_cents,payer\n" + "\n".join(action_rows) + "\n")
    CALENDAR.write_text("2026-04-01 closed\n")
    CAPS.write_text(caps_text if caps_text is not None else DEFAULT_CAPS)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the reconciliation script and return parsed outputs."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone4:
    def test_running_card_cap_blocks_second_match(self):
        """Cumulative CARD clearance must block a second match that would exceed the cap."""
        write_undated_inputs(
            [
                "SAMPLE810000001,PATIENT_ID01,0000005500,FINAL,CARD",
                "SAMPLE810000002,PATIENT_ID02,0000005000,FINAL,CARD",
            ],
            [
                "SAMPLE810000001,PATIENT_ID01,0000005500,CARD",
                "SAMPLE810000002,PATIENT_ID02,0000005000,CARD",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 1
        assert summary["unmatched_count"] == 1
        assert summary["matched_amount_cents"] == 5500

    def test_cap_blocked_credit_does_not_consume_sample(self):
        """A cap-blocked credit must leave its sample available for a later eligible credit."""
        write_undated_inputs(
            ["SAMPLE811000001,PATIENT_ID01,0000005000,FINAL,CARD"],
            [
                "SAMPLE811000001,PATIENT_ID01,0000005000,CARD",
                "SAMPLE811000001,PATIENT_ID01,0000005000,CARD",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 1

    def test_alias_cc_counts_toward_card_running_cap(self):
        """Canonical CARD totals must include credits that arrive as the cc alias."""
        write_undated_inputs(
            [
                "SAMPLE812000001,PATIENT_ID01,0000006000,FINAL,CARD",
                "SAMPLE812000002,PATIENT_ID02,0000005000,FINAL,CARD",
            ],
            [
                "SAMPLE812000001,PATIENT_ID01,0000006000,cc",
                "SAMPLE812000002,PATIENT_ID02,0000005000,cc",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert summary["matched_amount_cents"] == 6000

    def test_different_payers_have_independent_running_caps(self):
        """CARD and CASH running totals must not interfere with each other."""
        write_undated_inputs(
            [
                "SAMPLE813000001,PATIENT_ID01,0000005500,FINAL,CARD",
                "SAMPLE813000002,PATIENT_ID02,0000004400,FINAL,CASH",
            ],
            [
                "SAMPLE813000001,PATIENT_ID01,0000005500,CARD",
                "SAMPLE813000002,PATIENT_ID02,0000004400,CASH",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert summary["matched_amount_cents"] == 9900

    def test_dated_matching_and_caps_apply_together(self):
        """Calendar gates and cumulative caps must both pass before a dated credit matches."""
        write_inputs(
            [
                "SAMPLE814000001,PATIENT_ID01,0000007000,FINAL,INSURANCE,2026-04-12",
                "SAMPLE814000002,PATIENT_ID02,0000008500,FINAL,INSURANCE,2026-04-12",
            ],
            [
                "SAMPLE814000001,PATIENT_ID01,0000007000,INSURANCE,2026-04-10",
                "SAMPLE814000002,PATIENT_ID02,0000008500,INSURANCE,2026-04-10",
            ],
            ["2026-04-10 open", "2026-04-11 open", "2026-04-12 open"],
            "payer,cap_cents\nINSURANCE,15000\n",
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert summary["matched_amount_cents"] == 7000

    def test_uncapped_payer_is_not_limited_by_other_payer_totals(self):
        """Payers omitted from the caps file should remain uncapped."""
        write_undated_inputs(
            [
                "SAMPLE815000001,PATIENT_ID01,0000009000,FINAL,CARD",
                "SAMPLE815000002,PATIENT_ID02,0000009000,FINAL,CARD",
            ],
            [
                "SAMPLE815000001,PATIENT_ID01,0000009000,CARD",
                "SAMPLE815000002,PATIENT_ID02,0000009000,CARD",
            ],
            caps_text="payer,cap_cents\nCASH,20000\n",
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert summary["matched_amount_cents"] == 18000

    def test_exact_cap_boundary_allows_match(self):
        """A credit that reaches but does not exceed the cap must still match."""
        write_undated_inputs(
            ["SAMPLE816000001,PATIENT_ID01,0000010000,FINAL,CARD"],
            ["SAMPLE816000001,PATIENT_ID01,0000010000,CARD"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert summary["matched_amount_cents"] == 10000

    def test_undated_inputs_preserve_milestone_2_alias_matching_with_caps(self):
        """Undated alias normalization must still work once caps are enabled."""
        write_undated_inputs(
            [
                "SAMPLE817000001,PATIENT_ID01,0000004100,FINAL,CARD",
                "SAMPLE817000002,PATIENT_ID02,0000004200,FINAL,INSURANCE",
            ],
            [
                "SAMPLE817000001,PATIENT_ID01,0000004100,cc",
                "SAMPLE817000002,PATIENT_ID02,0000004200,ins",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["payer"] for row in rows] == ["CARD", "INSURANCE"]

    def test_cap_gate_runs_after_sample_selection_not_before(self):
        """A later credit blocked by caps must not prevent an earlier valid match on the same payer."""
        write_undated_inputs(
            [
                "SAMPLE818000001,PATIENT_ID01,0000003000,FINAL,CASH",
                "SAMPLE818000002,PATIENT_ID02,0000018000,FINAL,CASH",
            ],
            [
                "SAMPLE818000001,PATIENT_ID01,0000003000,CASH",
                "SAMPLE818000002,PATIENT_ID02,0000018000,CASH",
            ],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[1]["status"] == "UNMATCHED"
        assert summary["matched_amount_cents"] == 3000
