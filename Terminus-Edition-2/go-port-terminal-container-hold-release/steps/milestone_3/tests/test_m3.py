"""Verifier tests for the port terminal container hold-release reconciliation CLI."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
GO = Path("/usr/local/go/bin/go")
BIN = APP / "build" / "reconcile"
SOURCE = APP / "data" / "holds.csv"
ACTION = APP / "data" / "releases.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "release_report.csv"
SUMMARY = APP / "out" / "release_summary.txt"


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
    write_csv(SOURCE, ["hold_id", "container_id", "gate_id", "hold_type", "amount", "hold_ts", "status", "lane"], source)
    write_csv(ACTION, ["release_id", "hold_id", "container_id", "gate_id", "hold_type", "amount", "release_ts", "reason", "lane"], action)
    write_csv(WINDOWS, ["gate_id", "open_ts", "close_ts", "state"], windows)
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
                ["SRC-GATE-1", "PARTY-1", "S-G", "INSPECTION", "10", "20260528140000", "ACTIVE", "L1"],
                ["SRC-GATE-2", "PARTY-2", "S-G", "INSPECTION", "20", "20260528140100", "BAD", "L2"],
                ["SRC-GATE-3", "PARTY-3", "S-G", "CUSTOMS", "30", "20260528140200", "ACTIVE", "L3"],
                ["SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140300", "ACTIVE", "L4"],
            ],
            [
                ["ACT-A", "SRC-GATE-1", "PARTY-1", "S-G", "INSPECTION", "10", "20260528140500", "CLINRED", "L1"],
                ["ACT-B", "SRC-GATE-1", "PARTY-1", "S-G", "INSPECTION", "10", "20260528140600", "CLINRED", "L1"],
                ["ACT-C", "SRC-GATE-2", "PARTY-2", "S-G", "INSPECTION", "20", "20260528140700", "CLINRED", "L2"],
                ["ACT-D", "SRC-GATE-3", "PARTY-X", "S-G", "CUSTOMS", "30", "20260528140700", "WAIVED", "L3"],
                ["ACT-E", "SRC-GATE-3", "PARTY-3", "S-G", "CUSTOMS", "31", "20260528140700", "WAIVED", "L3"],
                ["ACT-F", "SRC-GATE-3", "PARTY-3", "S-G", "CUSTOMS", "30", "20260528135959", "WAIVED", "L3"],
                ["ACT-G", "SRC-GATE-3", "PARTY-3", "S-G", "CUSTOMS", "30", "20260528140700", "INFO", "L3"],
                ["ACT-H", "SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140700", "OVERRIDE", "L4"],
            ],
            [["S-G", "20260528135900", "20260528143000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 7, "unmatched_amount": 191}

    def test_aliases_full_keys_and_canonical_output(self):
        """Aliases should match full source keys and emit canonical hold_type values."""
        build_program()
        write_inputs(
            [
                ["SRC-100000001", "PARTY-1", "S-A", "INSPECTION", "12", "20260528120500", "ACTIVE", "LOC-1"],
                ["SRC-100000002", "PARTY-2", "S-A", "CUSTOMS", "34", "20260528120600", "ACTIVE", "LOC-2"],
                ["SRC-100000003", "PARTY-3", "S-B", "SECURITY", "56", "20260528130500", "ACTIVE", "LOC-3"],
            ],
            [
                ["ACT-1", "SRC-100000001", "PARTY-1", "S-A", "IN", "12", "20260528121000", "CLINRED", "LOC-1"],
                ["ACT-2", "SRC-100000002", "PARTY-2", "S-A", "CU", "34", "20260528121100", "WAIVED", "LOC-2"],
                ["ACT-3", "SRC-100000003", "PARTY-3", "S-B", "SE", "56", "20260528131000", "OVERRIDE", "LOC-3"],
            ],
            [["S-A", "20260528120000", "20260528123000", "OPEN"], ["S-B", "20260528130000", "20260528133000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["hold_type"] for row in rows] == ["INSPECTION", "CUSTOMS", "SECURITY"]

    def test_window_state_malformed_times_latest_candidate_and_order(self):
        """Window eligibility, malformed times, latest candidate selection, order, and blank unmatched hold_type should hold."""
        build_program()
        write_inputs(
            [
                ["SRC-WIN-1", "PARTY-1", "S-O", "INSPECTION", "1", "20260528150000", "ACTIVE", "L1"],
                ["SRC-WIN-2", "PARTY-2", "S-C", "INSPECTION", "2", "20260528150000", "ACTIVE", "L2"],
                ["SRC-WIN-3", "PARTY-3", "S-M", "CUSTOMS", "3", "bad-time", "ACTIVE", "L3"],
                ["SRC-DUPE", "PARTY-4", "S-O", "SECURITY", "4", "20260528150100", "ACTIVE", "L4"],
                ["SRC-DUPE", "PARTY-4", "S-O", "SECURITY", "4", "20260528150200", "ACTIVE", "L4"],
            ],
            [
                ["ACT-1", "SRC-WIN-1", "PARTY-1", "S-O", "INSPECTION", "1", "20260528150500", "CLINRED", "L1"],
                ["ACT-2", "SRC-WIN-2", "PARTY-2", "S-C", "INSPECTION", "2", "20260528150500", "CLINRED", "L2"],
                ["ACT-3", "SRC-WIN-3", "PARTY-3", "S-M", "CUSTOMS", "3", "20260528150500", "WAIVED", "L3"],
                ["ACT-4", "SRC-DUPE", "PARTY-4", "S-O", "SECURITY", "4", "20260528150600", "OVERRIDE", "L4"],
            ],
            [["S-O", "20260528145900", "20260528153000", "OPEN"], ["S-C", "20260528145900", "20260528153000", "CLOS"], ["S-M", "bad-time", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert [row["hold_type"] for row in rows] == ["INSPECTION", "", "", "SECURITY"]
        assert summary == {"matched_count": 2, "matched_amount": 5, "unmatched_count": 2, "unmatched_amount": 5}

    def test_release_after_window_close_is_unmatched(self):
        """A release after the matching window close_ts must stay unmatched."""
        build_program()
        write_inputs(
            [["SRC-AFTER-CLOSE", "BOX-CLOSE", "G-3", "SECURITY", "95", "20260528150000", "ACTIVE", "LANE-C"]],
            [["REL-AFTER-CLOSE", "SRC-AFTER-CLOSE", "BOX-CLOSE", "G-3", "SE", "95", "20260528153100", "OVERRIDE", "LANE-C"]],
            [["G-3", "20260528145900", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_equal_hold_ts_tie_uses_earliest_source_row(self):
        """When hold_ts ties, the earliest source input row must win."""
        build_program()
        write_inputs(
            [
                ["SRC-TIE-1", "PARTY-T", "S-TIE", "SECURITY", "33", "20260528200000", "ACTIVE", "L1"],
                ["SRC-TIE-1", "PARTY-T", "S-TIE", "SECURITY", "33", "20260528200000", "ACTIVE", "L1"],
            ],
            [
                ["ACT-TIE-1", "SRC-TIE-1", "PARTY-T", "S-TIE", "SE", "33", "20260528200100", "OVERRIDE", "L1"],
                ["ACT-TIE-2", "SRC-TIE-1", "PARTY-T", "S-TIE", "SE", "33", "20260528200200", "OVERRIDE", "L1"],
            ],
            [["S-TIE", "20260528195900", "20260528203000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount"] == 66

    def test_unknown_hold_type_stays_unmatched_inside_open_window(self):
        """The M3 window rules must not weaken the canonical hold_type gate."""
        build_program()
        write_inputs(
            [["SRC-BAD-WINDOW", "BOX-BAD", "G-3", "BAD", "90", "20260528150000", "ACTIVE", "LANE-B"]],
            [["REL-BAD-WINDOW", "SRC-BAD-WINDOW", "BOX-BAD", "G-3", "BAD", "90", "20260528150100", "OVERRIDE", "LANE-B"]],
            [["G-3", "20260528145900", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["hold_type"] == ""

    def test_hold_id_gate_id_and_lane_mismatch_stay_unmatched_with_windows(self):
        """Window-aware matching still requires exact hold_id, gate_id, and lane."""
        build_program()
        write_inputs(
            [["SRC-ID-1", "BOX-1", "G-ID", "INSPECTION", "9", "20260528140000", "ACTIVE", "LOC-1"]],
            [
                ["REL-PFX", "SRC-ID", "BOX-1", "G-ID", "INSPECTION", "9", "20260528140500", "CLINRED", "LOC-1"],
                ["REL-GATE", "SRC-ID-1", "BOX-1", "G-OTHER", "INSPECTION", "9", "20260528140500", "CLINRED", "LOC-1"],
                ["REL-LANE", "SRC-ID-1", "BOX-1", "G-ID", "INSPECTION", "9", "20260528140500", "CLINRED", "LOC-2"],
            ],
            [["G-ID", "20260528135900", "20260528143000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 0
