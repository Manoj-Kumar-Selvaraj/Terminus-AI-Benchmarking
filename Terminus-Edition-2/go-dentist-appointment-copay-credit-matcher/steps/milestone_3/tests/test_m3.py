"""Milestone 3 verifier tests for dated appointment credit reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
APPOINTMENTS = APP / "data" / "appointments.csv"
CREDITS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "copay_credit_report.csv"
SUMMARY = APP / "out" / "copay_credit_summary.json"
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


def write_inputs(appointment_rows, credit_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated credit scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    APPOINTMENTS.write_text("appointment_id,patient_id,amount_cents,status,service_type,appointment_date\n" + "\n".join(appointment_rows) + "\n")
    CREDITS.write_text("appointment_id,patient_id,amount_cents,service_type,credit_date\n" + "\n".join(credit_rows) + "\n")
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
    """Date gates and latest eligible appointment selection for credits."""

    def test_undated_inputs_apply_milestone_2_matching_without_calendar_gates(self):
        """Without date columns, matching must follow milestone 2 rules and ignore the calendar."""
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        APPOINTMENTS.write_text(
            "appointment_id,patient_id,amount_cents,status,service_type\n"
            "UND8001,CUST8001,1000,ACTIVE,CLEAN\n"
            "UND8002,CUST8002,2000,ACTIVE,XRAY\n"
        )
        CREDITS.write_text(
            "appointment_id,patient_id,amount_cents,service_type\n"
            "UND8001,CUST8001,1000,CL\n"
            "UND8002,CUST8002,2000,XR\n"
        )
        CALENDAR.write_text("2026-04-01 closed\n")
        REPORT.unlink(missing_ok=True)
        SUMMARY.unlink(missing_ok=True)
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["service_type"] for row in rows] == ["CLEAN", "XRAY"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 3000,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_open_credit_date_and_latest_appointment_date_win(self):
        """Open credit dates should gate matching and latest eligible source date should win."""
        write_inputs(
            [
                "BILL9301,CUST9301,1000,ACTIVE,CLEAN,2026-04-03",
                "BILL9301,CUST9301,1000,ACTIVE,XRAY,2026-04-04",
                "BILL9302,CUST9302,2000,ACTIVE,XRAY,2026-04-02",
                "BILL9303,CUST9303,3000,ACTIVE,SURG,2026-04-05",
                "BILL9304,CUST9304,4000,ACTIVE,SURG,2026-04-05",
            ],
            [
                "BILL9301,CUST9301,1000,XR,2026-04-02",
                "BILL9302,CUST9302,2000,XR,2026-04-04",
                "BILL9303,CUST9303,3000,SG,2026-04-06",
                "BILL9304,CUST9304,4000,SURG,2026-04-07",
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
        assert rows[0]["service_type"] == "XRAY"
        assert [row["service_type"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_appointment_date_tie_uses_appointment_order_and_consumption(self):
        """Same-date candidates should use appointment order and still enforce consumption."""
        write_inputs(
            [
                "BILL9401,CUST9401,500,ACTIVE,XRAY,2026-04-05",
                "BILL9401,CUST9401,500,ACTIVE,XRAY,2026-04-05",
                "BILL9402,CUST9402,700,ACTIVE,CLEAN,2026-04-05",
            ],
            [
                "BILL9401,CUST9401,500,XR,2026-04-04",
                "BILL9401,CUST9401,500,XR,2026-04-04",
                "BILL9401,CUST9401,500,XR,2026-04-04",
                "BILL9402,CUST9402,700,CLEAN,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["service_type"] for row in rows] == ["XRAY", "XRAY", "", "CLEAN"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_appointment_date_wins_before_older_appointment_row_is_used(self):
        """Latest appointment_date must win; consuming the older row leaves the second credit ineligible."""
        write_inputs(
            [
                "BILL9501,CUST9501,800,ACTIVE,XRAY,2026-04-03",
                "BILL9501,CUST9501,800,ACTIVE,XRAY,2026-04-06",
            ],
            [
                "BILL9501,CUST9501,800,XR,2026-04-02",
                "BILL9501,CUST9501,800,XR,2026-04-04",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["service_type"] for row in rows] == ["XRAY", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_closed_credit_date_is_not_eligible(self):
        """A credit whose date is listed as closed must not match."""
        write_inputs(
            ["BILL9601,CUST9601,1000,ACTIVE,XRAY,2026-04-10"],
            ["BILL9601,CUST9601,1000,XR,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["service_type"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_credit_date_is_not_eligible(self):
        """A credit date absent from the calendar must not be treated as open."""
        write_inputs(
            ["BILL9651,CUST9651,500,ACTIVE,XRAY,2026-04-30"],
            ["BILL9651,CUST9651,500,XR,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["service_type"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_credit_date_is_not_eligible(self):
        """A credit with an empty credit_date must not match any appointment."""
        write_inputs(
            ["BILL9701,CUST9701,900,ACTIVE,CLEAN,2026-04-05"],
            ["BILL9701,CUST9701,900,CLEAN,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["service_type"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_appointment_without_appointment_date_is_not_eligible(self):
        """A appointment with an empty appointment_date cannot be consumed."""
        write_inputs(
            ["BILL9801,CUST9801,700,ACTIVE,SURG,"],
            ["BILL9801,CUST9801,700,SG,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["service_type"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_latest_appointment_date_wins_even_when_later_dated_row_appears_first(self):
        """Among same service_type rows, latest appointment_date wins even when it appears earlier in the file."""
        write_inputs(
            [
                "BILL9051,CUST9051,1000,ACTIVE,XRAY,2026-04-08",
                "BILL9051,CUST9051,1000,ACTIVE,XRAY,2026-04-03",
            ],
            [
                "BILL9051,CUST9051,1000,XR,2026-04-02",
                "BILL9051,CUST9051,1000,XR,2026-04-04",
            ],
            ["2026-04-02 open", "2026-04-04 open"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[0]["service_type"] == "XRAY"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1000,
        }

    def test_cl_alias_matches_clean_under_dated_matching(self):
        """The CL alias should still normalize to CLEAN when date gates are present."""
        write_inputs(
            ["BILL9951,CUST9951,650,ACTIVE,CLEAN,2026-04-10"],
            ["BILL9951,CUST9951,650,CL,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_type"] == "CLEAN"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 650,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_sg_alias_matches_surg_appointment_and_emits_canonical_service_type(self):
        """A SG credit should match a SURG appointment and report the canonical service_type."""
        write_inputs(
            ["BILL9901,CUST9901,600,ACTIVE,SURG,2026-04-10"],
            ["BILL9901,CUST9901,600,SG,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_type"] == "SURG"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_malformed_action_date_stays_unmatched(self):
        """A malformed credit_date must not be treated as an open eligible calendar date."""
        write_inputs(
            ["BADDTE1,CUSTBD1,1400,ACTIVE,CLEAN,2026-04-10"],
            ["BADDTE1,CUSTBD1,1400,CLEAN,not-a-date"],
            ["2026-04-04 open", "2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["service_type"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 1400
