"""Verifier tests for realtime hotel night audit chargeback reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "folios.csv"
ACTION = APP / "data" / "chargebacks.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "chargeback_report.csv"
SUMMARY = APP / "out" / "chargeback_summary.txt"


def build_program():
    """Prepare the reconciler for one verifier scenario."""
    pass


def write_csv(path, header, rows):
    """Write one CSV fixture."""
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(source, action, windows):
    """Overwrite all input files at runtime."""
    write_csv(SOURCE, ["folio_id", "guest_id", "property_id", "kind", "amount", "source_ts", "status", "location"], source)
    write_csv(ACTION, ["action_id", "folio_id", "guest_id", "property_id", "kind", "amount", "action_ts", "reason", "location"], action)
    write_csv(WINDOWS, ["property_id", "open_ts", "close_ts", "state"], windows)
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


class TestMilestone3:
    def test_open_window_allows_valid_match(self):
        """An OPEN window with valid timestamps should allow a match."""
        build_program()
        write_inputs(
            [["SRC-WIN-1", "PARTY-1", "S-O", "CARD", "1", "20260528150000", "POSTED", "L1"]],
            [["ACT-1", "SRC-WIN-1", "PARTY-1", "S-O", "CARD", "1", "20260528150500", "DISPUTE", "L1"]],
            [["S-O", "20260528145900", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["kind"] == "CARD"
        assert summary["matched_amount"] == 1

    def test_closed_window_rejects_otherwise_valid_match(self):
        """Closed windows must reject matches even when other gates align."""
        build_program()
        write_inputs(
            [["SRC-WIN-2", "PARTY-2", "S-C", "CARD", "2", "20260528150000", "POSTED", "L2"]],
            [["ACT-2", "SRC-WIN-2", "PARTY-2", "S-C", "CARD", "2", "20260528150500", "DISPUTE", "L2"]],
            [["S-C", "20260528145900", "20260528153000", "CLOS"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary["matched_count"] == 0

    def test_malformed_window_timestamps_reject_match(self):
        """Malformed window timestamps must reject otherwise valid candidates."""
        build_program()
        write_inputs(
            [["SRC-WIN-3", "PARTY-3", "S-M", "CASH", "3", "20260528150000", "POSTED", "L3"]],
            [["ACT-3", "SRC-WIN-3", "PARTY-3", "S-M", "CASH", "3", "20260528150500", "DUPLICATE", "L3"]],
            [["S-M", "bad-time", "20260528153000", "OPEN"]],
        )
        rows, _ = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""

    def test_unlisted_property_window_stays_unmatched(self):
        """A property_id with no window row must stay unmatched."""
        build_program()
        write_inputs(
            [["SRC-MISS", "PARTY-7", "S-N", "CASH", "8", "20260528150500", "POSTED", "L7"]],
            [["ACT-7", "SRC-MISS", "PARTY-7", "S-N", "CSH", "8", "20260528150600", "DUPLICATE", "L7"]],
            [["S-OTHER", "20260528145900", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary["unmatched_amount"] == 8

    def test_latest_source_timestamp_wins_among_candidates(self):
        """Multiple unused candidates must resolve by latest source timestamp."""
        build_program()
        write_inputs(
            [
                ["SRC-DUPE", "PARTY-4", "S-O", "POINTS", "4", "20260528150100", "POSTED", "L4"],
                ["SRC-DUPE", "PARTY-4", "S-O", "POINTS", "4", "20260528150200", "POSTED", "L4"],
            ],
            [["ACT-4", "SRC-DUPE", "PARTY-4", "S-O", "PTS", "4", "20260528150600", "NOAUTH", "L4"]],
            [["S-O", "20260528145900", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["kind"] == "POINTS"
        assert summary["matched_amount"] == 4

    def test_location_mismatch_blocks_cumulative_match(self):
        """Location must still gate matching after alias normalization."""
        build_program()
        write_inputs(
            [["SRC-LOC", "PARTY-5", "S-O", "CARD", "6", "20260528150300", "POSTED", "L-ORIG"]],
            [["ACT-5", "SRC-LOC", "PARTY-5", "S-O", "CARD", "6", "20260528150600", "DISPUTE", "L-OTHER"]],
            [["S-O", "20260528145900", "20260528153000", "OPEN"]],
        )
        rows, _ = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""

    def test_action_after_window_close_rejects(self):
        """Corrections after close_ts must stay unmatched."""
        build_program()
        write_inputs(
            [["SRC-LATE", "PARTY-6", "S-O", "CARD", "7", "20260528150400", "POSTED", "L6"]],
            [["ACT-6", "SRC-LATE", "PARTY-6", "S-O", "CARD", "7", "20260528153100", "DISPUTE", "L6"]],
            [["S-O", "20260528145900", "20260528153000", "OPEN"]],
        )
        rows, _ = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""

    def test_preserves_correction_input_order(self):
        """Report rows must follow correction input order."""
        build_program()
        write_inputs(
            [
                ["SRC-A", "PARTY-1", "S-O", "CARD", "1", "20260528150000", "POSTED", "L1"],
                ["SRC-B", "PARTY-2", "S-C", "CARD", "2", "20260528150000", "POSTED", "L2"],
            ],
            [
                ["ACT-1", "SRC-A", "PARTY-1", "S-O", "CARD", "1", "20260528150500", "DISPUTE", "L1"],
                ["ACT-2", "SRC-B", "PARTY-2", "S-C", "CARD", "2", "20260528150500", "DISPUTE", "L2"],
            ],
            [["S-O", "20260528145900", "20260528153000", "OPEN"], ["S-C", "20260528145900", "20260528153000", "CLOS"]],
        )
        rows, _ = run_program()
        assert [row["action_id"] for row in rows] == ["ACT-1", "ACT-2"]
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
