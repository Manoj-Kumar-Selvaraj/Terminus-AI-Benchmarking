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


class TestMilestone2:
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
                ["ACT-1", "SRC-100000001", "PARTY-1", "S-A", "in", "12", "20260528121000", "SPOIL", "LOC-1"],
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
    
    
    def test_security_alias_is_valid_canonical_from_milestone_2(self):
        """The SE alias should normalize to AMBIENT and pass the canonical temp_band gate."""
        build_program()
        write_inputs(
            [["SRC-AMBIENT", "BOX-SEC", "G-2", "AMBIENT", "70", "20260528120000", "QUARANTINED", "LANE-S"]],
            [["REL-AMBIENT", "SRC-AMBIENT", "BOX-SEC", "G-2", "SE", "70", "20260528120100", "OVERRIDE", "LANE-S"]],
            [["G-2", "20260528115900", "20260528123000", "OPEN"]],
        )
        rows, summary = run_program()
    
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["temp_band"] == "AMBIENT"
        assert summary == {"matched_count": 1, "matched_amount": 70, "unmatched_count": 0, "unmatched_amount": 0}
    
    
    def test_unknown_temp_band_stays_unmatched_after_alias_normalization(self):
        """Unknown temp_band values must not match even when source and release use the same value."""
        build_program()
        write_inputs(
            [["SRC-BAD-TYPE", "BOX-BAD", "G-2", "BAD", "80", "20260528120000", "QUARANTINED", "LANE-B"]],
            [["REL-BAD-TYPE", "SRC-BAD-TYPE", "BOX-BAD", "G-2", "BAD", "80", "20260528120100", "OVERRIDE", "LANE-B"]],
            [["G-2", "20260528115900", "20260528123000", "OPEN"]],
        )
        rows, summary = run_program()
    
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["temp_band"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 80}
    
    
    def test_fz_shorthand_does_not_satisfy_in_alias_requirement(self):
        """Only the documented IN/CU/SE aliases apply; FZ/CH/AM shorthand alone is insufficient."""
        build_program()
        write_inputs(
            [["SRC-FZ", "BOX-FZ", "G-2", "FROZEN", "60", "20260528120000", "QUARANTINED", "LANE-F"]],
            [["REL-FZ", "SRC-FZ", "BOX-FZ", "G-2", "FZ", "60", "20260528120100", "OVERRIDE", "LANE-F"]],
            [["G-2", "20260528115900", "20260528123000", "OPEN"]],
        )
        rows, summary = run_program()
    
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["temp_band"] == ""
        assert summary["unmatched_amount"] == 60
