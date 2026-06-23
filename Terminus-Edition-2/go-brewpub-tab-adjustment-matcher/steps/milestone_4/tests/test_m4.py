"""Milestone 4 verifier tests for method-gated tab adjustment reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
TABS = APP / "data" / "tabs.csv"
ADJUSTMENTS = APP / "data" / "adjustments.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
METHODS = APP / "config" / "methods.csv"
REPORT = APP / "out" / "tab_adjustment_report.csv"
SUMMARY = APP / "out" / "tab_adjustment_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go tab adjustment CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the reconciliation CLI once for all milestone 4 tests."""
    build_program()


def write_inputs(tab_rows, adjustment_rows, calendar_rows, method_rows):
    """Replace inputs, calendar, and method config for a method-gated scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    TABS.write_text("tab_id,patron_id,amount_cents,status,pour_tier,tab_date\n" + "\n".join(tab_rows) + "\n")
    ADJUSTMENTS.write_text(
        "tab_id,patron_id,amount_cents,pour_tier,adjust_date,adjust_method\n"
        + "\n".join(adjustment_rows)
        + "\n"
    )
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    METHODS.write_text("method,enabled\n" + "\n".join(method_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone4:
    """Method gates must compose with date, alias, and consumption rules."""

    def test_enabled_methods_match_with_aliases_dates_and_case_folding(self):
        """Enabled adjustment methods should be trimmed/case-folded while aliases and dates still apply."""
        write_inputs(
            [
                "TABM401,CUSTM401,1100,COMPLETED,PINT,2026-04-09",
                "TABM402,CUSTM402,2200,COMPLETED,PITCH,2026-04-10",
                "TABM403,CUSTM403,3300,COMPLETED,KEG,2026-04-11",
            ],
            [
                "TABM401,CUSTM401,1100,PT,2026-04-05, cash ",
                "TABM402,CUSTM402,2200,pc,2026-04-06,CARD",
                "TABM403,CUSTM403,3300,kg,2026-04-07,Card",
            ],
            ["2026-04-05 open", "2026-04-06 open", "2026-04-07 open"],
            [" CASH , TRUE ", "card,true", "house,false"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["pour_tier"] for row in rows] == ["PINT", "PITCH", "KEG"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 6600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_disabled_missing_blank_and_malformed_methods_are_ineligible(self):
        """Only methods configured with enabled exactly true should be eligible."""
        write_inputs(
            [
                "TABM411,CUSTM411,100,COMPLETED,PINT,2026-04-09",
                "TABM412,CUSTM412,200,COMPLETED,PITCH,2026-04-09",
                "TABM413,CUSTM413,300,COMPLETED,KEG,2026-04-09",
                "TABM414,CUSTM414,400,COMPLETED,PINT,2026-04-09",
                "TABM415,CUSTM415,500,COMPLETED,PITCH,2026-04-09",
            ],
            [
                "TABM411,CUSTM411,100,PINT,2026-04-05,HOUSE",
                "TABM412,CUSTM412,200,PC,2026-04-05,MANAGER",
                "TABM413,CUSTM413,300,KG,2026-04-05,",
                "TABM414,CUSTM414,400,PINT,2026-04-05,PROMO",
                "TABM415,CUSTM415,500,PC,2026-04-05,CARD",
            ],
            ["2026-04-05 open"],
            ["HOUSE,false", "PROMO,yes", "CARD,true"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert [row["pour_tier"] for row in rows] == ["", "", "", "", "PITCH"]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 500,
            "unmatched_count": 4,
            "unmatched_amount_cents": 1000,
        }

    def test_enabled_method_does_not_bypass_prior_status_amount_or_date_gates(self):
        """The method gate is additive and must not override status, amount, or calendar failures."""
        write_inputs(
            [
                "TABM421,CUSTM421,700,DRAFT,PINT,2026-04-09",
                "TABM422,CUSTM422,800,COMPLETED,PITCH,2026-04-09",
                "TABM423,CUSTM423,900,COMPLETED,KEG,2026-04-04",
                "TABM424,CUSTM424,1000,COMPLETED,PINT,2026-04-10",
            ],
            [
                "TABM421,CUSTM421,700,PINT,2026-04-05,CARD",
                "TABM422,CUSTM422,801,PC,2026-04-05,CARD",
                "TABM423,CUSTM423,900,KG,2026-04-06,CARD",
                "TABM424,CUSTM424,1000,PINT,2026-04-07,CARD",
            ],
            ["2026-04-05 open", "2026-04-06 open", "2026-04-07 closed"],
            ["CARD,true"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert [row["pour_tier"] for row in rows] == ["", "", "", ""]
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 3401

    def test_absent_adjust_method_column_preserves_milestone3_behavior(self):
        """If the adjust_method column is absent, milestone 3 behavior should still work."""
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        TABS.write_text(
            "tab_id,patron_id,amount_cents,status,pour_tier,tab_date\n"
            "TABM441,CUSTM441,900,COMPLETED,PINT,2026-04-09\n"
        )
        ADJUSTMENTS.write_text(
            "tab_id,patron_id,amount_cents,pour_tier,adjust_date\n"
            "TABM441,CUSTM441,900,PT,2026-04-05\n"
        )
        CALENDAR.write_text("2026-04-05 open\n")
        METHODS.write_text("method,enabled\nCARD,true\n")
        REPORT.unlink(missing_ok=True)
        SUMMARY.unlink(missing_ok=True)

        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["pour_tier"] == "PINT"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 900,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_report_schema_omits_adjust_method_column(self):
        """Method-gated batches must not add adjust_method to the report CSV."""
        write_inputs(
            ["TABM441,CUSTM441,900,COMPLETED,PINT,2026-04-09"],
            ["TABM441,CUSTM441,900,PT,2026-04-05,CARD"],
            ["2026-04-05 open"],
            ["CARD,true"],
        )
        rows, summary = run_program()

        assert list(rows[0].keys()) == ["tab_id", "patron_id", "pour_tier", "amount_cents", "status"]
        assert rows[0]["status"] == "MATCHED"

    def test_enabled_method_rejects_wrong_pour_tier(self):
        """An enabled method must not bypass the pour_tier equality gate."""
        write_inputs(
            ["TABM442,CUSTM442,700,COMPLETED,PINT,2026-04-09"],
            ["TABM442,CUSTM442,700,KEG,2026-04-05,CARD"],
            ["2026-04-05 open"],
            ["CARD,true"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["pour_tier"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 700,
        }

    def test_unlisted_adjustment_method_is_not_eligible(self):
        """An adjustment method absent from methods.csv must not match."""
        write_inputs(
            ["TABM451,CUSTM451,650,COMPLETED,PINT,2026-04-09"],
            ["TABM451,CUSTM451,650,PT,2026-04-05,LOYALTY"],
            ["2026-04-05 open"],
            ["CARD,true"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert summary["unmatched_amount_cents"] == 650

    def test_method_gate_preserves_latest_date_selection_and_row_consumption(self):
        """An enabled method should still select the latest eligible tab row and consume rows once."""
        write_inputs(
            [
                "TABM431,CUSTM431,1200,COMPLETED,PITCH,2026-04-06",
                "TABM431,CUSTM431,1200,COMPLETED,PITCH,2026-04-08",
                "TABM431,CUSTM431,1200,COMPLETED,PITCH,2026-04-08",
            ],
            [
                "TABM431,CUSTM431,1200,PC,2026-04-05,CARD",
                "TABM431,CUSTM431,1200,PC,2026-04-05,CARD",
                "TABM431,CUSTM431,1200,PC,2026-04-05,CARD",
                "TABM431,CUSTM431,1200,PC,2026-04-05,CARD",
            ],
            ["2026-04-05 open"],
            ["CARD,true"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["pour_tier"] for row in rows] == ["PITCH", "PITCH", "PITCH", ""]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 3600,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1200,
        }
