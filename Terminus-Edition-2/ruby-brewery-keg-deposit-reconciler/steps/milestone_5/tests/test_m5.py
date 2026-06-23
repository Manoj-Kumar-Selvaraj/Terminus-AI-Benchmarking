
"""Milestone 5 verifier tests for configurable deposit open-day windows."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "kegs.csv"
ACTIONS = APP / "data" / "deposits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
PROFILE = APP / "config" / "run_profile.ini"
REPORT = APP / "out" / "deposit_report.csv"
SUMMARY = APP / "out" / "deposit_summary.json"


def write_inputs(source_rows, action_rows, calendar_rows, dated=True, window_days=2):
    """Replace dated CSV inputs, calendar, and deposit window setting."""
    source_header = "keg_id,distributor_id,amount_cents,status,keg_type,return_date"
    action_header = "keg_id,distributor_id,amount_cents,keg_type,deposit_date"
    SOURCE.write_text(source_header + "\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text(action_header + "\n" + "\n".join(action_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    base = PROFILE.read_text(encoding="utf-8")
    lines = [line for line in base.splitlines() if not line.startswith("deposit_open_window_days=")]
    lines.append(f"deposit_open_window_days={window_days}")
    PROFILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the Ruby batch and return parsed report and summary outputs."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone5:
    """Configurable open-day window after deposit_date through return_date."""

    def test_two_open_days_after_deposit_is_eligible_with_default_window(self):
        """Exactly two open days after deposit_date through return_date should match when window is 2."""
        write_inputs(
            ["WIN1001,DIST1001,1200,RETURNED,HALF,2026-04-04"],
            ["WIN1001,DIST1001,1200,HALF,2026-04-01"],
            ["2026-04-01 open", "2026-04-02 open", "2026-04-03 closed", "2026-04-04 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["keg_type"] == "HALF"
        assert summary["matched_count"] == 1

    def test_three_open_days_after_deposit_exceeds_default_window(self):
        """Three strictly-after open days should fail the default deposit_open_window_days=2 rule."""
        write_inputs(
            ["WIN2001,DIST2001,1300,RETURNED,SIXTH,2026-04-04"],
            ["WIN2001,DIST2001,1300,SIX,2026-04-01"],
            ["2026-04-01 open", "2026-04-02 open", "2026-04-03 open", "2026-04-04 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["keg_type"] == ""
        assert summary["matched_count"] == 0

    def test_equal_deposit_and_return_dates_count_zero_open_days_after(self):
        """Same-day deposit and return dates should count zero window days and still match."""
        write_inputs(
            ["WIN3001,DIST3001,650,RETURNED,CORNELIUS,2026-04-05"],
            ["WIN3001,DIST3001,650,COR,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["keg_type"] == "CORNELIUS"

    def test_tighter_window_from_run_profile_blocks_wider_span(self):
        """deposit_open_window_days=1 should reject two open days after deposit_date."""
        write_inputs(
            ["WIN4001,DIST4001,500,RETURNED,HALF,2026-04-03"],
            ["WIN4001,DIST4001,500,HLF,2026-04-01"],
            ["2026-04-01 open", "2026-04-02 open", "2026-04-03 open"],
            window_days=1,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"

    def test_window_does_not_bypass_keg_type_equality(self):
        """A valid open-day window must not match when keg types differ after canonicalization."""
        write_inputs(
            ["WIN5001,DIST5001,775,RETURNED,HALF,2026-04-02"],
            ["WIN5001,DIST5001,775,SIX,2026-04-01"],
            ["2026-04-01 open", "2026-04-02 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["keg_type"] == ""

    def test_latest_return_date_still_wins_within_open_window(self):
        """Latest return_date selection from milestone 3 must still apply under window rules."""
        write_inputs(
            [
                "WIN6001,DIST6001,600,RETURNED,HALF,2026-04-02",
                "WIN6001,DIST6001,600,RETURNED,HALF,2026-04-03",
            ],
            ["WIN6001,DIST6001,600,HLF,2026-04-03"],
            ["2026-04-02 open", "2026-04-03 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["keg_type"] == "HALF"
        assert summary["matched_amount_cents"] == 600

    def test_six_alias_still_works_under_configurable_window(self):
        """SIX should still normalize to SIXTH when the window and allowlist both pass."""
        write_inputs(
            ["WIN7001,DIST7001,610,RETURNED,SIXTH,2026-04-03"],
            ["WIN7001,DIST7001,610,SIX,2026-04-03"],
            ["2026-04-03 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["keg_type"] == "SIXTH"
