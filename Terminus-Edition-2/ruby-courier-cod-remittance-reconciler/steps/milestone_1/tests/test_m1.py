"""Milestone 1 tests for realtime courier COD remittance reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "deliveries.csv"
ACTION = APP / "data" / "remittances.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "cod_remittance_report.csv"
SUMMARY = APP / "out" / "cod_remittance_summary.txt"


def build_program():
    """Prepare the reconciler for one reconciliation scenario."""
    pass


def write_csv(path, header, rows):
    """Write one CSV fixture."""
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(source, action, windows):
    """Overwrite all input files at runtime."""
    write_csv(SOURCE, ["parcel_id", "courier_id", "station_id", "kind", "amount", "source_ts", "status", "location"], source)
    write_csv(ACTION, ["action_id", "parcel_id", "courier_id", "station_id", "kind", "amount", "action_ts", "reason", "location"], action)
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
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        summary[key] = int(value)
    return rows, summary


class TestMilestone1:
    def test_all_gates_consumption_and_positive_unmatched_totals(self):
        """Every identity, status, timestamp, reason, kind, and consumption gate should reject bad candidates."""
        build_program()
        write_inputs(
            [
                ["SRC-GATE-1", "PARTY-1", "S-G", "CASH", "10", "20260528140000", "DELIVERED", "L1"],
                ["SRC-GATE-2", "PARTY-2", "S-G", "CASH", "20", "20260528140100", "BAD", "L2"],
                ["SRC-GATE-3", "PARTY-3", "S-G", "UPI", "30", "20260528140200", "DELIVERED", "L3"],
                ["SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140300", "DELIVERED", "L4"],
                ["SRC-GATE-5", "PARTY-5", "S-G", "CARD", "50", "20260528140400", "DELIVERED", "L5"],
            ],
            [
                ["ACT-A", "SRC-GATE-1", "PARTY-1", "S-G", "CASH", "10", "20260528140500", "RETURN", "L1"],
                ["ACT-B", "SRC-GATE-1", "PARTY-1", "S-G", "CASH", "10", "20260528140600", "RETURN", "L1"],
                ["ACT-C", "SRC-GATE-2", "PARTY-2", "S-G", "CASH", "20", "20260528140700", "RETURN", "L2"],
                ["ACT-D", "SRC-GATE-3", "PARTY-X", "S-G", "UPI", "30", "20260528140700", "SHORT", "L3"],
                ["ACT-E", "SRC-GATE-3", "PARTY-3", "S-G", "UPI", "31", "20260528140700", "SHORT", "L3"],
                ["ACT-F", "SRC-GATE-3", "PARTY-3", "S-G", "UPI", "30", "20260528135959", "SHORT", "L3"],
                ["ACT-G", "SRC-GATE-3", "PARTY-3", "S-G", "UPI", "30", "20260528140700", "INFO", "L3"],
                ["ACT-H", "SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140700", "ADJUST", "L4"],
                ["ACT-I", "SRC-GATE-5", "PARTY-5", "S-G", "CARD", "50", "20260528140800", "ADJUST", "L5"],
            ],
            [["S-G", "20260528135900", "20260528143000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["kind"] == ""
        assert rows[8]["kind"] == "CARD"
        assert summary == {"matched_count": 2, "matched_amount": 60, "unmatched_count": 7, "unmatched_amount": 191}


    def test_location_mismatch_blocks_otherwise_valid_match(self):
        """The location field is part of the full identity key and must match exactly."""
        build_program()
        write_inputs(
            [["SRC-LOC", "PARTY-LOC", "S-LOC", "CASH", "25", "20260528140000", "DELIVERED", "LOCKER-A"]],
            [["ACT-LOC", "SRC-LOC", "PARTY-LOC", "S-LOC", "CASH", "25", "20260528140500", "RETURN", "LOCKER-B"]],
            [["S-LOC", "20260528135900", "20260528143000", "OPEN"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 25}


    def test_closed_missing_malformed_windows_and_late_action_ts(self):
        """Closed, malformed, unlisted windows and action_ts past close_ts must stay unmatched."""
        build_program()
        write_inputs(
            [
                ["SRC-OPEN", "P1", "S-O", "CASH", "10", "20260528150000", "DELIVERED", "L1"],
                ["SRC-CLOSED", "P2", "S-C", "CASH", "20", "20260528150000", "DELIVERED", "L2"],
                ["SRC-BAD", "P3", "S-M", "UPI", "30", "bad-time", "DELIVERED", "L3"],
                ["SRC-NOWIN", "P4", "S-X", "CARD", "40", "20260528150000", "DELIVERED", "L4"],
                ["SRC-LATE", "P5", "S-O", "CASH", "15", "20260528152000", "DELIVERED", "L5"],
            ],
            [
                ["ACT-OPEN", "SRC-OPEN", "P1", "S-O", "CASH", "10", "20260528150500", "RETURN", "L1"],
                ["ACT-CLOSED", "SRC-CLOSED", "P2", "S-C", "CASH", "20", "20260528150500", "RETURN", "L2"],
                ["ACT-BAD", "SRC-BAD", "P3", "S-M", "UPI", "30", "20260528150500", "SHORT", "L3"],
                ["ACT-NOWIN", "SRC-NOWIN", "P4", "S-X", "CARD", "40", "20260528150500", "ADJUST", "L4"],
                ["ACT-LATE", "SRC-LATE", "P5", "S-O", "CASH", "15", "20260528153100", "RETURN", "L5"],
            ],
            [
                ["S-O", "20260528145900", "20260528153000", "OPEN"],
                ["S-C", "20260528145900", "20260528153000", "CLOS"],
                ["S-M", "bad-time", "20260528153000", "OPEN"],
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert rows[0]["kind"] == "CASH"
        assert all(row["kind"] == "" for row in rows[1:])
        assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 4, "unmatched_amount": 105}


    def test_latest_source_ts_wins_among_duplicate_delivery_candidates(self):
        """When multiple deliveries qualify, the latest source_ts row must be consumed before older rows."""
        build_program()
        write_inputs(
            [
                ["SRC-TIE", "PARTY-T", "S-T", "CASH", "100", "20260528140000", "DELIVERED", "L1"],
                ["SRC-TIE", "PARTY-T", "S-T", "CASH", "100", "20260528140200", "DELIVERED", "L1"],
            ],
            [
                ["ACT-1", "SRC-TIE", "PARTY-T", "S-T", "CASH", "100", "20260528140500", "RETURN", "L1"],
                ["ACT-2", "SRC-TIE", "PARTY-T", "S-T", "CASH", "100", "20260528140600", "RETURN", "L1"],
            ],
            [["S-T", "20260528135900", "20260528143000", "OPEN"]],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert summary == {"matched_count": 2, "matched_amount": 200, "unmatched_count": 0, "unmatched_amount": 0}
