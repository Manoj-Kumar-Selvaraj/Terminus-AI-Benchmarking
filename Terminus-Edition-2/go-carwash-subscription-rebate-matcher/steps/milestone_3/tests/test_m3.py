"""Milestone 3 verifier tests for dated rebate reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
WSHS = APP / "data" / "washes.csv"
REFUNDS = APP / "data" / "rebates.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "wash_rebate_report.csv"
SUMMARY = APP / "out" / "wash_rebate_summary.json"
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


def write_inputs(bill_rows, credit_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated credit scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    WSHS.write_text("wash_id,customer_id,amount_cents,status,plan_tier,wash_date\n" + "\n".join(bill_rows) + "\n")
    REFUNDS.write_text("wash_id,customer_id,amount_cents,plan_tier,rebate_date\n" + "\n".join(credit_rows) + "\n")
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
    """Verify milestone 3 preserves alias behavior while adding optional dated matching, open-calendar rebate dates, latest wash_date selection, tie-breaks, and row-position consumption."""

    def test_open_rebate_date_and_latest_wash_date_win(self):
        """Open credit dates should gate matching and latest eligible due date should win."""
        write_inputs(
            [
                "WSH9301,CUST9301,1000,COMPLETED,BASIC,2026-04-03",
                "WSH9301,CUST9301,1000,COMPLETED,PLUS,2026-04-04",
                "WSH9302,CUST9302,2000,COMPLETED,PLUS,2026-04-02",
                "WSH9303,CUST9303,3000,COMPLETED,PRO,2026-04-05",
                "WSH9304,CUST9304,4000,COMPLETED,PRO,2026-04-05",
            ],
            [
                "WSH9301,CUST9301,1000,PL,2026-04-02",
                "WSH9302,CUST9302,2000,PL,2026-04-04",
                "WSH9303,CUST9303,3000,PR,2026-04-06",
                "WSH9304,CUST9304,4000,PRO,2026-04-07",
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
        assert rows[0]["plan_tier"] == "PLUS"
        assert [row["plan_tier"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_wash_date_tie_uses_record_order_and_consumption(self):
        """Same-date candidates should use trip order and still enforce consumption."""
        write_inputs(
            [
                "WSH9401,CUST9401,500,COMPLETED,PLUS,2026-04-05",
                "WSH9401,CUST9401,500,COMPLETED,PLUS,2026-04-05",
                "WSH9402,CUST9402,700,COMPLETED,BASIC,2026-04-05",
            ],
            [
                "WSH9401,CUST9401,500,PL,2026-04-04",
                "WSH9401,CUST9401,500,PL,2026-04-04",
                "WSH9401,CUST9401,500,PL,2026-04-04",
                "WSH9402,CUST9402,700,BASIC,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["plan_tier"] for row in rows] == ["PLUS", "PLUS", "", "BASIC"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_wash_date_wins_before_older_record_is_used(self):
        """Latest wash_date must win when the later input row carries the later date."""
        write_inputs(
            [
                "WSH9501,CUST9501,500,COMPLETED,BASIC,2026-04-03",
                "WSH9501,CUST9501,800,COMPLETED,PLUS,2026-04-06",
                "WSH9501,CUST9501,700,COMPLETED,PLUS,2026-04-05",
            ],
            [
                "WSH9501,CUST9501,800,PL,2026-04-02",
                "WSH9501,CUST9501,700,PL,2026-04-04",
                "WSH9501,CUST9501,500,BS,2026-04-03",
            ],
            [
                "2026-04-02 open",
                "2026-04-03 open",
                "2026-04-04 open",
                "2026-04-05 open",
                "2026-04-06 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 2000,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_closed_rebate_date_is_not_eligible(self):
        """A credit whose date is listed as closed must not match."""
        write_inputs(
            ["WSH9601,CUST9601,1000,COMPLETED,PLUS,2026-04-10"],
            ["WSH9601,CUST9601,1000,PL,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["plan_tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_rebate_date_is_not_eligible(self):
        """A credit date absent from the calendar must not be treated as open."""
        write_inputs(
            ["WSH9651,CUST9651,500,COMPLETED,PLUS,2026-04-30"],
            ["WSH9651,CUST9651,500,PL,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["plan_tier"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_rebate_date_is_not_eligible(self):
        """A credit with an empty rebate_date must not match any trip."""
        write_inputs(
            ["WSH9701,CUST9701,900,COMPLETED,BASIC,2026-04-05"],
            ["WSH9701,CUST9701,900,BASIC,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["plan_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_record_without_wash_date_is_not_eligible(self):
        """A trip with an empty wash_date cannot be consumed."""
        write_inputs(
            ["WSH9801,CUST9801,700,COMPLETED,PRO,"],
            ["WSH9801,CUST9801,700,PR,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["plan_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_pr_alias_matches_pro_record_and_emits_canonical_plan_tier(self):
        """A PR credit should match a PRO trip and report the canonical plan_tier."""
        write_inputs(
            ["WSH9901,CUST9901,600,COMPLETED,PRO,2026-04-10"],
            ["WSH9901,CUST9901,600,PR,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["plan_tier"] == "PRO"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }


    def test_matched_report_uses_credit_plan_tier_under_date_gates(self):
        """Date-gated matches should still emit the rebate row's canonical plan_tier."""
        write_inputs(
            [
                "WSH9921,CUST9921,810,COMPLETED,basic,2026-04-10",
                "WSH9922,CUST9922,820,COMPLETED,plus,2026-04-10",
            ],
            [
                "WSH9921,CUST9921,810,BASIC,2026-04-05",
                "WSH9922,CUST9922,820,PL,2026-04-05",
            ],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["plan_tier"] for row in rows] == ["BASIC", "PLUS"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 1630


    def test_mismatched_plan_tier_does_not_match_even_with_valid_dates(self):
        """Date logic must not bypass the original plan_tier equality requirement."""
        write_inputs(
            ["WSH9851,CUST9851,775,COMPLETED,BASIC,2026-04-10"],
            ["WSH9851,CUST9851,775,PLUS,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["plan_tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 775

    def test_bs_alias_matches_basic_record_with_dated_matching(self):
        """The BS alias should still normalize to BASIC when date gates are present."""
        write_inputs(
            ["WSH9951,CUST9951,650,COMPLETED,BASIC,2026-04-10"],
            ["WSH9951,CUST9951,650,BS,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["plan_tier"] == "BASIC"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 650,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_undated_inputs_preserve_alias_matching_without_calendar_gate(self):
        """When date columns are absent, milestone 3 must preserve the undated alias behavior."""
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        WSHS.write_text(
            "wash_id,customer_id,amount_cents,status,plan_tier\n"
            "WSHUND01,CUSTUND,1100,COMPLETED,PLUS\n"
            "WSHUND02,CUSTUND,1200,COMPLETED,BASIC\n"
        )
        REFUNDS.write_text(
            "wash_id,customer_id,amount_cents,plan_tier\n"
            "WSHUND01,CUSTUND,1100,PL\n"
            "WSHUND02,CUSTUND,1200,BS\n"
        )
        CALENDAR.write_text("2026-04-01 closed\n")
        REPORT.unlink(missing_ok=True)
        SUMMARY.unlink(missing_ok=True)

        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["plan_tier"] for row in rows] == ["PLUS", "BASIC"]
        assert summary["matched_amount_cents"] == 2300

    def test_only_rebate_date_column_triggers_dated_mode(self):
        """When rebates include rebate_date but washes omit wash_date, dated mode rejects missing wash dates."""
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        WSHS.write_text(
            "wash_id,customer_id,amount_cents,status,plan_tier\n"
            "WSHONE1,CUSTONE,900,COMPLETED,BASIC\n"
        )
        REFUNDS.write_text(
            "wash_id,customer_id,amount_cents,plan_tier,rebate_date\n"
            "WSHONE1,CUSTONE,900,BASIC,2026-04-05\n"
        )
        CALENDAR.write_text("2026-04-05 open\n")
        REPORT.unlink(missing_ok=True)
        SUMMARY.unlink(missing_ok=True)

        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_only_wash_date_column_triggers_dated_mode(self):
        """When washes include wash_date but rebates omit rebate_date, dated mode rejects missing rebate dates."""
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        WSHS.write_text(
            "wash_id,customer_id,amount_cents,status,plan_tier,wash_date\n"
            "WSHTWO1,CUSTTWO,1100,COMPLETED,PLUS,2026-04-08\n"
        )
        REFUNDS.write_text(
            "wash_id,customer_id,amount_cents,plan_tier\n"
            "WSHTWO1,CUSTTWO,1100,PLUS\n"
        )
        CALENDAR.write_text("2026-04-08 open\n")
        REPORT.unlink(missing_ok=True)
        SUMMARY.unlink(missing_ok=True)

        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 1100

    def test_latest_wash_date_choice_is_observable_across_tiers_and_consumption(self):
        """Latest wash_date selection should consume the later row so a second rebate can still use the older row."""
        write_inputs(
            [
                "WSHOBS1,CUSTOBS,1000,COMPLETED,BASIC,2026-04-04",
                "WSHOBS1,CUSTOBS,1000,COMPLETED,BASIC,2026-04-10",
                "WSHOBS1,CUSTOBS,1000,COMPLETED,PLUS,2026-04-06",
            ],
            [
                "WSHOBS1,CUSTOBS,1000,BS,2026-04-01",
                "WSHOBS1,CUSTOBS,1000,BASIC,2026-04-01",
                "WSHOBS1,CUSTOBS,1000,PL,2026-04-01",
            ],
            [
                "2026-04-01 open",
                "2026-04-04 open",
                "2026-04-06 open",
                "2026-04-10 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["plan_tier"] for row in rows] == ["BASIC", "BASIC", "PLUS"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 3000

    def test_malformed_dates_are_not_eligible_even_if_calendar_mentions_them(self):
        """Malformed rebate or wash dates must not become eligible through string comparison."""
        write_inputs(
            [
                "WSHBADDATE1,CUSTBD,900,COMPLETED,BASIC,not-a-date",
                "WSHBADDATE2,CUSTBD,800,COMPLETED,PLUS,2026-04-04",
            ],
            [
                "WSHBADDATE1,CUSTBD,900,BS,2026-04-01",
                "WSHBADDATE2,CUSTBD,800,PL,bad-date",
            ],
            [
                "2026-04-01 open",
                "bad-date open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 1700

