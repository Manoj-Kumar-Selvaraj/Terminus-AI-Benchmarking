"""Verifier tests for realtime airport gate baggage hold release reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
GO = Path("/usr/local/go/bin/go")
BIN = APP / "build" / "reconcile"
SOURCE = APP / "data" / "holds.csv"
ACTION = APP / "data" / "releases.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "baggage_release_report.csv"
SUMMARY = APP / "out" / "baggage_release_summary.txt"


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


def write_inputs(source, action, windows=None):
    """Overwrite input files at runtime."""
    write_csv(SOURCE, ["hold_id", "bag_tag_id", "gate_id", "check_type", "amount", "hold_ts", "status", "carousel"], source)
    write_csv(ACTION, ["release_id", "hold_id", "bag_tag_id", "gate_id", "check_type", "amount", "release_ts", "reason", "carousel"], action)
    if windows is not None:
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


class TestMilestone1:
    def test_all_gates_consumption_and_positive_unmatched_totals(self):
        """Every identity, status, timestamp, reason, and consumption gate should reject bad candidates."""
        build_program()
        write_inputs(
            [
                ["SRC-GATE-1", "PARTY-1", "S-G", "MEDICAL", "10", "20260528140000", "ACTIVE", "L1"],
                ["SRC-GATE-2", "PARTY-2", "S-G", "MEDICAL", "20", "20260528140100", "BAD", "L2"],
                ["SRC-GATE-3", "PARTY-3", "S-G", "CUSTOMS", "30", "20260528140200", "ACTIVE", "L3"],
                ["SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140300", "ACTIVE", "L4"],
            ],
            [
                ["ACT-A", "SRC-GATE-1", "PARTY-1", "S-G", "MEDICAL", "10", "20260528140500", "CLEAR", "L1"],
                ["ACT-B", "SRC-GATE-1", "PARTY-1", "S-G", "MEDICAL", "10", "20260528140600", "CLEAR", "L1"],
                ["ACT-C", "SRC-GATE-2", "PARTY-2", "S-G", "MEDICAL", "20", "20260528140700", "CLEAR", "L2"],
                ["ACT-D", "SRC-GATE-3", "PARTY-X", "S-G", "CUSTOMS", "30", "20260528140700", "MEDICAL", "L3"],
                ["ACT-E", "SRC-GATE-3", "PARTY-3", "S-G", "CUSTOMS", "31", "20260528140700", "MEDICAL", "L3"],
                ["ACT-F", "SRC-GATE-3", "PARTY-3", "S-G", "CUSTOMS", "30", "20260528135959", "MEDICAL", "L3"],
                ["ACT-G", "SRC-GATE-3", "PARTY-3", "S-G", "CUSTOMS", "30", "20260528140700", "INFO", "L3"],
                ["ACT-H", "SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140700", "OVERRIDE", "L4"],
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert rows[1]["check_type"] == ""
        assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 7, "unmatched_amount": 191}

    def test_hold_id_requires_exact_match_not_prefix(self):
        """A correction must not match when only the leading hold_id prefix overlaps."""
        build_program()
        write_inputs(
            [["SRC-100000001", "BOX-1", "G-1", "MEDICAL", "15", "20260528140000", "ACTIVE", "LANE-1"]],
            [
                ["REL-PFX", "SRC-100", "BOX-1", "G-1", "MEDICAL", "15", "20260528140500", "CLEAR", "LANE-1"],
                ["REL-EXACT", "SRC-100000001", "BOX-1", "G-1", "MEDICAL", "15", "20260528140600", "CLEAR", "LANE-1"],
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert summary["matched_count"] == 1

    def test_gate_id_mismatch_blocks_match(self):
        """Corrections must share the same gate_id as the hold record."""
        build_program()
        write_inputs(
            [["SRC-GATE", "BOX-1", "G-ONE", "CUSTOMS", "20", "20260528140000", "ACTIVE", "LANE-1"]],
            [["REL-GATE", "SRC-GATE", "BOX-1", "G-TWO", "CUSTOMS", "20", "20260528140500", "MEDICAL", "LANE-1"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_carousel_mismatch_blocks_match(self):
        """Corrections must share the same carousel as the hold record."""
        build_program()
        write_inputs(
            [["SRC-CAR", "BOX-1", "G-1", "MEDICAL", "25", "20260528140000", "ACTIVE", "LANE-A"]],
            [["REL-CAR", "SRC-CAR", "BOX-1", "G-1", "MEDICAL", "25", "20260528140500", "CLEAR", "LANE-B"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_nonnumeric_timestamps_are_ineligible(self):
        """Nonnumeric hold or release timestamps must stay unmatched."""
        build_program()
        write_inputs(
            [
                ["SRC-BAD-SRC", "BOX-1", "G-1", "MEDICAL", "11", "not-a-ts", "ACTIVE", "LANE-1"],
                ["SRC-BAD-ACT", "BOX-2", "G-1", "CUSTOMS", "12", "20260528140000", "ACTIVE", "LANE-2"],
            ],
            [
                ["REL-1", "SRC-BAD-SRC", "BOX-1", "G-1", "MEDICAL", "11", "20260528140500", "CLEAR", "LANE-1"],
                ["REL-2", "SRC-BAD-ACT", "BOX-2", "G-1", "CUSTOMS", "12", "bad-action-ts", "MEDICAL", "LANE-2"],
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 0

    def test_legacy_alias_codes_stay_unmatched_in_milestone_1(self):
        """IN, CU, and SE alias codes are not eligible until milestone 2."""
        build_program()
        write_inputs(
            [["SRC-ALIAS", "BOX-1", "G-1", "MEDICAL", "40", "20260528140000", "ACTIVE", "LANE-1"]],
            [
                ["REL-IN", "SRC-ALIAS", "BOX-1", "G-1", "IN", "40", "20260528140500", "CLEAR", "LANE-1"],
                ["REL-SE", "SRC-ALIAS", "BOX-1", "G-1", "SE", "40", "20260528140600", "OVERRIDE", "LANE-1"],
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert all(row["check_type"] == "" for row in rows)

    def test_active_status_is_required(self):
        """A source hold with any status other than ACTIVE must not match."""
        build_program()
        write_inputs(
            [["SRC-STATUS", "BOX-1", "G-1", "MEDICAL", "25", "20260528100000", "CLOSED", "LANE-1"]],
            [["REL-STATUS", "SRC-STATUS", "BOX-1", "G-1", "MEDICAL", "25", "20260528100100", "CLEAR", "LANE-1"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["check_type"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 25}

    def test_reason_must_be_allowed(self):
        """A release reason outside the allowed milestone 1 set must not match."""
        build_program()
        write_inputs(
            [["SRC-REASON", "BOX-2", "G-1", "CUSTOMS", "35", "20260528100000", "ACTIVE", "LANE-2"]],
            [["REL-REASON", "SRC-REASON", "BOX-2", "G-1", "CUSTOMS", "35", "20260528100100", "INFO", "LANE-2"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["check_type"] == ""
        assert summary["unmatched_amount"] == 35

    def test_consumption_prevents_second_release_match(self):
        """A matched hold row must be consumed so a later duplicate release stays unmatched."""
        build_program()
        write_inputs(
            [["SRC-CONSUME", "BOX-3", "G-1", "MEDICAL", "45", "20260528100000", "ACTIVE", "LANE-3"]],
            [
                ["REL-CONSUME-1", "SRC-CONSUME", "BOX-3", "G-1", "MEDICAL", "45", "20260528100100", "CLEAR", "LANE-3"],
                ["REL-CONSUME-2", "SRC-CONSUME", "BOX-3", "G-1", "MEDICAL", "45", "20260528100200", "CLEAR", "LANE-3"],
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["check_type"] for row in rows] == ["MEDICAL", ""]
        assert summary == {"matched_count": 1, "matched_amount": 45, "unmatched_count": 1, "unmatched_amount": 45}
