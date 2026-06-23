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


class TestMilestone3:
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
    def test_aliases_full_keys_and_canonical_output(self):
        """Aliases should match full source keys and emit canonical temp_band values."""
        build_program()
        write_inputs(
            [
                ["SRC-100000001", "PARTY-1", "S-A", "FROZEN", "12", "20260528120500", "QUARANTINED", "LOC-1"],
                ["SRC-100000002", "PARTY-2", "S-A", "CHILL", "34", "20260528120600", "QUARANTINED", "LOC-2"],
                ["SRC-100000003", "PARTY-3", "S-B", "AMBIENT", "56", "20260528130500", "QUARANTINED", "LOC-3"],
            ],
            [
                ["ACT-1", "SRC-100000001", "PARTY-1", "S-A", "IN", "12", "20260528121000", "SPOIL", "LOC-1"],
                ["ACT-2", "SRC-100000002", "PARTY-2", "S-A", "CU", "34", "20260528121100", "QUAR", "LOC-2"],
                ["ACT-3", "SRC-100000003", "PARTY-3", "S-B", "SE", "56", "20260528131000", "OVERRIDE", "LOC-3"],
            ],
            [["S-A", "20260528120000", "20260528123000", "OPEN"], ["S-B", "20260528130000", "20260528133000", "OPEN"]],
        )
        rows, summary = run_program()
        assert REPORT.read_text().splitlines()[0] == "release_id,hold_id,pallet_id,zone_id,temp_band,amount,reason,status"
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["temp_band"] for row in rows] == ["FROZEN", "CHILL", "AMBIENT"]
        assert summary == {"matched_count": 3, "matched_amount": 102, "unmatched_count": 0, "unmatched_amount": 0}
    
    
    def test_unknown_temp_band_stays_unmatched_inside_open_window(self):
        """The M3 window rules must not weaken the canonical temp_band gate."""
        build_program()
        write_inputs(
            [["SRC-BAD-WINDOW", "BOX-BAD", "G-3", "BAD", "90", "20260528150000", "QUARANTINED", "LANE-B"]],
            [["REL-BAD-WINDOW", "SRC-BAD-WINDOW", "BOX-BAD", "G-3", "BAD", "90", "20260528150100", "OVERRIDE", "LANE-B"]],
            [["G-3", "20260528145900", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()
    
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["temp_band"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 90}
    
    
    def test_release_after_window_close_is_unmatched(self):
        """A release after the matching window close_ts must stay unmatched."""
        build_program()
        write_inputs(
            [["SRC-AFTER-CLOSE", "BOX-CLOSE", "G-3", "AMBIENT", "95", "20260528150000", "QUARANTINED", "LANE-C"]],
            [["REL-AFTER-CLOSE", "SRC-AFTER-CLOSE", "BOX-CLOSE", "G-3", "SE", "95", "20260528153100", "OVERRIDE", "LANE-C"]],
            [["G-3", "20260528145900", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()
    
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["temp_band"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 95}

    def test_bay_mismatch_is_unmatched_inside_open_window(self):
        """A release whose only differing field is bay must stay unmatched."""
        build_program()
        write_inputs(
            [["SRC-BAY-ONLY", "PAL-B", "Z-B", "FROZEN", "66", "20260528100000", "QUARANTINED", "BAY-A"]],
            [["REL-BAY-ONLY", "SRC-BAY-ONLY", "PAL-B", "Z-B", "IN", "66", "20260528100100", "SPOIL", "BAY-B"]],
            [["Z-B", "20260528090000", "20260528110000", "OPEN"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["temp_band"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 66}

    def test_window_state_malformed_times_latest_candidate_and_order(self):
        """Window eligibility, malformed times, latest candidate selection, order, and blank unmatched temp_band should hold."""
        build_program()
        write_inputs(
            [
                ["SRC-WIN-1", "PARTY-1", "S-O", "FROZEN", "1", "20260528150000", "QUARANTINED", "L1"],
                ["SRC-WIN-2", "PARTY-2", "S-C", "FROZEN", "2", "20260528150000", "QUARANTINED", "L2"],
                ["SRC-WIN-3", "PARTY-3", "S-M", "CHILL", "3", "bad-time", "QUARANTINED", "L3"],
                ["SRC-DUPE", "PARTY-4", "S-O", "AMBIENT", "4", "20260528150100", "QUARANTINED", "L4"],
                ["SRC-DUPE", "PARTY-4", "S-O", "AMBIENT", "4", "20260528150200", "QUARANTINED", "L4"],
            ],
            [
                ["ACT-1", "SRC-WIN-1", "PARTY-1", "S-O", "FROZEN", "1", "20260528150500", "SPOIL", "L1"],
                ["ACT-2", "SRC-WIN-2", "PARTY-2", "S-C", "FROZEN", "2", "20260528150500", "SPOIL", "L2"],
                ["ACT-3", "SRC-WIN-3", "PARTY-3", "S-M", "CHILL", "3", "20260528150500", "QUAR", "L3"],
                ["ACT-4", "SRC-DUPE", "PARTY-4", "S-O", "AMBIENT", "4", "20260528150600", "OVERRIDE", "L4"],
            ],
            [["S-O", "20260528145900", "20260528153000", "OPEN"], ["S-C", "20260528145900", "20260528153000", "CLOS"], ["S-M", "bad-time", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["release_id"] for row in rows] == ["ACT-1", "ACT-2", "ACT-3", "ACT-4"]
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert [row["temp_band"] for row in rows] == ["FROZEN", "", "", "AMBIENT"]
        assert summary == {"matched_count": 2, "matched_amount": 5, "unmatched_count": 2, "unmatched_amount": 5}
    
    
    def test_latest_hold_ts_wins_not_first_eligible_row(self):
        """When several unused holds qualify, the latest hold_ts must be consumed."""
        build_program()
        write_inputs(
            [
                ["SRC-LATE", "PAL-L", "Z-L", "FROZEN", "88", "20260528100000", "QUARANTINED", "B1"],
                ["SRC-LATE", "PAL-L", "Z-L", "FROZEN", "88", "20260528103000", "QUARANTINED", "B1"],
            ],
            [["REL-LATE", "SRC-LATE", "PAL-L", "Z-L", "FROZEN", "88", "20260528104000", "SPOIL", "B1"]],
            [["Z-L", "20260528090000", "20260528110000", "OPEN"]],
        )
        rows, summary = run_program()
    
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["temp_band"] == "FROZEN"
        assert summary == {"matched_count": 1, "matched_amount": 88, "unmatched_count": 0, "unmatched_amount": 0}

    def test_same_timestamp_duplicate_sources_are_consumed_by_row_position(self):
        """Duplicate same-timestamp sources should be consumed one row at a time before later releases."""
        build_program()
        write_inputs(
            [
                ["SRC-TIE", "PAL-T", "Z-T", "FROZEN", "33", "20260528100000", "QUARANTINED", "B1"],
                ["SRC-TIE", "PAL-T", "Z-T", "FROZEN", "33", "20260528100000", "QUARANTINED", "B1"],
            ],
            [
                ["REL-TIE-1", "SRC-TIE", "PAL-T", "Z-T", "FROZEN", "33", "20260528101000", "SPOIL", "B1"],
                ["REL-TIE-2", "SRC-TIE", "PAL-T", "Z-T", "FROZEN", "33", "20260528101100", "SPOIL", "B1"],
                ["REL-TIE-3", "SRC-TIE", "PAL-T", "Z-T", "FROZEN", "33", "20260528101200", "SPOIL", "B1"],
            ],
            [["Z-T", "20260528090000", "20260528110000", "OPEN"]],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["temp_band"] for row in rows] == ["FROZEN", "FROZEN", ""]
        assert summary == {"matched_count": 2, "matched_amount": 66, "unmatched_count": 1, "unmatched_amount": 33}
    
    
    def test_hold_before_window_open_is_unmatched(self):
        """A hold timestamp before the zone window open_ts must not match."""
        build_program()
        write_inputs(
            [["SRC-EARLY", "PAL-E", "Z-E", "CHILL", "77", "20260528083000", "QUARANTINED", "B1"]],
            [["REL-EARLY", "SRC-EARLY", "PAL-E", "Z-E", "CU", "77", "20260528090000", "QUAR", "B1"]],
            [["Z-E", "20260528090000", "20260528110000", "OPEN"]],
        )
        rows, summary = run_program()
    
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["unmatched_amount"] == 77
