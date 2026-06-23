"""Verifier tests for parking garage session adjustment clearing milestone 3."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "sessions.csv"
ACTION = APP / "data" / "adjustments.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "cod_parking_adjustment_report.csv"
SUMMARY = APP / "out" / "cod_parking_adjustment_summary.txt"


def write_csv(path, header, rows):
    """Write one CSV fixture."""
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(source, action, windows):
    """Overwrite all input files at runtime."""
    write_csv(SOURCE, ["parcel_id", "plate_id", "station_id", "rate_type", "amount", "entry_ts", "status", "level"], source)
    write_csv(ACTION, ["adjustment_id", "parcel_id", "plate_id", "station_id", "rate_type", "amount", "adjust_ts", "reason", "level"], action)
    write_csv(WINDOWS, ["station_id", "open_ts", "close_ts", "state"], windows)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the reconciler and parse outputs."""
    subprocess.run(["ruby", "/app/app/reconcile.rb"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {}
    for line in SUMMARY.read_text().strip().splitlines():
        key, value = line.strip().split("=", 1)
        summary[key.strip()] = int(value.strip())
    return rows, summary


class TestMilestone3:
    def test_window_state_malformed_times_latest_candidate_and_order(self):
        """Window eligibility, malformed times, latest candidate selection, order, and blank unmatched rate_type should hold."""
        write_inputs(
            [
                ["SRC-WIN-1", "PARTY-1", "S-O", "HOURLY", "1", "20260528150000", "CLOSED", "L1"],
                ["SRC-WIN-2", "PARTY-2", "S-C", "HOURLY", "2", "20260528150000", "CLOSED", "L2"],
                ["SRC-WIN-3", "PARTY-3", "S-M", "DAILY", "3", "bad-time", "CLOSED", "L3"],
                ["SRC-DDYE", "PARTY-4", "S-O", "EVENT", "4", "20260528150100", "CLOSED", "L4"],
                ["SRC-DDYE", "PARTY-4", "S-O", "EVENT", "4", "20260528150200", "CLOSED", "L4"],
            ],
            [
                ["ACT-1", "SRC-WIN-1", "PARTY-1", "S-O", "HOURLY", "1", "20260528150500", "REFUND", "L1"],
                ["ACT-2", "SRC-WIN-2", "PARTY-2", "S-C", "HOURLY", "2", "20260528150500", "REFUND", "L2"],
                ["ACT-3", "SRC-WIN-3", "PARTY-3", "S-M", "DAILY", "3", "20260528150500", "SHORT", "L3"],
                ["ACT-4", "SRC-DDYE", "PARTY-4", "S-O", "CC", "4", "20260528150600", "WAIVE", "L4"],
            ],
            [["S-O", "20260528145900", "20260528153000", "OPEN"], ["S-C", "20260528145900", "20260528153000", "CLOS"], ["S-M", "bad-time", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["adjustment_id"] for row in rows] == ["ACT-1", "ACT-2", "ACT-3", "ACT-4"]
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert [row["rate_type"] for row in rows] == ["HOURLY", "", "", "EVENT"]
        assert summary == {"matched_count": 2, "matched_amount": 5, "unmatched_count": 2, "unmatched_amount": 5}

    def test_adjustment_after_window_close_is_rejected(self):
        """A correction whose adjust_ts is after the window close must not match."""
        write_inputs(
            [["SRC-CLOSE-1", "PARTY-C", "S-CLOSE", "HOURLY", "11", "20260528180000", "CLOSED", "L1"]],
            [["ACT-CLOSE-1", "SRC-CLOSE-1", "PARTY-C", "S-CLOSE", "HOURLY", "11", "20260528183001", "REFUND", "L1"]],
            [["S-CLOSE", "20260528175900", "20260528183000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["rate_type"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount"] == 11

    def test_adjustment_at_window_close_boundary_matches(self):
        """A correction whose adjust_ts equals the window close should still match."""
        write_inputs(
            [["SRC-BOUND-1", "PARTY-B", "S-BOUND", "DAILY", "22", "20260528190000", "CLOSED", "L1"]],
            [["ACT-BOUND-1", "SRC-BOUND-1", "PARTY-B", "S-BOUND", "DAILY", "22", "20260528193000", "WAIVE", "L1"]],
            [["S-BOUND", "20260528185900", "20260528193000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["rate_type"] == "DAILY"
        assert summary["matched_amount"] == 22

    def test_equal_entry_ts_tie_uses_earliest_source_row(self):
        """When entry_ts ties, the earliest source input row must win."""
        write_inputs(
            [
                ["SRC-TIE-1", "PARTY-T", "S-TIE", "HOURLY", "33", "20260528200000", "CLOSED", "L1"],
                ["SRC-TIE-1", "PARTY-T", "S-TIE", "DAILY", "44", "20260528200000", "CLOSED", "L1"],
            ],
            [
                ["ACT-TIE-1", "SRC-TIE-1", "PARTY-T", "S-TIE", "HR", "33", "20260528200100", "SHORT", "L1"],
                ["ACT-TIE-2", "SRC-TIE-1", "PARTY-T", "S-TIE", "QR", "44", "20260528200200", "SHORT", "L1"],
            ],
            [["S-TIE", "20260528195900", "20260528203000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["rate_type"] for row in rows] == ["HOURLY", "DAILY"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount"] == 77

    def test_unlisted_station_stays_unmatched(self):
        """A station_id with no window row must stay unmatched."""
        write_inputs(
            [["SRC-U", "PARTY-U", "S-UNLISTED", "HOURLY", "7", "20260528150000", "CLOSED", "L1"]],
            [["ACT-U", "SRC-U", "PARTY-U", "S-UNLISTED", "HR", "7", "20260528150500", "REFUND", "L1"]],
            [["S-OTHER", "20260528145900", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["rate_type"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 7}

    def test_level_mismatch_stays_unmatched_under_regression_gate(self):
        """Milestone 3 must still enforce the level identity gate with aliases active."""
        write_inputs(
            [["SRC-LOC", "PARTY-L", "S-O", "EVENT", "19", "20260528150000", "CLOSED", "L-ORIG"]],
            [["ACT-LOC", "SRC-LOC", "PARTY-L", "S-O", "CC", "19", "20260528150500", "WAIVE", "L-OTHER"]],
            [["S-O", "20260528145900", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["rate_type"] == ""
        assert summary["unmatched_amount"] == 19
