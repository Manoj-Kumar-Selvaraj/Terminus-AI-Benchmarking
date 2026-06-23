"""Verifier tests for the library waiver reconciliation CLI."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCES = APP / "data" / "fines.csv"
ACTIONS = APP / "data" / "waivers.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "waiver_report.csv"
SUMMARY = APP / "out" / "waiver_summary.json"


def write_inputs(source_rows, action_rows, calendar_rows=None):
    """Replace input CSV files with a focused scenario and clear previous outputs."""
    SOURCES.write_text("fine_id,patron_id,amount_cents,status,desk,due_date\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text("fine_id,patron_id,amount_cents,desk,waiver_date\n" + "\n".join(action_rows) + "\n")
    if calendar_rows is None:
        calendar_rows = ["2026-04-01 open"]
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the reconciliation script and return parsed outputs."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone3:
    def test_open_waiver_date_and_latest_due_date_win(self):
        """Open dates should gate matching and latest eligible due_date should win."""
        write_inputs(
            [
                "FINE900000001,PATRON_ID01,0000005000,ASSESSED,FRONT,2026-04-10",
                "FINE900000001,PATRON_ID01,0000005000,ASSESSED,FRONT,2026-04-20",
                "FINE900000002,PATRON_ID02,0000006000,ASSESSED,ONLINE,2026-04-05",
            ],
            [
                "FINE900000001,PATRON_ID01,0000005000,FRONT,2026-04-09",
                "FINE900000002,PATRON_ID02,0000006000,ONLINE,2026-04-07",
            ],
            ["2026-04-05 open", "2026-04-07 open", "2026-04-09 open", "2026-04-10 open", "2026-04-20 open"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_amount_cents"] == 6000

    def test_same_due_date_tie_uses_source_order_and_consumption(self):
        """Same-date candidates should use source row order and still enforce consumption."""
        write_inputs(
            [
                "FINE910000001,PATRON_ID01,0000004100,ASSESSED,MOBILE,2026-04-30",
                "FINE910000001,PATRON_ID01,0000004100,ASSESSED,MOBILE,2026-04-30",
            ],
            [
                "FINE910000001,PATRON_ID01,0000004100,MOBILE,2026-04-20",
                "FINE910000001,PATRON_ID01,0000004100,MOBILE,2026-04-20",
                "FINE910000001,PATRON_ID01,0000004100,MOBILE,2026-04-20",
            ],
            ["2026-04-20 open", "2026-04-30 open"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 2
        assert summary["unmatched_count"] == 1

    def test_closed_waiver_date_is_not_eligible(self):
        """Closed waiver_date should not be eligible."""
        write_inputs(
            ["FINE920000001,PATRON_ID01,0000005100,ASSESSED,FRONT,2026-04-30"],
            ["FINE920000001,PATRON_ID01,0000005100,FRONT,2026-04-10"],
            ["2026-04-10 closed", "2026-04-30 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_unlisted_waiver_date_is_not_eligible(self):
        """Unlisted waiver_date should not be treated as open."""
        write_inputs(
            ["FINE930000001,PATRON_ID01,0000005200,ASSESSED,ONLINE,2026-04-30"],
            ["FINE930000001,PATRON_ID01,0000005200,ONLINE,2026-04-10"],
            ["2026-04-30 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["unmatched_amount_cents"] == 5200

    def test_missing_waiver_date_is_not_eligible(self):
        """Missing waiver_date should not match."""
        write_inputs(
            ["FINE940000001,PATRON_ID01,0000005300,ASSESSED,ONLINE,2026-04-30"],
            ["FINE940000001,PATRON_ID01,0000005300,ONLINE,"],
            ["2026-04-30 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_source_without_due_date_is_not_eligible(self):
        """Missing source due_date should not match."""
        write_inputs(
            ["FINE950000001,PATRON_ID01,0000005400,ASSESSED,FRONT,"],
            ["FINE950000001,PATRON_ID01,0000005400,FRONT,2026-04-10"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"



    def test_exactly_two_open_days_before_source_date_is_eligible(self):
        """Exactly two open days after the waiver_date through the due_date should still match."""
        write_inputs(
            ["FINE970000001,PATRON_ID01,0000005700,ASSESSED,FRONT,2026-04-04"],
            ["FINE970000001,PATRON_ID01,0000005700,FRONT,2026-04-01"],
            ["2026-04-01 open", "2026-04-02 open", "2026-04-03 closed", "2026-04-04 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert summary["matched_count"] == 1

    def test_three_open_days_before_source_date_is_not_eligible(self):
        """Three open days after the waiver_date through the due_date should reject the match."""
        write_inputs(
            ["FINE970000002,PATRON_ID01,0000005800,ASSESSED,FRONT,2026-04-04"],
            ["FINE970000002,PATRON_ID01,0000005800,FRONT,2026-04-01"],
            ["2026-04-01 open", "2026-04-02 open", "2026-04-03 open", "2026-04-04 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 5800



    def test_closed_due_date_is_not_eligible(self):
        """A closed due_date should reject the match even when the waiver_date is open and in range."""
        write_inputs(
            ["FINE980000001,PATRON_ID01,0000005900,ASSESSED,FRONT,2026-04-04"],
            ["FINE980000001,PATRON_ID01,0000005900,FRONT,2026-04-02"],
            ["2026-04-02 open", "2026-04-03 open", "2026-04-04 closed"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["desk"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 5900

    def test_alias_matches_with_dates_and_emits_canonical_desk(self):
        """Alias handling should still work with date controls."""
        write_inputs(
            ["FINE960000001,PATRON_ID01,0000005500,ASSESSED,MOBILE,2026-04-30"],
            ["FINE960000001,PATRON_ID01,0000005500,APP,2026-04-10"],
            ["2026-04-10 open", "2026-04-30 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["desk"] == "MOBILE"
        assert summary["matched_amount_cents"] == 5500

    def test_mismatched_desk_does_not_match_even_with_valid_dates(self):
        """Date logic must not bypass the original desk equality requirement."""
        write_inputs(
            ["FINE985000001,PATRON_ID01,0000005750,ASSESSED,FRONT,2026-04-30"],
            ["FINE985000001,PATRON_ID01,0000005750,ONLINE,2026-04-10"],
            ["2026-04-10 open", "2026-04-30 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["desk"] == ""
        assert summary["unmatched_amount_cents"] == 5750

    def test_prior_match_criteria_still_reject_latest_due_date_decoy(self):
        """A later due_date must not win unless fine_id, patron_id, amount, and desk all match."""
        write_inputs(
            [
                "FINE996000001,PATRON_ID01,0000007000,ASSESSED,FRONT,2026-04-04",
                "FINE996000001,PATRON_ID01,0000007000,ASSESSED,ONLINE,2026-04-05",
                "FINE996000001,PATRON_ID99,0000007000,ASSESSED,FRONT,2026-04-04",
            ],
            ["FINE996000001,PATRON_ID01,0000007000,FRONT,2026-04-03"],
            ["2026-04-03 open", "2026-04-04 open", "2026-04-05 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["desk"] == "FRONT"
        assert summary["matched_count"] == 1
