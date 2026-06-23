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


def write_inputs(source, action, windows=None):
    """Overwrite input files at runtime."""
    write_csv(SOURCE, ["hold_id", "container_id", "gate_id", "hold_type", "amount", "hold_ts", "status", "lane"], source)
    write_csv(ACTION, ["release_id", "hold_id", "container_id", "gate_id", "hold_type", "amount", "release_ts", "reason", "lane"], action)
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


class TestMilestone2:
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
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["hold_type"] for row in rows] == ["INSPECTION", "CUSTOMS", "SECURITY"]
        assert summary == {"matched_count": 3, "matched_amount": 102, "unmatched_count": 0, "unmatched_amount": 0}

    def test_source_side_aliases_are_normalized_before_matching(self):
        """Aliases in holds.csv should normalize too, not only release-side aliases."""
        build_program()
        write_inputs(
            [
                ["SRCALIAS1", "CUSTA1", "G-A", "in", "41", "20260528140000", "ACTIVE", "L1"],
                ["SRCALIAS2", "CUSTA2", "G-A", " CU ", "42", "20260528140100", "ACTIVE", "L2"],
                ["SRCALIAS3", "CUSTA3", "G-B", "se", "43", "20260528140200", "ACTIVE", "L3"],
            ],
            [
                ["REL-A1", "SRCALIAS1", "CUSTA1", "G-A", "INSPECTION", "41", "20260528140500", "CLINRED", "L1"],
                ["REL-A2", "SRCALIAS2", "CUSTA2", "G-A", "CUSTOMS", "42", "20260528140600", "WAIVED", "L2"],
                ["REL-A3", "SRCALIAS3", "CUSTA3", "G-B", "SECURITY", "43", "20260528140700", "OVERRIDE", "L3"],
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["hold_type"] for row in rows] == ["INSPECTION", "CUSTOMS", "SECURITY"]

    def test_security_alias_is_valid_canonical_from_milestone_2(self):
        """The SE alias should normalize to SECURITY and pass the canonical hold_type gate."""
        build_program()
        write_inputs(
            [["SRC-SECURITY", "BOX-SEC", "G-2", "SECURITY", "70", "20260528120000", "ACTIVE", "LANE-S"]],
            [["REL-SECURITY", "SRC-SECURITY", "BOX-SEC", "G-2", "SE", "70", "20260528120100", "OVERRIDE", "LANE-S"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["hold_type"] == "SECURITY"

    def test_unknown_hold_type_stays_unmatched_after_alias_normalization(self):
        """Unknown hold_type values must not match even when source and release use the same value."""
        build_program()
        write_inputs(
            [["SRC-BAD-TYPE", "BOX-BAD", "G-2", "BAD", "80", "20260528120000", "ACTIVE", "LANE-B"]],
            [["REL-BAD-TYPE", "SRC-BAD-TYPE", "BOX-BAD", "G-2", "BAD", "80", "20260528120100", "OVERRIDE", "LANE-B"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["hold_type"] == ""

    def test_hold_id_requires_exact_match_not_prefix(self):
        """Alias-aware matching still requires the full hold_id."""
        build_program()
        write_inputs(
            [["SRC-200000001", "BOX-1", "G-W", "INSPECTION", "18", "20260528140000", "ACTIVE", "L1"]],
            [
                ["REL-PFX", "SRC-200", "BOX-1", "G-W", "IN", "18", "20260528140500", "CLINRED", "L1"],
                ["REL-EXACT", "SRC-200000001", "BOX-1", "G-W", "in", "18", "20260528140600", "CLINRED", "L1"],
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[1]["hold_type"] == "INSPECTION"
