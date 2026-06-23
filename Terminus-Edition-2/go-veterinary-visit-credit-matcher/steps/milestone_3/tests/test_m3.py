"""Milestone 3 verifier tests for dated visit credit reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
BILLS = APP / "data" / "visits.csv"
REFUNDS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go credit reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 3 tests."""
    build_program()


def write_inputs(bill_rows, refund_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated credit scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    BILLS.write_text("visit_id,owner_id,amount_cents,status,clinic,service_date\n" + "\n".join(bill_rows) + "\n")
    REFUNDS.write_text("visit_id,owner_id,amount_cents,clinic,credit_date\n" + "\n".join(refund_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_legacy_inputs(bill_rows, refund_rows):
    """Replace CSV inputs with the pre-date schema to verify M3 compatibility."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    BILLS.write_text("visit_id,owner_id,amount_cents,status,clinic\n" + "\n".join(bill_rows) + "\n")
    REFUNDS.write_text("visit_id,owner_id,amount_cents,clinic\n" + "\n".join(refund_rows) + "\n")
    CALENDAR.write_text("")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse its CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone3:
    """Date gates and latest eligible visit selection for refunds."""

    def test_legacy_schema_without_dates_keeps_prior_alias_and_consumption_behavior(self):
        """Pre-date inputs should keep milestone 2 matching instead of requiring calendar dates."""
        write_legacy_inputs(
            [
                "BILL9001,CUST9001,1200,CLOSED,MOBILE",
                "BILL9001,CUST9001,1200,CLOSED,MOBILE",
                "BILL9002,CUST9002,700,CLOSED,ER",
                "BILL9003,CUST9003,500,PENDING,MAIN",
            ],
            [
                "BILL9001,CUST9001,1200,VAN",
                "BILL9001,CUST9001,1200,VAN",
                "BILL9001,CUST9001,1200,VAN",
                "BILL9002,CUST9002,700,URG",
                "BILL9003,CUST9003,500,MN",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED", "UNMATCHED"]
        assert [row["clinic"] for row in rows] == ["MOBILE", "MOBILE", "", "ER", ""]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 3100,
            "unmatched_count": 2,
            "unmatched_amount_cents": 1700,
        }

    def test_open_credit_date_and_latest_service_date_win(self):
        """Open credit dates should gate matching; clinic must match even when another visit has a later service_date."""
        write_inputs(
            [
                "BILL9301,CUST9301,1000,CLOSED,MAIN,2026-04-03",
                "BILL9301,CUST9301,1000,CLOSED,ER,2026-04-10",
                "BILL9301,CUST9301,1000,CLOSED,MOBILE,2026-04-04",
                "BILL9302,CUST9302,2000,CLOSED,MOBILE,2026-04-02",
                "BILL9303,CUST9303,3000,CLOSED,ER,2026-04-05",
                "BILL9304,CUST9304,4000,CLOSED,ER,2026-04-05",
            ],
            [
                "BILL9301,CUST9301,1000,VAN,2026-04-02",
                "BILL9302,CUST9302,2000,VAN,2026-04-04",
                "BILL9303,CUST9303,3000,URG,2026-04-06",
                "BILL9304,CUST9304,4000,ER,2026-04-07",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
                "2026-04-05 open",
                "2026-04-06 open",
                "2026-04-07 open",
                "2026-04-10 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert rows[0]["clinic"] == "MOBILE"
        assert [row["clinic"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_service_date_tie_uses_bill_order_and_consumption(self):
        """When service_date ties among clinic-matching rows, earliest visit row wins and consumption is enforced."""
        write_inputs(
            [
                "BILL9401,CUST9401,500,CLOSED,MOBILE,2026-04-05",
                "BILL9401,CUST9401,500,CLOSED,ER,2026-04-05",
                "BILL9402,CUST9402,700,CLOSED,MAIN,2026-04-05",
            ],
            [
                "BILL9401,CUST9401,500,VAN,2026-04-04",
                "BILL9401,CUST9401,500,URG,2026-04-04",
                "BILL9401,CUST9401,500,VAN,2026-04-04",
                "BILL9402,CUST9402,700,MAIN,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["clinic"] for row in rows] == ["MOBILE", "ER", "", "MAIN"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_service_date_wins_before_older_bill_is_used(self):
        """A later eligible service_date should be consumed before an older eligible visit row."""
        write_inputs(
            [
                "BILL9501,CUST9501,800,CLOSED,MOBILE,2026-04-03",
                "BILL9501,CUST9501,800,CLOSED,MOBILE,2026-04-06",
            ],
            [
                "BILL9501,CUST9501,800,VAN,2026-04-02",
                "BILL9501,CUST9501,800,VAN,2026-04-04",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["clinic"] for row in rows] == ["MOBILE", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_closed_credit_date_is_not_eligible(self):
        """A credit whose date is listed as closed must not match."""
        write_inputs(
            ["BILL9601,CUST9601,1000,CLOSED,MOBILE,2026-04-10"],
            ["BILL9601,CUST9601,1000,VAN,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["clinic"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_credit_date_is_not_eligible(self):
        """A credit date absent from the calendar must not be treated as open."""
        write_inputs(
            ["BILL9651,CUST9651,500,CLOSED,MOBILE,2026-04-30"],
            ["BILL9651,CUST9651,500,VAN,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["clinic"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_credit_date_is_not_eligible(self):
        """A credit with an empty credit_date must not match any visit."""
        write_inputs(
            ["BILL9701,CUST9701,900,CLOSED,MAIN,2026-04-05"],
            ["BILL9701,CUST9701,900,MAIN,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["clinic"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_bill_without_service_date_is_not_eligible(self):
        """A visit with an empty service_date cannot be consumed."""
        write_inputs(
            ["BILL9801,CUST9801,700,CLOSED,ER,"],
            ["BILL9801,CUST9801,700,URG,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["clinic"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_urg_alias_matches_er_bill_and_emits_canonical_clinic(self):
        """A URG credit should match a ER visit and report the canonical clinic."""
        write_inputs(
            ["BILL9901,CUST9901,600,CLOSED,ER,2026-04-10"],
            ["BILL9901,CUST9901,600,URG,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["clinic"] == "ER"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_mn_alias_matches_main_with_dates_and_emits_canonical_clinic(self):
        """The MN alias should still normalize to MAIN under dated matching."""
        write_inputs(
            ["ALIAS3001,CUSTALIAS3,4321,CLOSED,MAIN,2026-04-10"],
            ["ALIAS3001,CUSTALIAS3,4321,MN,2026-04-05"],
            ["2026-04-05 open", "2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["clinic"] == "MAIN"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 4321,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_credit_date_later_than_service_date_rejects(self):
        """A credit_date after the visit service_date must not match even when other gates pass."""
        write_inputs(
            ["BILL9951,CUST9951,450,CLOSED,MOBILE,2026-04-05"],
            ["BILL9951,CUST9951,450,VAN,2026-04-08"],
            ["2026-04-05 open", "2026-04-08 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["clinic"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 450

    def test_duplicate_visit_id_rows_consumed_independently_by_row_position(self):
        """Two visit rows with the same visit_id must be consumable independently by input order."""
        write_inputs(
            [
                "BILL9961,CUST9961,300,CLOSED,MOBILE,2026-04-05",
                "BILL9961,CUST9961,300,CLOSED,ER,2026-04-05",
            ],
            [
                "BILL9961,CUST9961,300,VAN,2026-04-04",
                "BILL9961,CUST9961,300,URG,2026-04-04",
            ],
            ["2026-04-04 open", "2026-04-05 open"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["clinic"] for row in rows] == ["MOBILE", "ER"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 600

