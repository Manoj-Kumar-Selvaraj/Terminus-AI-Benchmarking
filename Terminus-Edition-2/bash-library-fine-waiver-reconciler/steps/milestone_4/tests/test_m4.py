"""Milestone 4 verifier tests for config-driven desk allowlists."""

import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCES = APP / "data" / "fines.csv"
ACTIONS = APP / "data" / "waivers.csv"
CHANNELS = APP / "config" / "channels.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "waiver_report.csv"
SUMMARY = APP / "out" / "waiver_summary.json"
DEFAULT_CHANNELS = "desk,enabled\nFRONT,true\nONLINE,true\nMOBILE,true\nKIOSK,false\nOTHER,false\n"


def write_dated_inputs(source_rows, action_rows, channel_rows=None, calendar_rows=None):
    """Replace dated CSV inputs and config for a milestone 4 scenario."""
    SOURCES.write_text("fine_id,patron_id,amount_cents,status,desk,due_date\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text("fine_id,patron_id,amount_cents,desk,waiver_date\n" + "\n".join(action_rows) + "\n")
    CHANNELS.write_text(
        "desk,enabled\n" + "\n".join(channel_rows) + "\n" if channel_rows else DEFAULT_CHANNELS
    )
    CALENDAR.write_text("\n".join(calendar_rows or ["2026-04-01 open"]) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the reconciliation script and return parsed outputs."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone4:
    def test_ksk_alias_matches_front_fine_with_allowlist(self):
        """KSK should canonicalize to FRONT when FRONT is enabled in channels.csv."""
        write_dated_inputs(
            ["FINE810000001,PATRON_ID01,0000004200,ASSESSED,FRONT,2026-04-05"],
            ["FINE810000001,PATRON_ID01,0000004200,KSK,2026-04-03"],
            calendar_rows=["2026-04-03 open", "2026-04-04 open", "2026-04-05 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["desk"] == "FRONT"
        assert summary["matched_count"] == 1

    def test_disabled_kiosk_desk_does_not_match(self):
        """KIOSK is disabled in channels.csv and must not match even when names align."""
        write_dated_inputs(
            ["FINE820000001,PATRON_ID01,0000003300,ASSESSED,KIOSK,2026-04-05"],
            ["FINE820000001,PATRON_ID01,0000003300,KIOSK,2026-04-03"],
            calendar_rows=["2026-04-03 open", "2026-04-04 open", "2026-04-05 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["desk"] == ""
        assert summary["unmatched_amount_cents"] == 3300

    def test_toggling_mobile_off_blocks_mobile_matches(self):
        """MOBILE=false in channels.csv must block an otherwise valid APP alias match."""
        write_dated_inputs(
            ["FINE830000001,PATRON_ID01,0000005000,ASSESSED,MOBILE,2026-04-05"],
            ["FINE830000001,PATRON_ID01,0000005000,APP,2026-04-03"],
            channel_rows=["FRONT,true", "ONLINE,true", "MOBILE,false", "KIOSK,false", "OTHER,false"],
            calendar_rows=["2026-04-03 open", "2026-04-04 open", "2026-04-05 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_enabled_flag_is_case_insensitive(self):
        """Mixed-case enabled values in channels.csv should still allow matching."""
        write_dated_inputs(
            ["FINE835000001,PATRON_ID01,0000005050,ASSESSED,ONLINE,2026-04-05"],
            ["FINE835000001,PATRON_ID01,0000005050,WEB,2026-04-03"],
            channel_rows=["FRONT,TRUE", "ONLINE,TrUe", "MOBILE,tRuE", "KIOSK,false", "OTHER,false"],
            calendar_rows=["2026-04-03 open", "2026-04-04 open", "2026-04-05 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["desk"] == "ONLINE"
        assert summary["matched_amount_cents"] == 5050

    def test_mismatched_desks_still_fail_with_config_allowlist(self):
        """Desk equality must still apply after loading the allowlist from config."""
        write_dated_inputs(
            ["FINE840000001,PATRON_ID01,0000006000,ASSESSED,FRONT,2026-04-05"],
            ["FINE840000001,PATRON_ID01,0000006000,WEB,2026-04-03"],
            calendar_rows=["2026-04-03 open", "2026-04-04 open", "2026-04-05 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["unmatched_amount_cents"] == 6000

    def test_legacy_fr_web_app_aliases_still_work_with_allowlist(self):
        """FR, WEB, and APP aliases should still normalize under the config allowlist."""
        write_dated_inputs(
            [
                "FINE850000001,PATRON_ID01,0000001000,ASSESSED,FRONT,2026-04-03",
                "FINE850000002,PATRON_ID02,0000002000,ASSESSED,ONLINE,2026-04-05",
                "FINE850000003,PATRON_ID03,0000003000,ASSESSED,MOBILE,2026-04-05",
            ],
            [
                "FINE850000001,PATRON_ID01,0000001000,fr,2026-04-03",
                "FINE850000002,PATRON_ID02,0000002000,WEB,2026-04-03",
                "FINE850000003,PATRON_ID03,0000003000,APP,2026-04-03",
            ],
            calendar_rows=["2026-04-03 open", "2026-04-04 open", "2026-04-05 open"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["desk"] for row in rows] == ["FRONT", "ONLINE", "MOBILE"]

    def test_dated_matching_still_uses_desk_allowlist(self):
        """Milestone 3 date gates and milestone 4 allowlist must both apply."""
        write_dated_inputs(
            ["FINE860000001,PATRON_ID01,0000009000,ASSESSED,ONLINE,2026-04-04"],
            ["FINE860000001,PATRON_ID01,0000009000,WEB,2026-04-04"],
            calendar_rows=["2026-04-04 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["desk"] == "ONLINE"
        assert summary["matched_amount_cents"] == 9000
