"""Milestone 4 verifier tests for config-driven reason allowlists."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
ACCRUALS = APP / "data" / "accruals.csv"
ADJUSTMENTS = APP / "data" / "adjustments.csv"
REASONS = APP / "config" / "reasons.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "adjustment_report.csv"
SUMMARY = APP / "out" / "adjustment_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")
DEFAULT_REASONS = "reason,enabled\nPURCHASE,true\nBONUS,true\nPROMO,true\nCHECK,false\n"


def build_program():
    """Compile the Go adjustment reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 4 tests."""
    build_program()


def write_inputs(accrual_rows, adjustment_rows, reason_rows=None, calendar_rows=None):
    """Replace CSV inputs and optional config files for a scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    ACCRUALS.write_text("accrual_id,member_id,amount_cents,status,reason\n" + "\n".join(accrual_rows) + "\n")
    ADJUSTMENTS.write_text("accrual_id,member_id,amount_cents,reason\n" + "\n".join(adjustment_rows) + "\n")
    if reason_rows is not None:
        REASONS.write_text("reason,enabled\n" + "\n".join(reason_rows) + "\n")
    else:
        REASONS.write_text(DEFAULT_REASONS)
    if calendar_rows is not None:
        CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_dated_inputs(accrual_rows, adjustment_rows, reason_rows=None, calendar_rows=None):
    """Replace dated CSV inputs and config for milestone 4 scenarios."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    ACCRUALS.write_text("accrual_id,member_id,amount_cents,status,reason,earn_date\n" + "\n".join(accrual_rows) + "\n")
    ADJUSTMENTS.write_text(
        "accrual_id,member_id,amount_cents,reason,adjustment_date\n" + "\n".join(adjustment_rows) + "\n"
    )
    if reason_rows is not None:
        REASONS.write_text("reason,enabled\n" + "\n".join(reason_rows) + "\n")
    else:
        REASONS.write_text(DEFAULT_REASONS)
    if calendar_rows is not None:
        CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse its CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone4:
    """Config-driven reason allowlist and PUR alias behavior."""

    def test_pur_alias_matches_purchase_accrual(self):
        """PUR should canonicalize to PURCHASE when PURCHASE is enabled in reasons.csv."""
        write_dated_inputs(
            ["INV8101,CUST8101,4200,POSTED,PURCHASE,2026-04-03"],
            ["INV8101,CUST8101,4200,PUR,2026-04-05"],
            calendar_rows=["2026-04-03 open", "2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["reason"] == "PURCHASE"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 4200

    def test_disabled_check_reason_does_not_match(self):
        """CHECK is disabled in reasons.csv and must not match even when names align."""
        write_dated_inputs(
            ["INV8201,CUST8201,3300,POSTED,CHECK,2026-04-03"],
            ["INV8201,CUST8201,3300,CHECK,2026-04-05"],
            calendar_rows=["2026-04-03 open", "2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["reason"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 3300

    def test_toggling_bonus_off_blocks_bonus_matches(self):
        """A reason disabled in reasons.csv must block otherwise valid matches."""
        write_dated_inputs(
            ["INV8301,CUST8301,5000,POSTED,BONUS,2026-04-03"],
            ["INV8301,CUST8301,5000,BNS,2026-04-05"],
            reason_rows=[
                "PURCHASE,true",
                "BONUS,false",
                "PROMO,true",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["reason"] == ""
        assert summary["matched_count"] == 0

    def test_mismatched_reasons_still_fail_with_config_allowlist(self):
        """Reason equality must still apply after loading the allowlist from config."""
        write_inputs(
            ["INV8401,CUST8401,6000,POSTED,PURCHASE"],
            ["INV8401,CUST8401,6000,BONUS"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert summary["unmatched_amount_cents"] == 6000

    def test_dated_matching_still_uses_reason_allowlist(self):
        """Milestone 3 date gates and milestone 4 allowlist must both apply."""
        write_dated_inputs(
            ["FILL8401,MEM8401,900,POSTED,PURCHASE,2026-04-03"],
            ["FILL8401,MEM8401,900,PUR,2026-04-04"],
            calendar_rows=["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["reason"] == "PURCHASE"
        assert summary["matched_count"] == 1

    def test_legacy_bns_prm_aliases_still_work_with_allowlist(self):
        """BNS and PRM aliases should still normalize under the config allowlist."""
        write_dated_inputs(
            [
                "INV8501,CUST8501,1000,POSTED,BONUS,2026-04-03",
                "INV8502,CUST8502,2000,POSTED,PROMO,2026-04-04",
            ],
            [
                "INV8501,CUST8501,1000,BNS,2026-04-05",
                "INV8502,CUST8502,2000,PRM,2026-04-05",
            ],
            calendar_rows=["2026-04-03 open", "2026-04-04 open", "2026-04-05 open"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["reason"] for row in rows] == ["BONUS", "PROMO"]
        assert summary["matched_count"] == 2

    def test_enabled_flag_is_case_insensitive(self):
        """reasons.csv enabled values must be treated as true case-insensitively."""
        write_dated_inputs(
            [
                "INV8601,CUST8601,1100,POSTED,PURCHASE,2026-04-03",
                "INV8602,CUST8602,1200,POSTED,BONUS,2026-04-03",
                "INV8603,CUST8603,1300,POSTED,PROMO,2026-04-03",
            ],
            [
                "INV8601,CUST8601,1100,PUR,2026-04-05",
                "INV8602,CUST8602,1200,BNS,2026-04-05",
                "INV8603,CUST8603,1300,PRM,2026-04-05",
            ],
            reason_rows=["PURCHASE, True", "BONUS, FALSE", "PROMO, TRUE"],
            calendar_rows=["2026-04-03 open", "2026-04-05 open"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["reason"] for row in rows] == ["PURCHASE", "", "PROMO"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 2400,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1200,
        }

    def test_reasons_csv_aliases_are_canonicalized_before_allowlist_check(self):
        """Aliased reason names in reasons.csv must canonicalize before enabled checks."""
        write_dated_inputs(
            ["INV9001,CUST9001,5000,POSTED,PURCHASE,2026-04-03"],
            ["INV9001,CUST9001,5000,PUR,2026-04-05"],
            reason_rows=["PUR, true", "BNS, true", "PRM, true"],
            calendar_rows=["2026-04-03 open", "2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["reason"] == "PURCHASE"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 5000
