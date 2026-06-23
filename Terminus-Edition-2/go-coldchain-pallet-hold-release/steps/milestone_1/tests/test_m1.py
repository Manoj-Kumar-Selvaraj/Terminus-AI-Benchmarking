"""Verifier tests for realtime cold chain pallet hold release reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
GO = Path("/usr/local/go/bin/go")
BIN = APP / "build" / "reconcile"
SOURCE = APP / "data" / "holds.csv"
ACTION = APP / "data" / "releases.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "pallet_release_report.csv"
SUMMARY = APP / "out" / "pallet_release_summary.txt"


def build_program():
    """Prepare the reconciler for one verifier scenario."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile/main.go"], check=True, cwd=APP, timeout=60)


def write_csv(path, header, rows):
    """Write one CSV fixture."""
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(source, action, windows):
    """Overwrite all input files at runtime."""
    write_csv(SOURCE, ["hold_id", "pallet_id", "zone_id", "temp_band", "amount", "hold_ts", "status", "bay"], source)
    write_csv(ACTION, ["release_id", "hold_id", "pallet_id", "zone_id", "temp_band", "amount", "release_ts", "reason", "bay"], action)
    write_csv(WINDOWS, ["zone_id", "open_ts", "close_ts", "state"], windows)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the reconciler and parse outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        summary[key] = int(value)
    return rows, summary


class TestMilestone1:
    def test_all_gates_consumption_and_positive_unmatched_totals(self):
        """Every identity, status, timestamp, reason, and consumption gate should reject bad candidates."""
        build_program()
        write_inputs(
            [
                ["SRC-GATE-1", "PARTY-1", "S-G", "FROZEN", "10", "20260528140000", "QUARANTINED", "L1"],
                ["SRC-GATE-2", "PARTY-2", "S-G", "FROZEN", "20", "20260528140100", "BAD", "L2"],
                ["SRC-GATE-3", "PARTY-3", "S-G", "CHILL", "30", "20260528140200", "QUARANTINED", "L3"],
                ["SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140300", "QUARANTINED", "L4"],
            ],
            [
                ["ACT-A", "SRC-GATE-1", "PARTY-1", "S-G", "FROZEN", "10", "20260528140500", "SPOIL", "L1"],
                ["ACT-B", "SRC-GATE-1", "PARTY-1", "S-G", "FROZEN", "10", "20260528140600", "SPOIL", "L1"],
                ["ACT-C", "SRC-GATE-2", "PARTY-2", "S-G", "FROZEN", "20", "20260528140700", "SPOIL", "L2"],
                ["ACT-D", "SRC-GATE-3", "PARTY-X", "S-G", "CHILL", "30", "20260528140700", "QUAR", "L3"],
                ["ACT-E", "SRC-GATE-3", "PARTY-3", "S-G", "CHILL", "31", "20260528140700", "QUAR", "L3"],
                ["ACT-F", "SRC-GATE-3", "PARTY-3", "S-G", "CHILL", "30", "20260528135959", "QUAR", "L3"],
                ["ACT-G", "SRC-GATE-3", "PARTY-3", "S-G", "CHILL", "30", "20260528140700", "INFO", "L3"],
                ["ACT-H", "SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140700", "OVERRIDE", "L4"],
            ],
            [["S-G", "20260528135900", "20260528143000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert rows[1]["temp_band"] == ""
        assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 7, "unmatched_amount": 191}
    
    
    def test_active_status_is_required(self):
        """A source hold with any status other than QUARANTINED must not match."""
        build_program()
        write_inputs(
            [["SRC-STATUS", "BOX-1", "G-1", "FROZEN", "25", "20260528100000", "CLOSED", "LANE-1"]],
            [["REL-STATUS", "SRC-STATUS", "BOX-1", "G-1", "FROZEN", "25", "20260528100100", "SPOIL", "LANE-1"]],
            [["G-1", "20260528090000", "20260528110000", "OPEN"]],
        )
        rows, summary = run_program()
    
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["temp_band"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 25}
    
    
    def test_reason_must_be_allowed(self):
        """A release reason outside the allowed milestone 1 set must not match."""
        build_program()
        write_inputs(
            [["SRC-REASON", "BOX-2", "G-1", "CHILL", "35", "20260528100000", "QUARANTINED", "LANE-2"]],
            [["REL-REASON", "SRC-REASON", "BOX-2", "G-1", "CHILL", "35", "20260528100100", "INFO", "LANE-2"]],
            [["G-1", "20260528090000", "20260528110000", "OPEN"]],
        )
        rows, summary = run_program()
    
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["temp_band"] == ""
        assert summary["unmatched_amount"] == 35

    def test_non_numeric_timestamps_are_unmatched(self):
        """Non-numeric hold_ts or release_ts values must fail the timestamp gate."""
        build_program()
        write_inputs(
            [
                ["SRC-BAD-HOLD-TS", "BOX-H", "G-1", "FROZEN", "22", "NOT_A_NUMBER", "QUARANTINED", "LANE-H"],
                ["SRC-BAD-REL-TS", "BOX-R", "G-1", "CHILL", "23", "20260528100000", "QUARANTINED", "LANE-R"],
            ],
            [
                ["REL-BAD-HOLD-TS", "SRC-BAD-HOLD-TS", "BOX-H", "G-1", "FROZEN", "22", "20260528100100", "SPOIL", "LANE-H"],
                ["REL-BAD-REL-TS", "SRC-BAD-REL-TS", "BOX-R", "G-1", "CHILL", "23", "NOT_A_NUMBER", "QUAR", "LANE-R"],
            ],
            [["G-1", "20260528090000", "20260528110000", "OPEN"]],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert [row["temp_band"] for row in rows] == ["", ""]
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 2, "unmatched_amount": 45}

    def test_closed_window_is_unmatched(self):
        """A source row inside a CLOSED window must not match."""
        build_program()
        write_inputs(
            [["SRC-CLOSED-WIN", "BOX-W", "G-1", "FROZEN", "24", "20260528100000", "QUARANTINED", "LANE-W"]],
            [["REL-CLOSED-WIN", "SRC-CLOSED-WIN", "BOX-W", "G-1", "FROZEN", "24", "20260528100100", "SPOIL", "LANE-W"]],
            [["G-1", "20260528090000", "20260528110000", "CLOSED"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["temp_band"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 24}

    def test_release_after_window_close_is_unmatched(self):
        """A release after the matching window close_ts must stay unmatched."""
        build_program()
        write_inputs(
            [["SRC-AFTER-CLOSE", "BOX-CLOSE", "G-3", "FROZEN", "95", "20260528150000", "QUARANTINED", "LANE-C"]],
            [["REL-AFTER-CLOSE", "SRC-AFTER-CLOSE", "BOX-CLOSE", "G-3", "FROZEN", "95", "20260528153100", "SPOIL", "LANE-C"]],
            [["G-3", "20260528145900", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["temp_band"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 95}

    
    def test_consumption_prevents_second_release_match(self):
        """A matched hold row must be consumed so a later duplicate release stays unmatched."""
        build_program()
        write_inputs(
            [["SRC-CONSUME", "BOX-3", "G-1", "FROZEN", "45", "20260528100000", "QUARANTINED", "LANE-3"]],
            [
                ["REL-CONSUME-1", "SRC-CONSUME", "BOX-3", "G-1", "FROZEN", "45", "20260528100100", "SPOIL", "LANE-3"],
                ["REL-CONSUME-2", "SRC-CONSUME", "BOX-3", "G-1", "FROZEN", "45", "20260528100200", "SPOIL", "LANE-3"],
            ],
            [["G-1", "20260528090000", "20260528110000", "OPEN"]],
        )
        rows, summary = run_program()
    
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["temp_band"] for row in rows] == ["FROZEN", ""]
        assert summary == {"matched_count": 1, "matched_amount": 45, "unmatched_count": 1, "unmatched_amount": 45}
    
    
    def test_required_output_paths_and_positive_matched_amount(self):
        """Milestone 1 must write pallet_release_* outputs with positive matched totals."""
        build_program()
        write_inputs(
            [["SRC-PATH", "PAL-P", "Z-P", "FROZEN", "55", "20260528100000", "QUARANTINED", "B1"]],
            [["REL-PATH", "SRC-PATH", "PAL-P", "Z-P", "FROZEN", "55", "20260528100100", "SPOIL", "B1"]],
            [["Z-P", "20260528090000", "20260528110000", "OPEN"]],
        )
        rows, summary = run_program()
    
        assert REPORT.is_file()
        assert SUMMARY.is_file()
        assert not (APP / "out" / "coldchain_release_report.csv").exists()
        assert not (APP / "out" / "release_summary.txt").exists()
        assert rows[0]["status"] == "MATCHED"
        assert summary["matched_amount"] == 55
    
    
    def test_prefix_hold_id_overlap_must_not_match(self):
        """Hold identifiers must match exactly; shared prefixes are not sufficient."""
        build_program()
        write_inputs(
            [["SRC-100", "PAL-1", "Z-1", "FROZEN", "15", "20260528100000", "QUARANTINED", "B1"]],
            [["REL-PFX", "SRC-10", "PAL-1", "Z-1", "FROZEN", "15", "20260528100100", "SPOIL", "B1"]],
            [["Z-1", "20260528090000", "20260528110000", "OPEN"]],
        )
        rows, summary = run_program()
    
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["unmatched_amount"] == 15
    
    
    def test_identity_fields_and_source_temp_band_on_match(self):
        """Pallet, zone, and bay must match, and matched rows report the source temp_band."""
        build_program()
        write_inputs(
            [["SRC-ID", "PAL-A", "Z-1", "CHILL", "40", "20260528100000", "QUARANTINED", "B1"]],
            [
                ["REL-BAY", "SRC-ID", "PAL-A", "Z-1", "CHILL", "40", "20260528100100", "QUAR", "B2"],
                ["REL-PAL", "SRC-ID", "PAL-X", "Z-1", "CHILL", "40", "20260528100100", "QUAR", "B1"],
                ["REL-OK", "SRC-ID", "PAL-A", "Z-1", "FROZEN", "40", "20260528100100", "QUAR", "B1"],
            ],
            [["Z-1", "20260528090000", "20260528110000", "OPEN"]],
        )
        rows, summary = run_program()
    
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 0
