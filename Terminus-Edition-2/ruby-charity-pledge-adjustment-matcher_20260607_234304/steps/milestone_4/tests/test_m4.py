"""Milestone 4 verifier tests for methods-config gated charity matching."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "pledges.csv"
ACTIONS = APP / "data" / "adjustments.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
METHODS = APP / "config" / "methods.csv"
REPORT = APP / "out" / "adjustment_report.csv"
SUMMARY = APP / "out" / "adjustment_summary.json"


def write_inputs(source_rows, action_rows, calendar_rows, methods_rows, dated=True):
    """Write focused CSV scenarios with calendar and methods config."""
    source_header = "pledge_id,donor_id,amount_cents,status,fund" + (",pledge_due" if dated else "")
    action_header = "pledge_id,donor_id,amount_cents,fund" + (",adjustment_date" if dated else "")
    SOURCE.write_text(source_header + "\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text(action_header + "\n" + "\n".join(action_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    METHODS.write_text("fund,enabled\n" + "\n".join(methods_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run ruby batch and parse report/summary."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone4:
    """Milestone 4 verifies methods.csv eligibility in dated and undated modes without regressing prior behavior."""

    def test_enabled_true_required_after_alias_normalization(self):
        """Alias-normalized fund must be enabled=true in methods config."""
        write_inputs(
            [
                "M4101,DON4101,1000,BOOKED,GENERAL,2026-05-08",
                "M4102,DON4102,2000,BOOKED,CAPITAL,2026-05-08",
                "M4103,DON4103,3000,BOOKED,RELIEF,2026-05-08",
            ],
            [
                "M4101,DON4101,1000,GEN,2026-05-07",
                "M4102,DON4102,2000,CAP,2026-05-07",
                "M4103,DON4103,3000,REL,2026-05-07",
            ],
            ["2026-05-07 open"],
            ["GENERAL,true", "CAPITAL,false", "RELIEF,true"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert [r["fund"] for r in rows] == ["GENERAL", "", "RELIEF"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 4000,
            "unmatched_count": 1,
            "unmatched_amount_cents": 2000,
        }


    def test_missing_methods_row_makes_fund_ineligible(self):
        """If canonical fund is absent from methods.csv it should be rejected."""
        write_inputs(
            ["M4201,DON4201,900,BOOKED,CAPITAL,2026-05-10"],
            ["M4201,DON4201,900,CAP,2026-05-09"],
            ["2026-05-09 open"],
            ["GENERAL,true", "RELIEF,true"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["fund"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_methods_gate_preserves_full_pledge_id_matching(self):
        """Enabled methods must not allow prefix pledge_id matching regressions."""
        write_inputs(
            [
                "PREFIX990001,DON9901,1250,BOOKED,GENERAL,2026-05-10",
                "PREFIX990002,DON9901,1250,BOOKED,GENERAL,2026-05-10",
            ],
            [
                "PREFIX990003,DON9901,1250,GEN,2026-05-09",
                "PREFIX990002,DON9901,1250,GEN,2026-05-09",
            ],
            ["2026-05-09 open"],
            ["GENERAL,true"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert [row["fund"] for row in rows] == ["", "GENERAL"]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1250,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1250,
        }


    def test_malformed_and_non_boolean_methods_rows_do_not_enable(self):
        """Malformed rows and non-true flags must not permit matching."""
        write_inputs(
            ["M4301,DON4301,700,BOOKED,RELIEF,2026-05-10"],
            ["M4301,DON4301,700,REL,2026-05-09"],
            ["2026-05-09 open"],
            ["RELIEF,yes", "BROKENROW", "GENERAL,true"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["fund"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 700,
        }


    def test_methods_gate_also_applies_in_undated_mode(self):
        """Even without date columns, enabled fund in methods.csv is required."""
        write_inputs(
            ["M4401,DON4401,800,BOOKED,GENERAL"],
            ["M4401,DON4401,800,GEN"],
            ["2026-05-01 open"],
            ["GENERAL,false"],
            dated=False,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["fund"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1


    def test_enabled_field_case_insensitive_and_whitespace_tolerant(self):
        """methods.csv enabled values must be parsed case-insensitively with surrounding whitespace trimmed."""
        write_inputs(
            ["M4601,DON4601,500,BOOKED,GENERAL,2026-05-08"],
            ["M4601,DON4601,500,GEN,2026-05-07"],
            ["2026-05-07 open"],
            ["GENERAL, TRUE"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["fund"] == "GENERAL"
        assert summary["matched_count"] == 1


    def test_methods_gate_does_not_override_closed_calendar_rule(self):
        """Enabled methods alone cannot bypass dated open-calendar requirement."""
        write_inputs(
            ["M4501,DON4501,1500,BOOKED,CAPITAL,2026-05-12"],
            ["M4501,DON4501,1500,CAP,2026-05-10"],
            ["2026-05-10 closed"],
            ["CAPITAL,true"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["fund"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 1500


    def test_methods_config_fund_aliases_and_input_whitespace_are_normalized(self):
        """methods.csv aliases and incidental input whitespace should normalize before matching."""
        write_inputs(
            [" M4701 , DON4701 , 1100 , booked , general ,2026-05-08"],
            [" M4701 , DON4701 , 1100 , gen ,2026-05-07"],
            ["2026-05-07 open"],
            [" gen , TRUE "],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["fund"] == "GENERAL"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1100,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }


    def test_blank_fund_and_missing_enabled_methods_rows_do_not_enable(self):
        """Blank fund names and missing enabled values in methods.csv should be ignored safely."""
        write_inputs(
            [
                "M4801,DON4801,600,BOOKED,GENERAL,2026-05-08",
                "M4802,DON4802,700,BOOKED,RELIEF,2026-05-08",
            ],
            [
                "M4801,DON4801,600,GEN,2026-05-07",
                "M4802,DON4802,700,REL,2026-05-07",
            ],
            ["2026-05-07 open"],
            [",true", "GENERAL,", "RELIEF,true"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert [row["fund"] for row in rows] == ["", "RELIEF"]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 700,
            "unmatched_count": 1,
            "unmatched_amount_cents": 600,
        }
