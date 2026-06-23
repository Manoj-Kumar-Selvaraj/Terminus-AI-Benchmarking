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


class TestMilestone2:
    def test_all_gates_consumption_and_positive_unmatched_totals(self):
        """Every identity, status, timestamp, reason, and consumption gate should reject bad candidates."""
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
        assert rows[1]["kind"] == ""
        assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 7, "unmatched_amount": 191}

    def test_aliases_full_keys_and_canonical_output(self):
        """Aliases should match full source keys and emit canonical kind values."""
        build_program()
        write_inputs(
            [
                ["SRC-100000001", "PARTY-1", "S-A", "EACH", "12", "20260528120500", "FULFILLED", "LOC-1"],
                ["SRC-100000002", "PARTY-2", "S-A", "CASE", "34", "20260528120600", "FULFILLED", "LOC-2"],
                ["SRC-100000003", "PARTY-3", "S-B", "PALLET", "56", "20260528130500", "FULFILLED", "LOC-3"],
            ],
            [
                ["ACT-1", "SRC-100000001", "PARTY-1", "S-A", "EA", "12", "20260528121000", "DAMAGE", "LOC-1"],
                ["ACT-2", "SRC-100000002", "PARTY-2", "S-A", "CS", "34", "20260528121100", "MISSING", "LOC-2"],
                ["ACT-3", "SRC-100000003", "PARTY-3", "S-B", "PL", "56", "20260528131000", "MISROUTE", "LOC-3"],
            ],
        )
        rows, summary = run_program()
        assert REPORT.read_text().splitlines()[0] == "action_id,pick_id,sku,wave_id,kind,amount,reason,status"
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["kind"] for row in rows] == ["EACH", "CASE", "PALLET"]
        assert summary == {"matched_count": 3, "matched_amount": 102, "unmatched_count": 0, "unmatched_amount": 0}

    def test_trim_and_case_fold_alias_normalization(self):
        """Aliases must normalize after trimming whitespace and case folding."""
        build_program()
        write_inputs(
            [
                ["SRC-A1", "PARTY-1", "S-A", "EACH", "10", "20260528140000", "FULFILLED", "L1"],
                ["SRC-A2", "PARTY-2", "S-A", "CASE", "20", "20260528140100", "FULFILLED", "L2"],
                ["SRC-A3", "PARTY-3", "S-B", "PALLET", "30", "20260528140200", "FULFILLED", "L3"],
            ],
            [
                ["ACT-1", "SRC-A1", "PARTY-1", "S-A", " ea ", "10", "20260528140500", "DAMAGE", "L1"],
                ["ACT-2", "SRC-A2", "PARTY-2", "S-A", "cs", "20", "20260528140600", "MISSING", "L2"],
                ["ACT-3", "SRC-A3", "PARTY-3", "S-B", " pl ", "30", "20260528140700", "MISROUTE", "L3"],
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["kind"] for row in rows] == ["EACH", "CASE", "PALLET"]
        assert summary["matched_count"] == 3

    def test_pick_id_requires_exact_match_not_prefix(self):
        """Alias-aware matching still requires the full pick_id."""
        build_program()
        write_inputs(
            [["SRC-200000001", "PARTY-1", "S-W", "EACH", "18", "20260528140000", "FULFILLED", "L1"]],
            [
                ["ACT-PFX", "SRC-200", "PARTY-1", "S-W", "EA", "18", "20260528140500", "DAMAGE", "L1"],
                ["ACT-EXACT", "SRC-200000001", "PARTY-1", "S-W", "ea", "18", "20260528140600", "DAMAGE", "L1"],
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[1]["kind"] == "EACH"
        assert summary["matched_count"] == 1

    def test_location_mismatch_blocks_alias_aware_matching(self):
        """Alias normalization must not weaken the location identity gate."""
        build_program()
        write_inputs(
            [["SRC-LOC-M2", "PARTY-LOC", "S-LOC", "EACH", "44", "20260528140000", "FULFILLED", "LOCKER-A"]],
            [["ACT-LOC-M2", "SRC-LOC-M2", "PARTY-LOC", "S-LOC", "EA", "44", "20260528140500", "DAMAGE", "LOCKER-B"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary["matched_count"] == 0

    def test_wave_id_mismatch_blocks_alias_aware_matching(self):
        """Alias normalization must not weaken the wave_id identity gate."""
        build_program()
        write_inputs(
            [["SRC-W1", "SKU-1", "WAVE-A", "EACH", "10", "20260528140000", "FULFILLED", "L1"]],
            [["ACT-W1", "SRC-W1", "SKU-1", "WAVE-B", "EA", "10", "20260528140500", "DAMAGE", "L1"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary["matched_count"] == 0

    def test_unknown_kind_same_on_both_sides_still_unmatched(self):
        """Unknown kinds stay ineligible even when source and correction use the same value."""
        build_program()
        write_inputs(
            [["SRC-U1", "SKU-1", "W-1", "BUNDLE", "10", "20260528140000", "FULFILLED", "L1"]],
            [["ACT-U1", "SRC-U1", "SKU-1", "W-1", "BUNDLE", "10", "20260528140500", "DAMAGE", "L1"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary["matched_count"] == 0
