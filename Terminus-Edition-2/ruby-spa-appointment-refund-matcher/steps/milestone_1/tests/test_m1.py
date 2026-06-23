"""Milestone 1 tests for the Ruby spa appointment refund reconciler."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
APPOINTMENTS = APP / "data" / "appointments.csv"
REFUNDS = APP / "data" / "refunds.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
ALIASES = APP / "config" / "service_aliases.csv"
METHODS = APP / "config" / "methods.csv"
LIMITS = APP / "config" / "client_limits.csv"
REPORT = APP / "out" / "refund_report.csv"
SUMMARY = APP / "out" / "refund_summary.json"
BASE_APPT_HEADERS = ["appointment_id", "client_id", "amount_cents", "status", "service_area"]
BASE_REFUND_HEADERS = ["appointment_id", "client_id", "amount_cents", "service_area"]
DATED_APPT_HEADERS = BASE_APPT_HEADERS + ["service_date"]
DATED_REFUND_HEADERS = BASE_REFUND_HEADERS + ["refund_date"]


def write_csv(path, headers, rows):
    """Write a CSV file using the supplied headers and row arrays."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        writer.writerows(rows)


def write_inputs(source_rows, refund_rows, source_headers=None, refund_headers=None):
    """Replace appointment and refund inputs with a scenario-specific dataset."""
    write_csv(APPOINTMENTS, source_headers or BASE_APPT_HEADERS, source_rows)
    write_csv(REFUNDS, refund_headers or BASE_REFUND_HEADERS, refund_rows)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_calendar(lines):
    """Replace the open-date calendar text file."""
    CALENDAR.parent.mkdir(parents=True, exist_ok=True)
    CALENDAR.write_text("\n".join(lines) + "\n")


def write_aliases(rows, headers=("alias", "canonical", "enabled")):
    """Replace the runtime service alias configuration."""
    write_csv(ALIASES, list(headers), rows)


def write_methods(rows, headers=("service_area", "enabled", "priority")):
    """Replace the runtime service policy configuration."""
    write_csv(METHODS, list(headers), rows)


def write_limits(rows, headers=("client_id", "service_area", "max_refund_cents", "enabled", "allow_any")):
    """Replace the runtime client limit policy configuration."""
    write_csv(LIMITS, list(headers), rows)


def run_program():
    """Run the batch command and return parsed report rows plus JSON summary."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


def assert_schema(rows):
    """Assert the public report schema exactly."""
    assert rows
    assert list(rows[0].keys()) == ["appointment_id", "client_id", "service_area", "amount_cents", "status"]

class TestMilestone1:
    """Base exact-gate, parsing, consumption, and output contract checks."""

    def test_all_canonical_services_match_and_emit_uppercase(self):
        """All supported canonical service values should match and emit canonical uppercase output."""
        write_inputs(
            [
                ["M1A", "C1", "1200", "COMPLETED", "massage"],
                ["M1B", "C2", "2300", "completed", "Facial"],
                ["M1C", "C3", "3400", "COMPLETED", "SAUNA"],
            ],
            [["M1A", "C1", "1200", "MASSAGE"], ["M1B", "C2", "2300", "facial"], ["M1C", "C3", "3400", "sauna"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["service_area"] for row in rows] == ["MASSAGE", "FACIAL", "SAUNA"]
        assert summary == {"matched_count": 3, "matched_amount_cents": 6900, "unmatched_count": 0, "unmatched_amount_cents": 0}

    def test_full_identifier_matching_rejects_prefix_collision(self):
        """Shared prefixes must not satisfy the appointment_id gate."""
        write_inputs(
            [["PREFIX770001", "CUST2001", "3300", "COMPLETED", "MASSAGE"], ["PREFIX770002", "CUST2001", "3300", "COMPLETED", "MASSAGE"]],
            [["PREFIX770003", "CUST2001", "3300", "MASSAGE"], ["PREFIX770002", "CUST2001", "3300", "MASSAGE"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["service_area"] == ""
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300

    def test_customer_amount_status_and_service_all_gate_matching(self):
        """Customer, amount, status, and service must all pass before a row can match."""
        write_inputs(
            [
                ["GATE1", "C1", "1000", "COMPLETED", "MASSAGE"],
                ["GATE2", "C2", "2000", "COMPLETED", "FACIAL"],
                ["GATE3", "C3", "3000", "DRAFT", "SAUNA"],
                ["GATE4", "C4", "4000", "COMPLETED", "CHECK"],
                ["GATE5", "C5", "5000", "COMPLETED", "SAUNA"],
            ],
            [["GATE1", "WRONG", "1000", "MASSAGE"], ["GATE2", "C2", "2100", "FACIAL"], ["GATE3", "C3", "3000", "SAUNA"], ["GATE4", "C4", "4000", "CHECK"], ["GATE5", "C5", "5000", "SAUNA"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["service_area"] == "SAUNA"
        assert summary["matched_count"] == 1
        assert summary["unmatched_amount_cents"] == 10100

    def test_duplicate_refunds_do_not_reuse_consumed_appointment_row(self):
        """A single appointment row can satisfy only one refund row."""
        write_inputs([["DUP1", "C1", "5500", "COMPLETED", "FACIAL"]], [["DUP1", "C1", "5500", "FACIAL"], ["DUP1", "C1", "5500", "FACIAL"]])
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 1
        assert summary["unmatched_count"] == 1

    def test_first_appointment_row_wins_when_multiple_rows_are_eligible(self):
        """Consumption must follow physical row order when multiple appointment rows qualify."""
        write_inputs(
            [
                ["DUP1", "C1", "5500", "COMPLETED", "FACIAL"],
                ["DUP1", "C1", "5500", "COMPLETED", "FACIAL"],
            ],
            [
                ["DUP1", "C1", "5500", "FACIAL"],
                ["DUP1", "C1", "5500", "FACIAL"],
                ["DUP1", "C1", "5500", "FACIAL"],
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 2
        assert summary["unmatched_count"] == 1

    def test_header_addressing_handles_reordered_and_extra_columns(self):
        """The reconciler should use headers, not physical column positions."""
        write_inputs(
            [["ignored", "COMPLETED", "FACIAL", "HDR1", "C1", "777"]],
            [["FACIAL", "another", "777", "C1", "HDR1"]],
            source_headers=["extra", "status", "service_area", "appointment_id", "client_id", "amount_cents"],
            refund_headers=["service_area", "extra_refund", "amount_cents", "client_id", "appointment_id"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service_area"] == "FACIAL"
        assert summary["matched_amount_cents"] == 777

    def test_invalid_amounts_count_unmatched_but_do_not_add_amount_totals(self):
        """Malformed, zero, signed, and decimal refund amounts should be counted but not totaled."""
        write_inputs(
            [["BAD1", "C1", "100", "COMPLETED", "MASSAGE"], ["BAD2", "C2", "200", "COMPLETED", "FACIAL"]],
            [["BAD1", "C1", "10x", "MASSAGE"], ["BAD2", "C2", "0", "FACIAL"], ["BAD3", "C3", "-9", "SAUNA"], ["BAD4", "C4", "1.5", "SAUNA"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary == {"matched_count": 0, "matched_amount_cents": 0, "unmatched_count": 4, "unmatched_amount_cents": 0}

    def test_report_amount_preserves_trimmed_refund_string_with_leading_zeroes(self):
        """Matching uses integer value but report amount preserves the input string."""
        write_inputs([["ZERO1", "C1", "1000", "COMPLETED", "MASSAGE"]], [[" ZERO1 ", " C1 ", " 01000 ", " massage "]])
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["amount_cents"] == "01000"
        assert summary["matched_amount_cents"] == 1000

    def test_unmatched_valid_amounts_are_totaled_in_input_order(self):
        """Valid unmatched amounts should contribute to unmatched_amount_cents."""
        write_inputs([["UM1", "C1", "1000", "COMPLETED", "MASSAGE"]], [["NO1", "C1", "25", "MASSAGE"], ["NO2", "C2", "075", "SAUNA"]])
        rows, summary = run_program()
        assert [row["appointment_id"] for row in rows] == ["NO1", "NO2"]
        assert summary["unmatched_count"] == 2
        assert summary["unmatched_amount_cents"] == 100

    def test_report_schema_and_blank_unmatched_service_are_stable(self):
        """Report columns and blank unmatched service values should be exact."""
        write_inputs([["SCHEMA1", "C1", "1100", "COMPLETED", "FACIAL"]], [["NO_MATCH", "C9", "9900", "MASSAGE"], ["SCHEMA1", "C1", "1100", "FACIAL"]])
        rows, summary = run_program()
        assert_schema(rows)
        assert [row["appointment_id"] for row in rows] == ["NO_MATCH", "SCHEMA1"]
        assert rows[0]["service_area"] == ""
        assert rows[1]["service_area"] == "FACIAL"
        assert summary["matched_count"] == 1

    def test_outputs_are_regenerated_not_appended_or_reused(self):
        """Stale output content must be overwritten on each run."""
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        REPORT.write_text("appointment_id,client_id,service_area,amount_cents,status\nSTALE,C,SAUNA,1,MATCHED\n")
        SUMMARY.write_text('{"matched_count":99,"matched_amount_cents":99,"unmatched_count":99,"unmatched_amount_cents":99}')
        write_inputs([["FRESH1", "C1", "444", "COMPLETED", "SAUNA"]], [["FRESH1", "C1", "444", "SAUNA"]])
        rows, summary = run_program()
        assert len(rows) == 1
        assert rows[0]["appointment_id"] == "FRESH1"
        assert summary == {"matched_count": 1, "matched_amount_cents": 444, "unmatched_count": 0, "unmatched_amount_cents": 0}
