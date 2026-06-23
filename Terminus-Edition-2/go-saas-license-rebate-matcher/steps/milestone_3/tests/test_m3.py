"""Milestone 3 verifier tests for dated license rebate reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
LICENSES = APP / "data" / "licenses.csv"
REBATES = APP / "data" / "rebates.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "rebate_report.csv"
SUMMARY = APP / "out" / "rebate_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go rebate reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 3 tests."""
    build_program()
    assert BIN.exists()


def write_inputs(license_rows, rebate_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated rebate scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    LICENSES.write_text("license_id,tenant_id,amount_cents,status,tier,license_end\n" + "\n".join(license_rows) + "\n")
    REBATES.write_text("license_id,tenant_id,amount_cents,tier,rebate_date\n" + "\n".join(rebate_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse its CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone3:
    """Date gates and latest eligible license selection for rebates."""

    def test_open_rebate_date_and_ineligible_dates_stay_unmatched(self):
        """Open rebate dates should gate matching; duplicate license ids pick the row with latest license_end."""
        write_inputs(
            [
                "LIC9301,CUST9301,1000,LICENSED,STARTER,2026-04-03",
                "LIC9301,CUST9301,1000,LICENSED,BUSINESS,2026-04-04",
                "LIC9302,CUST9302,2000,LICENSED,BUSINESS,2026-04-02",
                "LIC9303,CUST9303,3000,LICENSED,ENTERPRISE,2026-04-05",
                "LIC9304,CUST9304,4000,LICENSED,ENTERPRISE,2026-04-05",
            ],
            [
                "LIC9301,CUST9301,1000,BUS,2026-04-02",
                "LIC9302,CUST9302,2000,BUS,2026-04-04",
                "LIC9303,CUST9303,3000,ENT,2026-04-06",
                "LIC9304,CUST9304,4000,ENTERPRISE,2026-04-07",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
                "2026-04-05 open",
                "2026-04-06 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert rows[0]["tier"] == "BUSINESS"
        assert [row["tier"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_license_end_tie_uses_license_order_and_consumption(self):
        """Same license_end ties should use the earliest licenses.csv input row and still enforce consumption."""
        write_inputs(
            [
                "LIC9401,CUST9401,500,LICENSED,BUSINESS,2026-04-05",
                "LIC9401,CUST9401,500,LICENSED,BUSINESS,2026-04-05",
                "LIC9402,CUST9402,700,LICENSED,STARTER,2026-04-05",
            ],
            [
                "LIC9401,CUST9401,500,BUS,2026-04-04",
                "LIC9401,CUST9401,500,BUS,2026-04-04",
                "LIC9401,CUST9401,500,BUS,2026-04-04",
                "LIC9402,CUST9402,700,STARTER,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["tier"] for row in rows] == ["BUSINESS", "BUSINESS", "", "STARTER"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_license_end_wins_before_older_license_is_used(self):
        """A later eligible license_end should be consumed before an older eligible license."""
        write_inputs(
            [
                "LIC9501,CUST9501,800,LICENSED,BUSINESS,2026-04-03",
                "LIC9501,CUST9501,800,LICENSED,BUSINESS,2026-04-06",
            ],
            [
                "LIC9501,CUST9501,800,BUS,2026-04-02",
                "LIC9501,CUST9501,800,BUS,2026-04-04",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["tier"] for row in rows] == ["BUSINESS", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_closed_rebate_date_is_not_eligible(self):
        """A rebate whose date is listed as closed must not match."""
        write_inputs(
            ["LIC9601,CUST9601,1000,LICENSED,BUSINESS,2026-04-10"],
            ["LIC9601,CUST9601,1000,BUS,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_rebate_date_is_not_eligible(self):
        """A rebate date absent from the calendar must not be treated as open."""
        write_inputs(
            ["LIC9651,CUST9651,500,LICENSED,BUSINESS,2026-04-30"],
            ["LIC9651,CUST9651,500,BUS,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["tier"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_rebate_date_is_not_eligible(self):
        """A rebate with an empty rebate_date must not match any license."""
        write_inputs(
            ["LIC9701,CUST9701,900,LICENSED,STARTER,2026-04-05"],
            ["LIC9701,CUST9701,900,STARTER,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_license_without_license_end_is_not_eligible(self):
        """A license with an empty license_end cannot be consumed."""
        write_inputs(
            ["LIC9801,CUST9801,700,LICENSED,ENTERPRISE,"],
            ["LIC9801,CUST9801,700,ENT,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_latest_license_end_tie_consumes_earliest_row_before_older_end(self):
        """Among equal license_end values, consume earliest input rows before older-end leftovers."""
        write_inputs(
            [
                "LIC-TIE,CUST-TIE,900,LICENSED,BUSINESS,2026-04-01",
                "LIC-TIE,CUST-TIE,900,LICENSED,BUSINESS,2026-04-03",
                "LIC-TIE,CUST-TIE,900,LICENSED,BUSINESS,2026-04-03",
            ],
            [
                "LIC-TIE,CUST-TIE,900,BUS,2026-04-02",
                "LIC-TIE,CUST-TIE,900,BUS,2026-04-02",
                "LIC-TIE,CUST-TIE,900,BUS,2026-04-02",
            ],
            ["2026-04-02 open"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["tier"] for row in rows] == ["BUSINESS", "BUSINESS", ""]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 900,
        }

    def test_ent_alias_matches_enterprise_license_and_emits_canonical_tier(self):
        """A ENT rebate should match a ENTERPRISE license and report the canonical tier."""
        write_inputs(
            ["LIC9901,CUST9901,600,LICENSED,ENTERPRISE,2026-04-10"],
            ["LIC9901,CUST9901,600,ENT,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["tier"] == "ENTERPRISE"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
