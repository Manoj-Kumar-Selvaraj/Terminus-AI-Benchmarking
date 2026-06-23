"""Verifier tests for realtime warehouse pickwave shortage reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
GO = Path("/usr/local/go/bin/go")
BIN = APP / "build" / "reconcile"
SOURCE = APP / "data" / "picks.csv"
ACTION = APP / "data" / "shortages.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "shortage_report.csv"
SUMMARY = APP / "out" / "shortage_summary.txt"


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
    write_csv(SOURCE, ["pick_id", "sku", "wave_id", "kind", "amount", "source_ts", "status", "location"], source)
    write_csv(ACTION, ["action_id", "pick_id", "sku", "wave_id", "kind", "amount", "action_ts", "reason", "location"], action)
    if windows is not None:
        write_csv(WINDOWS, ["wave_id", "open_ts", "close_ts", "state"], windows)
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
        """Only ACT-A should MATCH; the other seven corrections stay UNMATCHED with positive unmatched totals."""
        build_program()
        write_inputs(
            [
                ["SRC-GATE-1", "PARTY-1", "S-G", "EACH", "10", "20260528140000", "FULFILLED", "L1"],
                ["SRC-GATE-2", "PARTY-2", "S-G", "EACH", "20", "20260528140100", "BAD", "L2"],
                ["SRC-GATE-3", "PARTY-3", "S-G", "CASE", "30", "20260528140200", "FULFILLED", "L3"],
                ["SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140300", "FULFILLED", "L4"],
            ],
            [
                ["ACT-A", "SRC-GATE-1", "PARTY-1", "S-G", "EACH", "10", "20260528140500", "DAMAGE", "L1"],
                ["ACT-B", "SRC-GATE-1", "PARTY-1", "S-G", "EACH", "10", "20260528140600", "DAMAGE", "L1"],
                ["ACT-C", "SRC-GATE-2", "PARTY-2", "S-G", "EACH", "20", "20260528140700", "DAMAGE", "L2"],
                ["ACT-D", "SRC-GATE-3", "PARTY-X", "S-G", "CASE", "30", "20260528140700", "MISSING", "L3"],
                ["ACT-E", "SRC-GATE-3", "PARTY-3", "S-G", "CASE", "31", "20260528140700", "MISSING", "L3"],
                ["ACT-F", "SRC-GATE-3", "PARTY-3", "S-G", "CASE", "30", "20260528135959", "MISSING", "L3"],
                ["ACT-G", "SRC-GATE-3", "PARTY-3", "S-G", "CASE", "30", "20260528140700", "INFO", "L3"],
                ["ACT-H", "SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140700", "MISROUTE", "L4"],
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert rows[0]["action_id"] == "ACT-A"
        assert rows[0]["pick_id"] == "SRC-GATE-1"
        assert rows[0]["amount"] == "10"
        assert rows[0]["reason"] == "DAMAGE"
        assert rows[0]["kind"] == "EACH"
        assert rows[1]["kind"] == ""
        assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 7, "unmatched_amount": 191}

    def test_pick_id_requires_exact_match_not_prefix(self):
        """A correction must not match a pick record when only the leading pick_id prefix overlaps."""
        build_program()
        write_inputs(
            [["SRC-100000001", "PARTY-1", "S-W", "EACH", "15", "20260528140000", "FULFILLED", "L1"]],
            [
                ["ACT-PFX", "SRC-100", "PARTY-1", "S-W", "EACH", "15", "20260528140500", "DAMAGE", "L1"],
                ["ACT-EXACT", "SRC-100000001", "PARTY-1", "S-W", "EACH", "15", "20260528140600", "DAMAGE", "L1"],
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[1]["kind"] == "EACH"
        assert summary["matched_count"] == 1
        assert summary["matched_amount"] == 15

    def test_kind_trim_and_case_fold_before_matching(self):
        """Non-canonical kind text must normalize to EACH before matching."""
        build_program()
        write_inputs(
            [["SRC-1", "PARTY-1", "S-K", "each", "5", "20260528140000", "FULFILLED", "L1"]],
            [["ACT-1", "SRC-1", "PARTY-1", "S-K", " Each ", "5", "20260528140500", "DAMAGE", "L1"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["kind"] == "EACH"
        assert summary["matched_count"] == 1

    def test_wave_id_mismatch_blocks_match(self):
        """Corrections must share the same wave_id as the pick record."""
        build_program()
        write_inputs(
            [["SRC-WAVE-1", "PARTY-1", "W-ONE", "EACH", "20", "20260528140000", "FULFILLED", "L1"]],
            [["ACT-WAVE", "SRC-WAVE-1", "PARTY-1", "W-TWO", "EACH", "20", "20260528140500", "MISSING", "L1"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary["matched_count"] == 0

    def test_location_mismatch_blocks_match(self):
        """Corrections must share the same location as the pick record."""
        build_program()
        write_inputs(
            [["SRC-LOC-1", "PARTY-1", "S-L", "CASE", "25", "20260528140000", "FULFILLED", "BIN-A"]],
            [["ACT-LOC", "SRC-LOC-1", "PARTY-1", "S-L", "CASE", "25", "20260528140500", "DAMAGE", "BIN-B"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_nonnumeric_timestamps_are_ineligible(self):
        """Nonnumeric source or correction timestamps must stay unmatched."""
        build_program()
        write_inputs(
            [
                ["SRC-BAD-SRC", "PARTY-1", "S-T", "EACH", "11", "not-a-ts", "FULFILLED", "L1"],
                ["SRC-BAD-ACT", "PARTY-2", "S-T", "EACH", "12", "20260528140000", "FULFILLED", "L2"],
            ],
            [
                ["ACT-1", "SRC-BAD-SRC", "PARTY-1", "S-T", "EACH", "11", "20260528140500", "DAMAGE", "L1"],
                ["ACT-2", "SRC-BAD-ACT", "PARTY-2", "S-T", "EACH", "12", "bad-action-ts", "MISSING", "L2"],
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 0

    def test_short_numeric_timestamp_is_ineligible(self):
        """Numeric timestamps shorter than 14 digits must stay unmatched."""
        build_program()
        write_inputs(
            [
                ["SRC-SHORT", "PARTY-3", "S-T", "EACH", "13", "202605281400", "FULFILLED", "L3"],
                ["SRC-OK", "PARTY-4", "S-T", "CASE", "14", "20260528140000", "FULFILLED", "L4"],
            ],
            [
                ["ACT-SHORT", "SRC-SHORT", "PARTY-3", "S-T", "EACH", "13", "20260528140500", "MISSING", "L3"],
                ["ACT-OK", "SRC-OK", "PARTY-4", "S-T", "CASE", "14", "20260528140500", "DAMAGE", "L4"],
            ],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert rows[1]["status"] == "MATCHED"
        assert rows[1]["kind"] == "CASE"
        assert summary["matched_count"] == 1

    def test_pallet_kind_stays_unmatched_in_milestone_1(self):
        """PALLET and PL aliases are not eligible until milestone 2."""
        build_program()
        write_inputs(
            [["SRC-PAL-1", "PARTY-1", "S-P", "PALLET", "40", "20260528140000", "FULFILLED", "L1"]],
            [
                ["ACT-PAL", "SRC-PAL-1", "PARTY-1", "S-P", "PALLET", "40", "20260528140500", "MISROUTE", "L1"],
                ["ACT-PL", "SRC-PAL-1", "PARTY-1", "S-P", "PL", "40", "20260528140600", "DAMAGE", "L1"],
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert all(row["kind"] == "" for row in rows)
        assert summary["matched_count"] == 0
