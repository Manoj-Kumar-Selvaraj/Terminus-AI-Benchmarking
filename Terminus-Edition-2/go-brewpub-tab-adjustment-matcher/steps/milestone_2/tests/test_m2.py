"""Verifier tests for the tab adjustment reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
TABS = APP / "data" / "tabs.csv"
ADJUSTMENTS = APP / "data" / "adjustments.csv"
REPORT = APP / "out" / "tab_adjustment_report.csv"
SUMMARY = APP / "out" / "tab_adjustment_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go reconciliation CLI for the current source tree."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all verifier tests."""
    build_program()


def write_inputs(tab_rows, adjustment_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    TABS.write_text("tab_id,patron_id,amount_cents,status,pour_tier\n" + "\n".join(tab_rows) + "\n")
    ADJUSTMENTS.write_text("tab_id,patron_id,amount_cents,pour_tier\n" + "\n".join(adjustment_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())




class TestMilestone2:
    """Behavior checks for milestone 2."""

    def test_pitch_adjustment_matches_and_counts_positive_amount(self):
        """PITCH adjustments should match completed tabs and add positive cents to matched totals."""
        write_inputs(
            [
                "TAB20260401001,CUST1001,12500,COMPLETED,PINT",
                "TAB20260401002,CUST1002,9900,COMPLETED,PITCH",
            ],
            [
                "TAB20260401001,CUST1001,12500,PINT",
                "TAB20260401002,CUST1002,9900,PITCH",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["pour_tier"] == "PITCH"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 22400
        assert summary["unmatched_count"] == 0


    def test_tab_id_match_uses_full_identifier(self):
        """An adjustment must not match a tab that only shares the leading tab_id prefix."""
        write_inputs(
            [
                "TAB777770001,CUST2001,3300,COMPLETED,PINT",
                "TAB777770002,CUST2001,3300,COMPLETED,PINT",
            ],
            [
                "TAB777770003,CUST2001,3300,PINT",
                "TAB777770002,CUST2001,3300,PINT",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["pour_tier"] == ""
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300


    def test_customer_amount_status_and_pour_tier_all_gate_matching(self):
        """Customer, amount, completed status, and allowed pour_tier must all be satisfied."""
        write_inputs(
            [
                "TAB3001,CUST3001,1000,COMPLETED,PINT",
                "TAB3002,CUST3002,2000,COMPLETED,PITCH",
                "TAB3003,CUST3003,3000,DRAFT,KEG",
                "TAB3004,CUST3004,4000,COMPLETED,CHECK",
                "TAB3005,CUST3005,5000,COMPLETED,KEG",
            ],
            [
                "TAB3001,CUST9999,1000,PINT",
                "TAB3002,CUST3002,2100,PITCH",
                "TAB3003,CUST3003,3000,KEG",
                "TAB3004,CUST3004,4000,CHECK",
                "TAB3005,CUST3005,5000,KEG",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["pour_tier"] == "KEG"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_count"] == 4
        assert summary["unmatched_amount_cents"] == 10100


    def test_matched_report_emits_canonical_pour_tier_from_alias(self):
        """A PC adjustment should match a PITCH tab and report canonical PITCH."""
        write_inputs(
            ["TAB8053,CUST8053,4200,COMPLETED,PITCH"],
            ["TAB8053,CUST8053,4200,PC"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["pour_tier"] == "PITCH"

    def test_duplicate_adjustments_do_not_reuse_consumed_tab_row(self):
        """Only the earliest eligible adjustment may consume a matching tab row."""
        write_inputs(
            [
                "TAB5551,CUST5551,7500,COMPLETED,PITCH",
                "TAB5552,CUST5552,8800,COMPLETED,PINT",
            ],
            [
                "TAB5551,CUST5551,7500,PITCH",
                "TAB5551,CUST5551,7500,PITCH",
                "TAB5552,CUST5552,8800,PINT",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["pour_tier"] == ""
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 16300
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 7500


    def test_matching_trims_fields_and_normalizes_pour_tier_status_case(self):
        """Matching should tolerate surrounding spaces and case differences in pour_tier/status values."""
        write_inputs(
            [
                " TAB6601 , CUST6601 , 6100 , completed , pint ",
                "TAB6602,CUST6602,7200,COMPLETED,keg",
            ],
            [
                "TAB6601,CUST6601, 6100 ,PINT",
                " TAB6602 , CUST6602 ,7200, KEG ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["tab_id"] for row in rows] == ["TAB6601", "TAB6602"]
        assert [row["patron_id"] for row in rows] == ["CUST6601", "CUST6602"]
        assert [row["pour_tier"] for row in rows] == ["PINT", "KEG"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 13300


    def test_pour_tier_alias_trims_surrounding_spaces(self):
        """Legacy aliases with surrounding spaces should still canonicalize and match."""
        write_inputs(
            ["TAB7751,CUST7751,4100,COMPLETED,PINT"],
            ["TAB7751,CUST7751,4100, pt "],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["pour_tier"] == "PINT"
        assert summary["matched_count"] == 1

    def test_legacy_pour_tier_aliases_match_and_emit_canonical_pour_tiers(self):
        """Legacy PT, PC, and KG adjustment pour tiers should match and report canonical pour tiers."""
        write_inputs(
            [
                "TAB7701,CUST7701,8800,COMPLETED,PITCH",
                "TAB7702,CUST7702,9100,completed,keg",
                "TAB7703,CUST7703,4200,COMPLETED,PINT",
                "TAB7704,CUST7704,3300,COMPLETED,CHECK",
            ],
            [
                "TAB7701,CUST7701,8800,pc",
                "TAB7702,CUST7702,9100,KG",
                "TAB7703,CUST7703,4200,PT",
                "TAB7704,CUST7704,3300,chk",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["pour_tier"] for row in rows] == ["PITCH", "KEG", "PINT", ""]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 22100
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 3300


    def test_report_schema_and_adjustment_input_order_are_stable(self):
        """The report should use the required schema and preserve adjustment input order."""
        write_inputs(
            [
                "TAB9001,CUST9001,100,COMPLETED,PINT",
                "TAB9002,CUST9002,200,COMPLETED,PITCH",
                "TAB9003,CUST9003,300,COMPLETED,KEG",
            ],
            [
                "TAB9003,CUST9003,300,KEG",
                "TAB9001,CUST9001,100,PINT",
                "TAB9002,CUST9002,200,PITCH",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "tab_id,patron_id,pour_tier,amount_cents,status"
        assert [row["tab_id"] for row in rows] == ["TAB9003", "TAB9001", "TAB9002"]
        assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
        assert set(summary.keys()) == {
            "matched_count",
            "matched_amount_cents",
            "unmatched_count",
            "unmatched_amount_cents",
        }
        assert all(isinstance(summary[key], int) for key in summary)
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_empty_adjustments_file_produces_empty_report_and_zero_summary(self):
        """An adjustments file with only the header should produce no report rows and zero totals."""
        write_inputs(
            ["TABEMPTY1,CUSTEMPTY1,100,COMPLETED,PINT"],
            [],
        )
        rows, summary = run_program()

        assert rows == []
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_empty_tabs_file_keeps_adjustments_unmatched_with_positive_totals(self):
        """A tabs file with only the header should leave adjustments unmatched."""
        write_inputs(
            [],
            ["TABEMPTY2,CUSTEMPTY2,250,PT", "TABEMPTY3,CUSTEMPTY3,350,PC"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert summary["unmatched_amount_cents"] == 600
