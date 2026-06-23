"""Milestone 5 tests for donor-limit gated charity matching."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "pledges.csv"
ACTIONS = APP / "data" / "adjustments.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
METHODS = APP / "config" / "methods.csv"
DONOR_LIMITS = APP / "config" / "donor_limits.csv"
REPORT = APP / "out" / "adjustment_report.csv"
SUMMARY = APP / "out" / "adjustment_summary.json"


def write_inputs(source_rows, action_rows, calendar_rows, methods_rows, donor_limit_rows, dated=True):
    """Write focused CSV scenarios with calendar, methods, and donor-limit config."""
    source_header = "pledge_id,donor_id,amount_cents,status,fund" + (",pledge_due" if dated else "")
    action_header = "pledge_id,donor_id,amount_cents,fund" + (",adjustment_date" if dated else "")
    SOURCE.write_text(source_header + "\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text(action_header + "\n" + "\n".join(action_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    METHODS.write_text("fund,enabled\n" + "\n".join(methods_rows) + "\n")
    DONOR_LIMITS.write_text("donor_id,fund,max_adjustment_cents,enabled\n" + "\n".join(donor_limit_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run ruby batch and parse report/summary."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone5:
    """Milestone 5 verifies donor_limits.csv caps, trimming, case-insensitive policy parsing, overrides, and prior gates."""

    def test_donor_limit_required_after_fund_alias_and_amount_cap(self):
        """Donor/fund policy must be present, enabled, alias-aware, and cap the adjustment amount."""
        write_inputs(
            [
                "M5101,DON5101,1000,BOOKED,GENERAL,2026-05-10",
                "M5102,DON5102,2000,BOOKED,CAPITAL,2026-05-10",
                "M5103,DON5103,3000,BOOKED,RELIEF,2026-05-10",
            ],
            [
                "M5101,DON5101,1000,GEN,2026-05-09",
                "M5102,DON5102,2000,CAP,2026-05-09",
                "M5103,DON5103,3000,REL,2026-05-09",
            ],
            ["2026-05-09 open"],
            ["GENERAL,true", "CAPITAL,true", "RELIEF,true"],
            ["DON5101,GENERAL,1000,true", "DON5102,CAP,1500,true", "DON5103,REL,3000,true"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["fund"] for row in rows] == ["GENERAL", "", "RELIEF"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 4000,
            "unmatched_count": 1,
            "unmatched_amount_cents": 2000,
        }

    def test_last_well_formed_donor_limit_row_is_authoritative(self):
        """A later disabled well-formed row must override an earlier enabled row and block matching."""
        write_inputs(
            [
                "M5201,DON5201,1500,BOOKED,GENERAL,2026-05-10",
                "M5202,DON5202,800,BOOKED,RELIEF,2026-05-10",
            ],
            [
                "M5201,DON5201,1500,GEN,2026-05-09",
                "M5202,DON5202,800,REL,2026-05-09",
            ],
            ["2026-05-09 open"],
            ["GENERAL,true", "RELIEF,true"],
            [
                "DON5201,GENERAL,1000,true",
                "DON5201,GEN,2000,true",
                "DON5202,RELIEF,1000,true",
                "DON5202,REL,0,false",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["fund"] for row in rows] == ["GENERAL", ""]
        assert summary["matched_amount_cents"] == 1500
        assert summary["unmatched_amount_cents"] == 800

    def test_missing_blank_malformed_and_non_integer_limit_rows_are_ineligible(self):
        """Malformed, incomplete, or short donor-limit rows must not enable matching and must not crash."""
        write_inputs(
            [
                "M5301,DON5301,700,BOOKED,GENERAL,2026-05-10",
                "M5302,DON5302,800,BOOKED,CAPITAL,2026-05-10",
                "M5303,DON5303,900,BOOKED,RELIEF,2026-05-10",
            ],
            [
                "M5301,DON5301,700,GEN,2026-05-09",
                "M5302,DON5302,800,CAP,2026-05-09",
                "M5303,DON5303,900,REL,2026-05-09",
            ],
            ["2026-05-09 open"],
            ["GENERAL,true", "CAPITAL,true", "RELIEF,true"],
            [
                ",GENERAL,1000,true",
                "DON5301,,1000,true",
                "DON5301,GENERAL",
                "DON5302,CAP,abc,true",
                "DON5302,CAP,500",
                "DON5303,REL,900,true",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "MATCHED"]
        assert [row["fund"] for row in rows] == ["", "", "RELIEF"]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 900,
            "unmatched_count": 2,
            "unmatched_amount_cents": 1500,
        }

    def test_donor_limit_gate_applies_in_undated_mode(self):
        """Donor limits are required even when the legacy undated path skips calendar gating."""
        write_inputs(
            ["M5401,DON5401,600,BOOKED,GENERAL", "M5402,DON5402,700,BOOKED,CAPITAL"],
            ["M5401,DON5401,600,GEN", "M5402,DON5402,700,CAP"],
            ["2026-05-09 open"],
            ["GENERAL,true", "CAPITAL,true"],
            ["DON5401,GENERAL,500,true", "DON5402,CAPITAL,700,true"],
            dated=False,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert [row["fund"] for row in rows] == ["", "CAPITAL"]
        assert summary["matched_amount_cents"] == 700
        assert summary["unmatched_amount_cents"] == 600

    def test_donor_limits_do_not_bypass_methods_or_closed_calendar(self):
        """Enabled donor limits cannot override disabled methods or closed adjustment dates."""
        write_inputs(
            [
                "M5501,DON5501,400,BOOKED,GENERAL,2026-05-10",
                "M5502,DON5502,500,BOOKED,CAPITAL,2026-05-10",
            ],
            [
                "M5501,DON5501,400,GEN,2026-05-09",
                "M5502,DON5502,500,CAP,2026-05-08",
            ],
            ["2026-05-09 open", "2026-05-08 closed"],
            ["GENERAL,false", "CAPITAL,true"],
            ["DON5501,GENERAL,400,true", "DON5502,CAPITAL,500,true"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert [row["fund"] for row in rows] == ["", ""]
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_donor_limit_preserves_latest_due_selection_and_row_consumption(self):
        """The donor gate must preserve latest-due selection and row-position consumption."""
        write_inputs(
            [
                "M5601,DON5601,1000,BOOKED,CAPITAL,2026-05-05",
                "M5601,DON5601,1000,BOOKED,CAPITAL,2026-05-10",
            ],
            [
                "M5601,DON5601,1000,CAP,2026-05-04",
                "M5601,DON5601,1000,CAP,2026-05-08",
            ],
            ["2026-05-04 open", "2026-05-08 open"],
            ["CAPITAL,true"],
            ["DON5601,CAP,1000,true"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["fund"] for row in rows] == ["CAPITAL", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1000,
        }

    def test_negative_and_blank_maximum_amounts_do_not_enable_matching(self):
        """Blank or negative maximum amounts must be treated as ineligible policy rows."""
        write_inputs(
            ["M5701,DON5701,100,BOOKED,GENERAL,2026-05-10", "M5702,DON5702,200,BOOKED,RELIEF,2026-05-10"],
            ["M5701,DON5701,100,GEN,2026-05-09", "M5702,DON5702,200,REL,2026-05-09"],
            ["2026-05-09 open"],
            ["GENERAL,true", "RELIEF,true"],
            ["DON5701,GENERAL,,true", "DON5702,RELIEF,-1,true"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 2,
            "unmatched_amount_cents": 300,
        }

    def test_trimmed_donor_id_and_case_insensitive_enabled_policy_match(self):
        """Donor-limit donor_id and enabled fields should be trimmed and compared case-insensitively."""
        write_inputs(
            [
                "M5801,DON5801,1000,BOOKED,GENERAL,2026-05-10",
                "M5802,DON5802,2000,BOOKED,CAPITAL,2026-05-10",
            ],
            [
                "M5801,DON5801,1000,GEN,2026-05-09",
                "M5802,DON5802,2000,CAP,2026-05-09",
            ],
            ["2026-05-09 open"],
            ["GENERAL,true", "CAPITAL,true"],
            [" DON5801 , GENERAL , 1000 , TRUE ", "DON5802,CAP,2000, True "],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["fund"] for row in rows] == ["GENERAL", "CAPITAL"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 3000,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

