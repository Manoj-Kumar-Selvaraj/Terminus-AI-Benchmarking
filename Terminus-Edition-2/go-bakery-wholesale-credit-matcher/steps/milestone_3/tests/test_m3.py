"""Milestone 3 verifier tests for dated order credit reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
ORDERS = APP / "data" / "orders.csv"
CREDITS = APP / "data" / "credits.csv"
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
    assert BIN.exists()


def write_inputs(order_rows, credit_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated credit scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    ORDERS.write_text("order_id,cafe_id,amount_cents,status,route,bake_date\n" + "\n".join(order_rows) + "\n")
    CREDITS.write_text("order_id,cafe_id,amount_cents,route,credit_date\n" + "\n".join(credit_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_legacy_inputs(order_rows, credit_rows, calendar_rows):
    """Replace CSV inputs with the pre-date schema to verify M3 compatibility."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    ORDERS.write_text("order_id,cafe_id,amount_cents,status,route\n" + "\n".join(order_rows) + "\n")
    CREDITS.write_text("order_id,cafe_id,amount_cents,route\n" + "\n".join(credit_rows) + "\n")
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
    """Date gates and latest eligible order selection for credits."""

    def test_legacy_schema_without_dates_keeps_prior_alias_and_consumption_behavior(self):
        """Pre-date inputs should keep milestone 2 matching instead of requiring calendar dates."""
        write_legacy_inputs(
            [
                "BILL9001,CUST9001,1200,FULFILLED,REGIONAL",
                "BILL9001,CUST9001,1200,FULFILLED,REGIONAL",
                "BILL9002,CUST9002,700,FULFILLED,EXPORT",
                "BILL9003,CUST9003,500,PENDING,LOCAL",
            ],
            [
                "BILL9001,CUST9001,1200,REG",
                "BILL9001,CUST9001,1200,REG",
                "BILL9001,CUST9001,1200,REG",
                "BILL9002,CUST9002,700,EXP",
                "BILL9003,CUST9003,500,LOC",
            ],
            [],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED", "UNMATCHED"]
        assert [row["route"] for row in rows] == ["REGIONAL", "REGIONAL", "", "EXPORT", ""]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 3100,
            "unmatched_count": 2,
            "unmatched_amount_cents": 1700,
        }

    def test_status_case_insensitive_and_trimmed(self):
        """Status matching should accept FULFILLED after trimming and case folding."""
        write_inputs(
            [
                "BILL8001,CUST8001,500, fulfilled ,LOCAL,2026-04-10",
                "BILL8001,CUST8001,500,FULFILLED,LOCAL,2026-04-05",
            ],
            ["BILL8001,CUST8001,500,LOC,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["route"] == "LOCAL"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 500,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_date_and_prior_match_gates_apply_before_latest_bake_date(self):
        """Only rows passing identity, route, status, and date gates should be ranked by bake_date."""
        write_inputs(
            [
                "BILL9301,CUST9301,1000,FULFILLED,LOCAL,2026-04-03",
                "BILL9301,CUST9301,1000,FULFILLED,REGIONAL,2026-04-04",
                "BILL9302,CUST9302,2000,FULFILLED,REGIONAL,2026-04-02",
                "BILL9303,CUST9303,3000,FULFILLED,EXPORT,2026-04-05",
                "BILL9304,CUST9304,4000,FULFILLED,EXPORT,2026-04-05",
            ],
            [
                "BILL9301,CUST9301,1000,REG,2026-04-02",
                "BILL9302,CUST9302,2000,REG,2026-04-04",
                "BILL9303,CUST9303,3000,EXP,2026-04-06",
                "BILL9304,CUST9304,4000,EXPORT,2026-04-07",
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
        assert rows[0]["route"] == "REGIONAL"
        assert [row["route"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_bake_date_duplicates_are_consumed_by_row_count(self):
        """Same-date duplicate order rows should allow two matches and leave the third duplicate credit unmatched."""
        write_inputs(
            [
                "BILL9401,CUST9401,500,FULFILLED,REGIONAL,2026-04-05",
                "BILL9401,CUST9401,500,FULFILLED,REGIONAL,2026-04-05",
                "BILL9402,CUST9402,700,FULFILLED,LOCAL,2026-04-05",
            ],
            [
                "BILL9401,CUST9401,500,REG,2026-04-04",
                "BILL9401,CUST9401,500,REG,2026-04-04",
                "BILL9401,CUST9401,500,REG,2026-04-04",
                "BILL9402,CUST9402,700,LOCAL,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["route"] for row in rows] == ["REGIONAL", "REGIONAL", "", "LOCAL"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_bake_date_wins_before_older_record_is_used(self):
        """A later eligible bake_date should be consumed before an older eligible source row."""
        write_inputs(
            [
                "BILL9501,CUST9501,800,FULFILLED,REGIONAL,2026-04-06",
                "BILL9501,CUST9501,800,FULFILLED,REGIONAL,2026-04-03",
            ],
            [
                "BILL9501,CUST9501,800,REG,2026-04-02",
                "BILL9501,CUST9501,800,REG,2026-04-04",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["route"] for row in rows] == ["REGIONAL", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_closed_credit_date_is_not_eligible(self):
        """A credit whose date is listed as closed must not match."""
        write_inputs(
            ["BILL9601,CUST9601,1000,FULFILLED,REGIONAL,2026-04-10"],
            ["BILL9601,CUST9601,1000,REG,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["route"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_calendar_open_state_is_case_insensitive_and_malformed_rows_are_ignored(self):
        """Calendar parsing should ignore one-token and extra-token rows while accepting open state case-insensitively."""
        write_inputs(
            [
                "BILL9151,CUST9151,910,FULFILLED,LOCAL,2026-04-09",
                "BILL9152,CUST9152,920,FULFILLED,REGIONAL,2026-04-09",
            ],
            [
                "BILL9151,CUST9151,910,LOC,2026-04-04",
                "BILL9152,CUST9152,920,REG,2026-04-06",
            ],
            ["malformed-calendar-line", "2026-04-04 OpEn", "2026-04-06 open extra-token"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["route"] for row in rows] == ["LOCAL", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 910,
            "unmatched_count": 1,
            "unmatched_amount_cents": 920,
        }

    def test_unlisted_credit_date_is_not_eligible(self):
        """A credit date absent from the calendar must not be treated as open."""
        write_inputs(
            ["BILL9651,CUST9651,500,FULFILLED,REGIONAL,2026-04-30"],
            ["BILL9651,CUST9651,500,REG,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["route"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_credit_date_is_not_eligible(self):
        """A credit with an empty credit_date must not match any order."""
        write_inputs(
            ["BILL9701,CUST9701,900,FULFILLED,LOCAL,2026-04-05"],
            ["BILL9701,CUST9701,900,LOCAL,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["route"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_record_without_bake_date_is_not_eligible(self):
        """An order with an empty bake_date cannot be consumed."""
        write_inputs(
            ["BILL9801,CUST9801,700,FULFILLED,EXPORT,"],
            ["BILL9801,CUST9801,700,EXP,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["route"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_exp_alias_matches_export_record_and_emits_canonical_route(self):
        """A EXP credit should match a EXPORT order and report the canonical route."""
        write_inputs(
            ["BILL9901,CUST9901,600,FULFILLED,EXPORT,2026-04-10"],
            ["BILL9901,CUST9901,600,EXP,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["route"] == "EXPORT"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }


    def test_mismatched_route_does_not_match_even_with_valid_dates(self):
        """Date logic must not bypass the original route equality requirement."""
        write_inputs(
            ["BILL9851,CUST9851,775,FULFILLED,LOCAL,2026-04-10"],
            ["BILL9851,CUST9851,775,REGIONAL,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["route"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 775

    def test_prior_match_criteria_still_reject_latest_bake_date_decoy(self):
        """A later bake_date must not win unless order_id, cafe_id, amount, and route all match."""
        write_inputs(
            [
                "BILL9961,CUST9961,700,FULFILLED,LOCAL,2026-04-08",
                "BILL9961,CUST9961,700,FULFILLED,REGIONAL,2026-04-12",
                "BILL9961,CUST9999,700,FULFILLED,LOCAL,2026-04-15",
            ],
            ["BILL9961,CUST9961,700,LOC,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["route"] == "LOCAL"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 700,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_wrong_order_id_does_not_match_despite_later_bake_date_decoy(self):
        """order_id equality must still gate matching when a later-dated decoy row exists."""
        write_inputs(
            [
                "BILL9971,CUST9971,600,FULFILLED,LOCAL,2026-04-08",
                "BILL9972,CUST9971,600,FULFILLED,LOCAL,2026-04-15",
            ],
            ["BILL9971,CUST9971,600,LOC,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["route"] == "LOCAL"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 600

    def test_wrong_cafe_id_does_not_match_despite_later_bake_date_decoy(self):
        """cafe_id equality must still gate matching when a later-dated decoy row exists."""
        write_inputs(
            [
                "BILL9981,CUST9981,650,FULFILLED,LOCAL,2026-04-08",
                "BILL9981,CUST9982,650,FULFILLED,LOCAL,2026-04-15",
            ],
            ["BILL9981,CUST9981,650,LOC,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["route"] == "LOCAL"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 650

    def test_wrong_amount_does_not_match_despite_later_bake_date_decoy(self):
        """amount_cents equality must still gate matching when a later-dated decoy row exists."""
        write_inputs(
            [
                "BILL9991,CUST9991,700,FULFILLED,LOCAL,2026-04-08",
                "BILL9991,CUST9991,900,FULFILLED,LOCAL,2026-04-15",
            ],
            ["BILL9991,CUST9991,700,LOC,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["route"] == "LOCAL"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 700

    def test_loc_alias_matches_local_record_with_dated_matching(self):
        """The LOC alias should still normalize to LOCAL when date gates are present."""
        write_inputs(
            ["BILL9951,CUST9951,650,FULFILLED,LOCAL,2026-04-10"],
            ["BILL9951,CUST9951,650,LOC,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["route"] == "LOCAL"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 650,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
