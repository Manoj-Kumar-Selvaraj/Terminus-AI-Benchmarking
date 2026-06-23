"""Verifier tests for specimen release-lot controls on the credit reconciliation CLI."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCES = APP / "data" / "samples.csv"
ACTIONS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
CAPS = APP / "config" / "payer_clearance_caps.csv"
LOTS = APP / "config" / "specimen_release_lots.csv"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"

DEFAULT_CAPS = "payer,cap_cents\nCARD,10000\nCASH,20000\nINSURANCE,15000\n"
DEFAULT_LOTS = (
    "lot_id,payer,release_date,capacity_cents,enabled\n"
    "LOT-A,CARD,2026-04-12,10000,Y\n"
    "LOT-B,CARD,2026-04-12,10000,N\n"
    "LOT-C,INSURANCE,2026-04-13,15000,yes\n"
)


def clear_outputs():
    """Remove previous report files so each case observes only its own run."""
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_dated_lot_inputs(source_rows, action_rows, calendar_rows=None, caps_text=None, lots_text=None):
    """Write dated CSV inputs with lot_id columns and focused config fixtures."""
    SOURCES.write_text("sample_id,patient_id,amount_cents,status,payer,result_date,lot_id\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text("sample_id,patient_id,amount_cents,payer,credit_date,lot_id\n" + "\n".join(action_rows) + "\n")
    if calendar_rows is None:
        calendar_rows = ["2026-04-10 open", "2026-04-11 open", "2026-04-12 open", "2026-04-13 open"]
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    CAPS.write_text(caps_text if caps_text is not None else DEFAULT_CAPS)
    LOTS.write_text(lots_text if lots_text is not None else DEFAULT_LOTS)
    clear_outputs()


def write_legacy_m4_inputs(source_rows, action_rows, caps_text=None):
    """Write milestone 4 CSV inputs without lot_id columns."""
    SOURCES.write_text("sample_id,patient_id,amount_cents,status,payer\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text("sample_id,patient_id,amount_cents,payer\n" + "\n".join(action_rows) + "\n")
    CALENDAR.write_text("2026-04-10 closed\n")
    CAPS.write_text(caps_text if caps_text is not None else DEFAULT_CAPS)
    LOTS.write_text(DEFAULT_LOTS)
    clear_outputs()


def run_program():
    """Run the reconciliation script and return parsed outputs."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone5:
    def test_matching_requires_same_enabled_open_lot_and_payer(self):
        """A lot must match both sides, be enabled, be open, and match the canonical payer."""
        write_dated_lot_inputs(
            [
                "SAMPLE900000001,PATIENT_ID01,0000003000,FINAL,CARD,2026-04-12, lot-a ",
                "SAMPLE900000002,PATIENT_ID02,0000003000,FINAL,CARD,2026-04-12,LOT-B",
                "SAMPLE900000003,PATIENT_ID03,0000003000,FINAL,INSURANCE,2026-04-13,LOT-C",
            ],
            [
                "SAMPLE900000001,PATIENT_ID01,0000003000,cc,2026-04-10,LOT-A",
                "SAMPLE900000002,PATIENT_ID02,0000003000,CARD,2026-04-10,LOT-B",
                "SAMPLE900000003,PATIENT_ID03,0000003000,ins,2026-04-11,LOT-C",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["payer"] for row in rows] == ["CARD", "", "INSURANCE"]
        assert summary["matched_amount_cents"] == 6000

    def test_lot_capacity_is_cumulative_per_lot_and_payer(self):
        """Release-lot capacity must accumulate across matched credits in file order."""
        write_dated_lot_inputs(
            [
                "SAMPLE901000001,PATIENT_ID01,0000004500,FINAL,CARD,2026-04-12,LOT-A",
                "SAMPLE901000002,PATIENT_ID02,0000003500,FINAL,CARD,2026-04-12,LOT-A",
                "SAMPLE901000003,PATIENT_ID03,0000002500,FINAL,INSURANCE,2026-04-13,LOT-C",
            ],
            [
                "SAMPLE901000001,PATIENT_ID01,0000004500,CARD,2026-04-10,LOT-A",
                "SAMPLE901000002,PATIENT_ID02,0000003500,CARD,2026-04-10,LOT-A",
                "SAMPLE901000003,PATIENT_ID03,0000002500,INS,2026-04-11,LOT-C",
            ],
            lots_text=(
                "lot_id,payer,release_date,capacity_cents,enabled\n"
                "LOT-A,CARD,2026-04-12,7000,Y\n"
                "LOT-C,INSURANCE,2026-04-13,15000,Y\n"
            ),
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert summary["matched_amount_cents"] == 7000
        assert summary["unmatched_amount_cents"] == 3500

    def test_release_date_must_be_open_and_not_before_credit_or_result_date(self):
        """Closed or premature release dates must make an otherwise valid lot ineligible."""
        write_dated_lot_inputs(
            [
                "SAMPLE902000001,PATIENT_ID01,0000003000,FINAL,CARD,2026-04-12,LOT-CLOSED",
                "SAMPLE902000002,PATIENT_ID02,0000003000,FINAL,CARD,2026-04-12,LOT-EARLY",
            ],
            [
                "SAMPLE902000001,PATIENT_ID01,0000003000,CARD,2026-04-10,LOT-CLOSED",
                "SAMPLE902000002,PATIENT_ID02,0000003000,CARD,2026-04-12,LOT-EARLY",
            ],
            ["2026-04-10 open", "2026-04-11 closed", "2026-04-12 open"],
            lots_text=(
                "lot_id,payer,release_date,capacity_cents,enabled\n"
                "LOT-CLOSED,CARD,2026-04-11,10000,Y\n"
                "LOT-EARLY,CARD,2026-04-11,10000,Y\n"
            ),
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 0

    def test_lot_gate_filters_rows_before_latest_result_date_selection(self):
        """An unreleased later sample must not be consumed ahead of an older eligible row."""
        write_dated_lot_inputs(
            [
                "SAMPLE903000001,PATIENT_ID01,0000003000,FINAL,CARD,2026-04-10,LOT-A",
                "SAMPLE903000001,PATIENT_ID01,0000003000,FINAL,CARD,2026-04-12,LOT-A",
            ],
            [
                "SAMPLE903000001,PATIENT_ID01,0000003000,CARD,2026-04-10,LOT-A",
                "SAMPLE903000001,PATIENT_ID01,0000003000,CARD,2026-04-10,LOT-A",
            ],
            ["2026-04-10 open", "2026-04-11 open", "2026-04-12 open"],
            lots_text="lot_id,payer,release_date,capacity_cents,enabled\nLOT-A,CARD,2026-04-11,10000,Y\n",
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 1

    def test_inputs_without_lot_columns_preserve_milestone_4_caps(self):
        """Milestone 5 must leave legacy no-lot inputs on the milestone 4 path."""
        write_legacy_m4_inputs(
            [
                "SAMPLE904000001,PATIENT_ID01,0000006000,FINAL,CARD",
                "SAMPLE904000002,PATIENT_ID02,0000005000,FINAL,CARD",
            ],
            [
                "SAMPLE904000001,PATIENT_ID01,0000006000,cc",
                "SAMPLE904000002,PATIENT_ID02,0000005000,cc",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[0]["payer"] == "CARD"
        assert summary["matched_amount_cents"] == 6000
