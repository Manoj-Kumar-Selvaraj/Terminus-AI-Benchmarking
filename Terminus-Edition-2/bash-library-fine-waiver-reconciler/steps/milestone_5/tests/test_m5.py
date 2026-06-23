"""Milestone 5 verifier tests for configurable waiver open-day windows."""

import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCES = APP / "data" / "fines.csv"
ACTIONS = APP / "data" / "waivers.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
PROFILE = APP / "config" / "run_profile.ini"
REPORT = APP / "out" / "waiver_report.csv"
SUMMARY = APP / "out" / "waiver_summary.json"


def write_inputs(source_rows, action_rows, calendar_rows, window_days=2):
    """Replace dated CSV inputs, calendar, and waiver window setting."""
    SOURCES.write_text("fine_id,patron_id,amount_cents,status,desk,due_date\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text("fine_id,patron_id,amount_cents,desk,waiver_date\n" + "\n".join(action_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    base = PROFILE.read_text(encoding="utf-8")
    lines = [line for line in base.splitlines() if not line.startswith("waiver_open_window_days=")]
    lines.append(f"waiver_open_window_days={window_days}")
    PROFILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the reconciliation script and return parsed outputs."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone5:
    def test_two_open_days_after_waiver_is_eligible_with_default_window(self):
        """Exactly two open days after waiver_date through due_date should match when window is 2."""
        write_inputs(
            ["FINE910000001,PATRON_ID01,0000005700,ASSESSED,FRONT,2026-04-04"],
            ["FINE910000001,PATRON_ID01,0000005700,FRONT,2026-04-01"],
            ["2026-04-01 open", "2026-04-02 open", "2026-04-03 closed", "2026-04-04 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert summary["matched_count"] == 1

    def test_three_open_days_after_waiver_exceeds_default_window(self):
        """Three strictly-after open days should fail the default waiver_open_window_days=2 rule."""
        write_inputs(
            ["FINE920000001,PATRON_ID01,0000005800,ASSESSED,FRONT,2026-04-04"],
            ["FINE920000001,PATRON_ID01,0000005800,FRONT,2026-04-01"],
            ["2026-04-01 open", "2026-04-02 open", "2026-04-03 open", "2026-04-04 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_equal_waiver_and_due_dates_count_zero_open_days_after(self):
        """Same-day waiver and due dates should count zero window days and still match."""
        write_inputs(
            ["FINE930000001,PATRON_ID01,0000006500,ASSESSED,MOBILE,2026-04-05"],
            ["FINE930000001,PATRON_ID01,0000006500,APP,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["desk"] == "MOBILE"

    def test_closed_and_absent_dates_do_not_count_toward_window(self):
        """Only explicitly open dates after waiver_date through due_date should count against the window."""
        write_inputs(
            ["FINE935000001,PATRON_ID01,0000006650,ASSESSED,FRONT,2026-04-05"],
            ["FINE935000001,PATRON_ID01,0000006650,FRONT,2026-04-01"],
            ["2026-04-01 open", "2026-04-02 closed", "2026-04-04 open", "2026-04-05 open"],
            window_days=2,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert summary["matched_amount_cents"] == 6650

    def test_tighter_window_from_run_profile_blocks_wider_span(self):
        """waiver_open_window_days=1 should reject two open days after waiver_date."""
        write_inputs(
            ["FINE940000001,PATRON_ID01,0000005000,ASSESSED,FRONT,2026-04-03"],
            ["FINE940000001,PATRON_ID01,0000005000,FRONT,2026-04-01"],
            ["2026-04-01 open", "2026-04-02 open", "2026-04-03 open"],
            window_days=1,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"

    def test_window_does_not_bypass_desk_equality(self):
        """A valid open-day window must not match when desks differ after canonicalization."""
        write_inputs(
            ["FINE950000001,PATRON_ID01,0000007750,ASSESSED,FRONT,2026-04-02"],
            ["FINE950000001,PATRON_ID01,0000007750,ONLINE,2026-04-01"],
            ["2026-04-01 open", "2026-04-02 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["desk"] == ""

    def test_latest_due_date_still_wins_within_open_window(self):
        """Latest due_date selection from milestone 3 must still apply under window rules."""
        write_inputs(
            [
                "FINE960000001,PATRON_ID01,0000006000,ASSESSED,FRONT,2026-04-02",
                "FINE960000001,PATRON_ID01,0000006000,ASSESSED,FRONT,2026-04-03",
            ],
            ["FINE960000001,PATRON_ID01,0000006000,KSK,2026-04-03"],
            ["2026-04-02 open", "2026-04-03 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["desk"] == "FRONT"
        assert summary["matched_amount_cents"] == 6000

    def test_ksk_alias_still_works_under_configurable_window(self):
        """KSK should still normalize to FRONT when the window and allowlist both pass."""
        write_inputs(
            ["FINE970000001,PATRON_ID01,0000006100,ASSESSED,FRONT,2026-04-03"],
            ["FINE970000001,PATRON_ID01,0000006100,KSK,2026-04-03"],
            ["2026-04-03 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["desk"] == "FRONT"
