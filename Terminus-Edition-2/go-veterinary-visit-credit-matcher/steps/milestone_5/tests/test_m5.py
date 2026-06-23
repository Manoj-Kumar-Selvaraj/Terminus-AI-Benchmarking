"""Milestone 5 tests for clinic-day calendar controls."""

import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
GO = Path("/usr/local/go/bin/go")
BIN = APP / "build" / "reconcile"
VISITS = APP / "data" / "visits.csv"
CREDITS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
POLICY = APP / "config" / "clinic_policy.csv"
CLINIC_CAL = APP / "config" / "clinic_calendar.txt"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"


def build_program():
    """Compile the Go reconciler."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


def write_csv(path, header, rows):
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(visits, credits, clinic_calendar, cutoff=None, policy=None):
    write_csv(
        VISITS,
        ["visit_id", "owner_id", "amount_cents", "status", "clinic", "service_date"],
        visits,
    )
    write_csv(
        CREDITS,
        ["visit_id", "owner_id", "amount_cents", "clinic", "credit_date"],
        credits,
    )
    write_csv(
        POLICY,
        ["clinic", "enabled", "priority"],
        policy or [["MAIN", "true", "2"], ["MOBILE", "true", "1"], ["ER", "true", "3"]],
    )
    CALENDAR.write_text("\n".join(cutoff or ["2026-04-01 open", "2026-04-02 open", "2026-04-03 open", "2026-04-04 open"]) + "\n")
    CLINIC_CAL.write_text("\n".join(clinic_calendar) + "\n")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone5:
    def test_clinic_calendar_allows_two_open_days_but_blocks_three(self):
        """At most two open clinic days after the visit service_date are eligible."""
        build_program()
        write_inputs(
            [
                ["VET-CAL-1", "OWN-CAL-1", "10", "CLOSED", "MAIN", "2026-04-01"],
                ["VET-CAL-2", "OWN-CAL-2", "20", "CLOSED", "MAIN", "2026-04-01"],
            ],
            [
                ["VET-CAL-1", "OWN-CAL-1", "10", "MAIN", "2026-04-03"],
                ["VET-CAL-2", "OWN-CAL-2", "20", "MAIN", "2026-04-04"],
            ],
            [
                "2026-04-01 OPEN",
                "2026-04-02 OPEN",
                "2026-04-03 OPEN",
                "2026-04-04 OPEN",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 10,
            "unmatched_count": 1,
            "unmatched_amount_cents": 20,
        }

    def test_same_day_and_closed_or_absent_clinic_dates_reject(self):
        """Same-day credits are eligible, but closed or unlisted clinic dates are not."""
        build_program()
        write_inputs(
            [
                ["VET-SAME", "OWN-SAME", "11", "CLOSED", "MOBILE", "2026-04-02"],
                ["VET-CLOSED", "OWN-CLOSED", "12", "CLOSED", "MOBILE", "2026-04-02"],
                ["VET-ABSENT", "OWN-ABSENT", "13", "CLOSED", "MOBILE", "2026-04-05"],
            ],
            [
                ["VET-SAME", "OWN-SAME", "11", "MOBILE", "2026-04-02"],
                ["VET-CLOSED", "OWN-CLOSED", "12", "MOBILE", "2026-04-04"],
                ["VET-ABSENT", "OWN-ABSENT", "13", "MOBILE", "2026-04-05"],
            ],
            [
                "2026-04-02 OPEN",
                "2026-04-03 OPEN",
                "2026-04-04 CLOSED",
            ],
            cutoff=["2026-04-02 open", "2026-04-03 open", "2026-04-04 open", "2026-04-05 open"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED"]
        assert [row["clinic"] for row in rows] == ["MOBILE", "", ""]
        assert summary["matched_amount_cents"] == 11
        assert summary["unmatched_amount_cents"] == 25

    def test_policy_any_and_row_consumption_still_apply_under_calendar_gate(self):
        """Calendar support must preserve policy-driven ANY selection and row consumption."""
        build_program()
        write_inputs(
            [
                ["VET-MIX", "OWN-MIX", "30", "CLOSED", "MAIN", "2026-04-01"],
                ["VET-MIX", "OWN-MIX", "30", "CLOSED", "MOBILE", "2026-04-01"],
            ],
            [
                ["VET-MIX", "OWN-MIX", "30", "ANY", "2026-04-02"],
                ["VET-MIX", "OWN-MIX", "30", "ANY", "2026-04-02"],
            ],
            ["2026-04-01 OPEN", "2026-04-02 OPEN"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["clinic"] for row in rows] == ["MOBILE", "MAIN"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 60

    def test_blank_dates_follow_undated_matching_under_calendar_files(self):
        """Blank service_date and credit_date pairs skip calendar gates and match like milestone 2."""
        build_program()
        write_inputs(
            [
                ["VET-UND-1", "OWN-UND", "15", "CLOSED", "MOBILE", ""],
                ["VET-UND-1", "OWN-UND", "15", "CLOSED", "MAIN", ""],
            ],
            [
                ["VET-UND-1", "OWN-UND", "15", "VAN", ""],
                ["VET-UND-1", "OWN-UND", "15", "MN", ""],
            ],
            ["2026-04-01 OPEN"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["clinic"] for row in rows] == ["MOBILE", "MAIN"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 30
