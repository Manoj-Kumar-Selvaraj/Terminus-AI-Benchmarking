"""Milestone 3 tests for dated voucher reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
SOURCE_FILE = APP / "data" / "orders.csv"
ACTION_FILE = APP / "data" / "vouchers.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "rally_voucher_report.csv"
SUMMARY = APP / "out" / "rally_voucher_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go voucher reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 3 tests."""
    build_program()


def write_inputs(order_rows, voucher_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated voucher scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_FILE.write_text("order_id,vendor_id,amount_cents,status,meal_tier,order_date\n" + "\n".join(order_rows) + "\n")
    ACTION_FILE.write_text("order_id,vendor_id,amount_cents,meal_tier,voucher_date\n" + "\n".join(voucher_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_legacy_inputs(order_rows, voucher_rows):
    """Use the pre-date schema to verify milestone 3 stays compatible with milestone 2."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SOURCE_FILE.write_text("order_id,vendor_id,amount_cents,status,meal_tier\n" + "\n".join(order_rows) + "\n")
    ACTION_FILE.write_text("order_id,vendor_id,amount_cents,meal_tier\n" + "\n".join(voucher_rows) + "\n")
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
    """Date gates and latest eligible source-row selection for vouchers."""

    def test_milestone3_report_header_and_status_vocabulary(self):
        """Milestone 3 keeps the same report schema and MATCHED and UNMATCHED status labels."""
        write_legacy_inputs(
            ["RLY0001,CUST0001,100,COMPLETED,SNACK"],
            ["RLY0001,CUST0001,100,SN"],
        )
        rows, _ = run_program()
        with REPORT.open(newline="") as handle:
            assert handle.readline().strip() == "order_id,vendor_id,meal_tier,amount_cents,status"
        assert {row["status"] for row in rows} <= {"MATCHED", "UNMATCHED"}

    def test_legacy_schema_without_dates_keeps_prior_alias_and_consumption(self):
        """Pre-date inputs should keep milestone 2 matching without requiring calendar dates."""
        write_legacy_inputs(
            [
                "RLY9001,CUST9001,1200,COMPLETED,COMBO",
                "RLY9001,CUST9001,1200,COMPLETED,COMBO",
                "RLY9002,CUST9002,700,COMPLETED,SNACK",
            ],
            [
                "RLY9001,CUST9001,1200,CB",
                "RLY9001,CUST9001,1200,CB",
                "RLY9002,CUST9002,700,SN",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["meal_tier"] for row in rows] == ["COMBO", "COMBO", "SNACK"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 3100,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_open_voucher_date_and_latest_order_date_win(self):
        """Open voucher_date gates matching; matched row uses canonical meal_tier from latest order_date."""
        write_inputs(
            [
                "RLY9301,CUST9301,1000,COMPLETED,SNACK,2026-04-03",
                "RLY9301,CUST9301,1000,COMPLETED,MEAL,2026-04-04",
                "RLY9302,CUST9302,2000,COMPLETED,MEAL,2026-04-02",
                "RLY9303,CUST9303,3000,COMPLETED,COMBO,2026-04-05",
                "RLY9304,CUST9304,4000,COMPLETED,COMBO,2026-04-05",
            ],
            [
                "RLY9301,CUST9301,1000,ML,2026-04-02",
                "RLY9302,CUST9302,2000,ML,2026-04-04",
                "RLY9303,CUST9303,3000,CB,2026-04-06",
                "RLY9304,CUST9304,4000,COMBO,2026-04-07",
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
        assert rows[0]["meal_tier"] == "MEAL"
        assert [row["meal_tier"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_order_date_tie_uses_record_order_and_consumption(self):
        """Same-date candidates should use source row order and still enforce consumption."""
        write_inputs(
            [
                "RLY9401,CUST9401,500,COMPLETED,MEAL,2026-04-05",
                "RLY9401,CUST9401,500,COMPLETED,MEAL,2026-04-05",
                "RLY9402,CUST9402,700,COMPLETED,SNACK,2026-04-05",
            ],
            [
                "RLY9401,CUST9401,500,ML,2026-04-04",
                "RLY9401,CUST9401,500,ML,2026-04-04",
                "RLY9401,CUST9401,500,ML,2026-04-04",
                "RLY9402,CUST9402,700,SNACK,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["meal_tier"] for row in rows] == ["MEAL", "MEAL", "", "SNACK"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_order_date_wins_before_older_record_is_used(self):
        """Latest order_date must win when the later input row carries the later date."""
        write_inputs(
            [
                "RLY9501,CUST9501,500,COMPLETED,SNACK,2026-04-03",
                "RLY9501,CUST9501,800,COMPLETED,MEAL,2026-04-06",
                "RLY9501,CUST9501,700,COMPLETED,MEAL,2026-04-05",
            ],
            [
                "RLY9501,CUST9501,800,ML,2026-04-02",
                "RLY9501,CUST9501,700,ML,2026-04-04",
                "RLY9501,CUST9501,500,SN,2026-04-03",
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

    def test_closed_voucher_date_is_not_eligible(self):
        """A voucher whose date is listed as closed must not match."""
        write_inputs(
            ["RLY9601,CUST9601,1000,COMPLETED,MEAL,2026-04-10"],
            ["RLY9601,CUST9601,1000,ML,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["meal_tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_voucher_date_is_not_eligible(self):
        """A voucher date absent from the calendar must not be treated as open."""
        write_inputs(
            ["RLY9651,CUST9651,500,COMPLETED,MEAL,2026-04-30"],
            ["RLY9651,CUST9651,500,ML,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["meal_tier"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_voucher_date_is_not_eligible(self):
        """A voucher with an empty voucher_date must not match any order row."""
        write_inputs(
            ["RLY9701,CUST9701,900,COMPLETED,SNACK,2026-04-05"],
            ["RLY9701,CUST9701,900,SNACK,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["meal_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_record_without_order_date_is_not_eligible(self):
        """A source row with an empty order_date cannot be consumed."""
        write_inputs(
            ["RLY9801,CUST9801,700,COMPLETED,COMBO,"],
            ["RLY9801,CUST9801,700,CB,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["meal_tier"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_alias_matches_canonical_record_and_emits_canonical_meal_tier(self):
        """A CB action row should match a COMBO source row and report the canonical meal_tier."""
        write_inputs(
            ["RLY9901,CUST9901,600,COMPLETED,COMBO,2026-04-10"],
            ["RLY9901,CUST9901,600,CB,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["meal_tier"] == "COMBO"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_mismatched_meal_tier_does_not_match_even_with_valid_dates(self):
        """Date logic must not bypass the original meal_tier equality requirement."""
        write_inputs(
            ["RLY9851,CUST9851,775,COMPLETED,SNACK,2026-04-10"],
            ["RLY9851,CUST9851,775,MEAL,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["meal_tier"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 775

    def test_alias_matches_canonical_record_with_dated_matching(self):
        """The SN alias should still normalize to SNACK when date gates are present."""
        write_inputs(
            ["RLY9951,CUST9951,650,COMPLETED,SNACK,2026-04-10"],
            ["RLY9951,CUST9951,650,SN,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["meal_tier"] == "SNACK"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 650,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_calendar_open_keyword_is_case_insensitive(self):
        """Calendar rows marked OPEN or mixed-case Open must be treated as open."""
        write_inputs(
            [
                "RLY8851,CUST8851,500,COMPLETED,MEAL,2026-04-10",
                "RLY8852,CUST8852,600,COMPLETED,SNACK,2026-04-10",
            ],
            [
                "RLY8851,CUST8851,500,ML,2026-04-05",
                "RLY8852,CUST8852,600,SN,2026-04-06",
            ],
            [
                "2026-04-05 OPEN",
                "2026-04-06 Open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["meal_tier"] for row in rows] == ["MEAL", "SNACK"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 1100

    def test_latest_order_date_selection_is_observable_through_consumption(self):
        """The latest eligible source row must be consumed before older eligible rows."""
        write_inputs(
            [
                "RLY8871,CUST8871,1000,COMPLETED,MEAL,2026-04-03",
                "RLY8871,CUST8871,1000,COMPLETED,MEAL,2026-04-06",
            ],
            [
                "RLY8871,CUST8871,1000,ML,2026-04-01",
                "RLY8871,CUST8871,1000,ML,2026-04-05",
            ],
            [
                "2026-04-01 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["meal_tier"] for row in rows] == ["MEAL", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1000,
        }
