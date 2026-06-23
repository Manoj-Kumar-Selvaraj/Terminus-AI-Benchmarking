"""Milestone 4 verifier tests for policy-driven veterinary visit credit reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
VISITS = APP / "data" / "visits.csv"
CREDITS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
POLICY = APP / "config" / "clinic_policy.csv"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")

DEFAULT_CALENDAR = [
    "2026-04-01 open",
    "2026-04-02 open",
    "2026-04-03 open",
    "2026-04-04 open",
    "2026-04-05 open",
    "2026-04-06 open",
]


def build_program():
    """Compile the Go reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile once for all milestone 4 verifier tests."""
    build_program()


def write_inputs(visit_rows, credit_rows, calendar_rows=None, policy_rows=None):
    """Replace CSV inputs, calendar, and policy with one focused scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    VISITS.write_text(
        "visit_id,owner_id,amount_cents,status,clinic,service_date\n"
        + "\n".join(visit_rows)
        + "\n"
    )
    CREDITS.write_text(
        "visit_id,owner_id,amount_cents,clinic,credit_date\n"
        + "\n".join(credit_rows)
        + "\n"
    )
    CALENDAR.write_text("\n".join(calendar_rows or DEFAULT_CALENDAR) + "\n")
    POLICY.write_text(
        "clinic,enabled,priority\n"
        + "\n".join(
            policy_rows
            or [
                "MAIN,true,2",
                "MOBILE,true,1",
                "ER,true,3",
                "CHECK,false,9",
            ]
        )
        + "\n"
    )
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone4:
    """Policy-driven clinic eligibility, ANY matching, priority, and prior-rule regressions."""

    def test_disabled_clinic_rejects_otherwise_valid_specific_credit(self):
        """A disabled clinic must stay unmatched even when every M1-M3 gate passes."""
        write_inputs(
            ["VET4101,OWNER4101,1200,CLOSED,MOBILE,2026-04-05"],
            ["VET4101,OWNER4101,1200,VAN,2026-04-02"],
            policy_rows=[
                "MAIN,true,2",
                "MOBILE,false,1",
                "ER,true,3",
            ],
        )

        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["clinic"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1200,
        }

    def test_any_credit_uses_latest_service_date_before_priority(self):
        """ANY should prefer latest eligible service_date even when an older row has better priority."""
        write_inputs(
            [
                "VET4201,OWNER4201,900,CLOSED,MOBILE,2026-04-03",
                "VET4201,OWNER4201,900,CLOSED,ER,2026-04-06",
            ],
            ["VET4201,OWNER4201,900,ANY,2026-04-02"],
            policy_rows=[
                "MAIN,true,2",
                "MOBILE,true,1",
                "ER,true,9",
            ],
        )

        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["clinic"] == "ER"
        assert rows[0]["clinic"] != "ANY"
        assert summary["matched_amount_cents"] == 900

    def test_any_same_date_uses_lower_policy_priority(self):
        """When service_date ties, ANY should pick the lower configured clinic priority."""
        write_inputs(
            [
                "VET4301,OWNER4301,700,CLOSED,ER,2026-04-05",
                "VET4301,OWNER4301,700,CLOSED,MOBILE,2026-04-05",
            ],
            ["VET4301,OWNER4301,700,ANY,2026-04-02"],
            policy_rows=[
                "MOBILE,true,5",
                "ER,true,1",
            ],
        )

        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["clinic"] == "ER"
        assert summary["matched_count"] == 1

    def test_any_equal_priority_tie_uses_earliest_visit_row(self):
        """When service_date and priority tie, ANY should choose the first eligible visit row."""
        write_inputs(
            [
                "VET4401,OWNER4401,650,CLOSED,MAIN,2026-04-05",
                "VET4401,OWNER4401,650,CLOSED,MOBILE,2026-04-05",
            ],
            ["VET4401,OWNER4401,650,ANY,2026-04-02"],
            policy_rows=[
                "MAIN,true,4",
                "MOBILE,true,4",
            ],
        )

        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["clinic"] == "MAIN"
        assert summary["matched_count"] == 1

    def test_any_consumes_selected_row_and_second_any_gets_next_best(self):
        """Consumption should happen by visit row, so the second ANY uses the next eligible row."""
        write_inputs(
            [
                "VET4501,OWNER4501,500,CLOSED,MAIN,2026-04-05",
                "VET4501,OWNER4501,500,CLOSED,MOBILE,2026-04-05",
            ],
            [
                "VET4501,OWNER4501,500,ANY,2026-04-02",
                "VET4501,OWNER4501,500,ANY,2026-04-02",
                "VET4501,OWNER4501,500,ANY,2026-04-02",
            ],
            policy_rows=[
                "MAIN,true,2",
                "MOBILE,true,1",
            ],
        )

        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["clinic"] for row in rows] == ["MOBILE", "MAIN", ""]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1000,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_specific_alias_still_requires_exact_canonical_clinic(self):
        """A VAN credit must not match an ER visit just because ER has better policy priority."""
        write_inputs(
            [
                "VET4601,OWNER4601,1300,CLOSED,ER,2026-04-06",
                "VET4601,OWNER4601,1300,CLOSED,MOBILE,2026-04-05",
            ],
            ["VET4601,OWNER4601,1300,VAN,2026-04-02"],
            policy_rows=[
                "MOBILE,true,5",
                "ER,true,1",
            ],
        )

        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["clinic"] == "MOBILE"
        assert summary["matched_amount_cents"] == 1300

    def test_malformed_priority_ranks_after_numeric_priority(self):
        """Malformed priority should rank behind configured numeric priorities for ANY ties."""
        write_inputs(
            [
                "VET4701,OWNER4701,800,CLOSED,MAIN,2026-04-05",
                "VET4701,OWNER4701,800,CLOSED,MOBILE,2026-04-05",
            ],
            ["VET4701,OWNER4701,800,ANY,2026-04-02"],
            policy_rows=[
                "MAIN,true,not-a-number",
                "MOBILE,true,2",
            ],
        )

        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["clinic"] == "MOBILE"
        assert summary["matched_count"] == 1

    def test_missing_priority_ranks_after_numeric_priority(self):
        """A policy row with a missing priority should rank behind configured numeric priorities."""
        write_inputs(
            [
                "VET4751,OWNER4751,850,CLOSED,MAIN,2026-04-05",
                "VET4751,OWNER4751,850,CLOSED,MOBILE,2026-04-05",
            ],
            ["VET4751,OWNER4751,850,ANY,2026-04-02"],
            policy_rows=[
                "MAIN,true,",
                "MOBILE,true,2",
            ],
        )

        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["clinic"] == "MOBILE"
        assert summary["matched_count"] == 1

    def test_any_still_respects_closed_calendar_date(self):
        """ANY matching must still obey the milestone 3 open-date gate."""
        write_inputs(
            ["VET4801,OWNER4801,1400,CLOSED,MOBILE,2026-04-05"],
            ["VET4801,OWNER4801,1400,ANY,2026-04-02"],
            calendar_rows=["2026-04-02 closed", "2026-04-05 open"],
        )

        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["clinic"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1400,
        }
