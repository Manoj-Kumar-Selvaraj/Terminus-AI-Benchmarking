"""Milestone 3 verifier tests for dated freight claim matching."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
SHIPMENTS = APP / "data" / "shipments.csv"
CLAIMS = APP / "data" / "claims.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "claim_report.csv"
SUMMARY = APP / "out" / "claim_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")
REPORT_FIELDS = ["shipment_id", "admgount_id", "reason", "amount_cents", "status"]
SUMMARY_FIELDS = ["matched_count", "matched_amount_cents", "unmatched_count", "unmatched_amount_cents"]


def build_program():
    """Compile the Go claim reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go claim reconciliation CLI once for all milestone 3 tests."""
    build_program()


def write_inputs(shipment_rows, claim_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated claim scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SHIPMENTS.write_text("shipment_id,admgount_id,amount_cents,status,reason,ship_date\n" + "\n".join(shipment_rows) + "\n")
    CLAIMS.write_text("shipment_id,admgount_id,amount_cents,reason,claim_date\n" + "\n".join(claim_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse its CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        reader = csv.DictReader(f)
        assert reader.fieldnames == REPORT_FIELDS
        rows = list(reader)
    summary = json.loads(SUMMARY.read_text())
    assert list(summary) == SUMMARY_FIELDS
    assert all(type(summary[key]) is int for key in SUMMARY_FIELDS)
    return rows, summary


class TestMilestone3:
    """Date gates and latest eligible shipment selection for claims."""

    def test_open_and_closed_claim_dates_gate_alias_aware_matching(self):
        """Open and closed claim dates should gate matching while aliases emit canonical reasons."""
        write_inputs(
            [
                "SHIP9301,ACCT9301,1000,POSTED,DAMAGED,2026-04-01",
                "SHIP9301,ACCT9301,1000,POSTED,LOST,2026-04-03",
                "SHIP9302,ACCT9302,2000,POSTED,HAZ,2026-04-05",
                "SHIP9303,ACCT9303,3000,POSTED,DAMAGED,2026-04-04",
                "SHIP9304,ACCT9304,4000,POSTED,HAZ,2026-04-05",
            ],
            [
                "SHIP9301,ACCT9301,1000,DMG,2026-04-04",
                "SHIP9302,ACCT9302,2000,HZD,2026-04-04",
                "SHIP9303,ACCT9303,3000,DAMAGED,2026-04-05",
                "SHIP9304,ACCT9304,4000,HZD,2026-04-07",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 closed",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert rows[0]["reason"] == "LOST"
        assert [row["reason"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_ship_date_tie_uses_shipment_order_and_consumption(self):
        """Same-date candidates should use shipment order and still enforce consumption."""
        write_inputs(
            [
                "SHIP9401,ACCT9401,500,POSTED,LOST,2026-04-05",
                "SHIP9401,ACCT9401,500,POSTED,LOST,2026-04-05",
                "SHIP9402,ACCT9402,700,POSTED,DAMAGED,2026-04-05",
            ],
            [
                "SHIP9401,ACCT9401,500,DMG,2026-04-06",
                "SHIP9401,ACCT9401,500,DMG,2026-04-06",
                "SHIP9401,ACCT9401,500,DMG,2026-04-06",
                "SHIP9402,ACCT9402,700,DAMAGED,2026-04-06",
            ],
            [
                "2026-04-06 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["reason"] for row in rows] == ["LOST", "LOST", "", "DAMAGED"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_ship_date_selection_leaves_older_eligible_shipment_for_later_claim(self):
        """Latest-date selection should leave an older eligible shipment for a later claim."""
        write_inputs(
            [
                "SHIP9501,ACCT9501,800,POSTED,LOST,2026-04-01",
                "SHIP9501,ACCT9501,800,POSTED,LOST,2026-04-03",
            ],
            [
                "SHIP9501,ACCT9501,800,DMG,2026-04-04",
                "SHIP9501,ACCT9501,800,DMG,2026-04-02",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["reason"] for row in rows] == ["LOST", "LOST"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_missing_claim_date_is_not_eligible(self):
        """A claim with an empty claim_date must not match any shipment."""
        write_inputs(
            ["SHIP9601,ACCT9601,900,POSTED,DAMAGED,2026-04-05"],
            ["SHIP9601,ACCT9601,900,DAMAGED,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["reason"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 900

    def test_hzd_alias_matches_haz_shipment_and_emits_canonical_reason(self):
        """A HZD claim should match a HAZ shipment and report canonical HAZ."""
        write_inputs(
            ["SHIP9701,ACCT9701,600,POSTED,HAZ,2026-04-03"],
            ["SHIP9701,ACCT9701,600,HZD,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["reason"] == "HAZ"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_missing_ship_date_makes_shipment_ineligible(self):
        """A shipment with an empty ship_date must not be chosen for dated matching."""
        write_inputs(
            [
                "SHIP9801,ACCT9801,500,POSTED,LOST,",
                "SHIP9801,ACCT9801,500,POSTED,LOST,2026-04-02",
            ],
            ["SHIP9801,ACCT9801,500,LOST,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["reason"] == "LOST"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 500
