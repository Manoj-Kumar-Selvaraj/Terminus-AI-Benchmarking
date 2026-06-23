"""Milestone 4 verifier tests for policy-controlled SaaS rebate matching."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
LICENSES = APP / "data" / "licenses.csv"
REBATES = APP / "data" / "rebates.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
POLICY = APP / "config" / "tier_policy.csv"
LIMITS = APP / "config" / "tenant_limits.csv"
BLACKOUTS = APP / "config" / "license_blackouts.csv"
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
    """Compile the Go reconciliation CLI once for all milestone 4 tests."""
    build_program()
    assert BIN.exists()


def write_policy(rows):
    POLICY.write_text("tier,enabled,priority\n" + "\n".join(rows) + "\n")


def write_limits(rows):
    LIMITS.write_text("tenant_id,effective_date,max_daily_amount_cents\n" + "\n".join(rows) + "\n")


def write_blackouts(rows):
    BLACKOUTS.write_text("license_id,start_date,end_date\n" + "\n".join(rows) + "\n")


def write_inputs(license_rows, rebate_rows, calendar_rows=None, dated=True):
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    if dated:
        LICENSES.write_text("license_id,tenant_id,amount_cents,status,tier,license_end\n" + "\n".join(license_rows) + "\n")
        REBATES.write_text("license_id,tenant_id,amount_cents,tier,rebate_date\n" + "\n".join(rebate_rows) + "\n")
    else:
        LICENSES.write_text("license_id,tenant_id,amount_cents,status,tier\n" + "\n".join(license_rows) + "\n")
        REBATES.write_text("license_id,tenant_id,amount_cents,tier\n" + "\n".join(rebate_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows or ["2026-04-02 open", "2026-04-03 open"]) + "\n")
    write_policy(["STARTER,true,20", "BUSINESS,true,10", "ENTERPRISE,true,30"])
    write_limits(["TENANT-A,2026-01-01,10000", "TENANT-B,2026-01-01,900"])
    write_blackouts([])
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse its CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone4:
    """Configured tier policy, ANY matching, limits, and blackouts."""

    def test_disabled_policy_tier_rejects_otherwise_valid_rebate(self):
        write_inputs(
            ["LIC-401,TENANT-A,400,LICENSED,ENTERPRISE,2026-04-04"],
            ["LIC-401,TENANT-A,400,ENT,2026-04-02"],
            ["2026-04-02 open"],
        )
        write_policy(["STARTER,true,20", "BUSINESS,true,10", "ENTERPRISE,false,30"])
        rows, summary = run_program()

        assert rows == [{"license_id": "LIC-401", "tenant_id": "TENANT-A", "tier": "", "amount_cents": "400", "status": "UNMATCHED"}]
        assert summary == {"matched_count": 0, "matched_amount_cents": 0, "unmatched_count": 1, "unmatched_amount_cents": 400}

    def test_any_uses_latest_date_before_policy_priority(self):
        write_inputs(
            [
                "LIC-402,TENANT-A,500,LICENSED,BUSINESS,2026-04-04",
                "LIC-402,TENANT-A,500,LICENSED,STARTER,2026-04-06",
                "LIC-402,TENANT-A,500,LICENSED,BUSINESS,2026-04-04",
            ],
            [
                "LIC-402,TENANT-A,500,ANY,2026-04-02",
                "LIC-402,TENANT-A,500,ANY,2026-04-03",
            ],
            ["2026-04-02 open", "2026-04-03 open"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["tier"] for row in rows] == ["STARTER", "BUSINESS"]
        assert summary["matched_amount_cents"] == 1000

    def test_any_same_date_uses_priority_then_license_row(self):
        write_inputs(
            [
                "LIC-403,TENANT-A,300,LICENSED,ENTERPRISE,2026-04-05",
                "LIC-403,TENANT-A,300,LICENSED,BUSINESS,2026-04-05",
                "LIC-403,TENANT-A,300,LICENSED,BUSINESS,2026-04-05",
            ],
            [
                "LIC-403,TENANT-A,300,ANY,2026-04-02",
                "LIC-403,TENANT-A,300,ANY,2026-04-02",
            ],
            ["2026-04-02 open"],
        )
        rows, summary = run_program()

        assert [row["tier"] for row in rows] == ["BUSINESS", "BUSINESS"]
        assert summary == {"matched_count": 2, "matched_amount_cents": 600, "unmatched_count": 0, "unmatched_amount_cents": 0}

    def test_tenant_daily_limit_rejects_without_consuming_license(self):
        write_inputs(
            [
                "LIC-404,TENANT-B,600,LICENSED,BUSINESS,2026-04-04",
                "LIC-405,TENANT-B,400,LICENSED,BUSINESS,2026-04-04",
                "LIC-404,TENANT-B,600,LICENSED,BUSINESS,2026-04-04",
            ],
            [
                "LIC-404,TENANT-B,600,BUS,2026-04-02",
                "LIC-405,TENANT-B,400,BUS,2026-04-02",
                "LIC-404,TENANT-B,600,BUS,2026-04-03",
            ],
            ["2026-04-02 open", "2026-04-03 open"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["tier"] for row in rows] == ["BUSINESS", "", "BUSINESS"]
        assert summary == {"matched_count": 2, "matched_amount_cents": 1200, "unmatched_count": 1, "unmatched_amount_cents": 400}

    def test_latest_limit_effective_date_and_file_tie_win(self):
        write_inputs(
            [
                "LIC-406,TENANT-C,700,LICENSED,BUSINESS,2026-04-04",
                "LIC-407,TENANT-C,600,LICENSED,BUSINESS,2026-04-04",
            ],
            [
                "LIC-406,TENANT-C,700,BUS,2026-04-02",
                "LIC-407,TENANT-C,600,BUS,2026-04-02",
            ],
            ["2026-04-02 open"],
        )
        write_limits(["TENANT-C,2026-01-01,700", "TENANT-C,2026-04-01,1200", "TENANT-C,2026-04-01,1300"])
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert summary["matched_amount_cents"] == 1300

    def test_missing_dated_limit_blocks_match(self):
        write_inputs(
            ["LIC-408,TENANT-NO-LIMIT,500,LICENSED,BUSINESS,2026-04-04"],
            ["LIC-408,TENANT-NO-LIMIT,500,BUS,2026-04-02"],
            ["2026-04-02 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert summary["unmatched_amount_cents"] == 500

    def test_blackout_filters_candidates_before_any_ranking(self):
        write_inputs(
            [
                "LIC-409,TENANT-A,500,LICENSED,BUSINESS,2026-04-06",
                "LIC-409,TENANT-A,500,LICENSED,STARTER,2026-04-05",
            ],
            ["LIC-409,TENANT-A,500,ANY,2026-04-02"],
            ["2026-04-02 open"],
        )
        write_blackouts(["LIC-409,2026-04-06,2026-04-06", "LIC-409,,2026-04-05", "LIC-409,2026-04-09,2026-04-01"])
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["tier"] == "STARTER"
        assert summary["matched_amount_cents"] == 500

    def test_blank_blackout_dates_are_ignored(self):
        """Blackout rows with blank start or end dates must not block otherwise eligible licenses."""
        write_inputs(
            [
                "LIC-BLK,TENANT-A,450,LICENSED,BUSINESS,2026-04-05",
                "LIC-BLK,TENANT-A,450,LICENSED,STARTER,2026-04-04",
            ],
            ["LIC-BLK,TENANT-A,450,ANY,2026-04-02"],
            ["2026-04-02 open"],
        )
        write_blackouts(["LIC-BLK,,2026-04-05", "LIC-BLK,2026-04-04,"])
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["tier"] == "BUSINESS"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 450,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_undated_any_applies_policy_without_limits_or_blackouts(self):
        write_inputs(
            [
                "LIC-410,TENANT-NO-LIMIT,400,LICENSED,STARTER",
                "LIC-410,TENANT-NO-LIMIT,400,LICENSED,BUSINESS",
            ],
            [
                "LIC-410,TENANT-NO-LIMIT,400,ANY",
                "LIC-410,TENANT-NO-LIMIT,400,ENT",
            ],
            dated=False,
        )
        write_policy(["STARTER,false,20", "BUSINESS,true,10", "ENTERPRISE,true,30"])
        write_blackouts(["LIC-410,2026-01-01,2026-12-31"])
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["tier"] for row in rows] == ["BUSINESS", ""]
        assert summary == {"matched_count": 1, "matched_amount_cents": 400, "unmatched_count": 1, "unmatched_amount_cents": 400}
