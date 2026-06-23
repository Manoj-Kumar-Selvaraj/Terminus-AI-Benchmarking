"""Verifier tests for realtime pharmacy coldchain exception routing reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
GO = Path("/usr/local/go/bin/go")
BIN = APP / "build" / "reconcile"
SOURCE = APP / "data" / "accessions.csv"
ACTION = APP / "data" / "exceptions.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "coldchain_exception_report.csv"
SUMMARY = APP / "out" / "coldchain_exception_summary.txt"


def build_program():
    """Compile the Go reconciler and run the batch script."""
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
    write_csv(SOURCE, ["shipment_id", "pharmacy_id", "chain_id", "package_type", "amount", "scan_ts", "status", "depot"], source)
    write_csv(ACTION, ["exception_id", "shipment_id", "pharmacy_id", "chain_id", "package_type", "amount", "exception_ts", "reason", "depot"], action)
    write_csv(WINDOWS, ["chain_id", "open_ts", "close_ts", "state"], windows)
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


def test_all_gates_consumption_and_positive_unmatched_totals():
    """Every identity, status, timestamp, reason, and consumption gate should reject bad candidates."""
    build_program()
    write_inputs(
        [
            ["SRC-GATE-1", "PARTY-1", "S-G", "CHEM", "10", "20260528140000", "RECEIVED", "L1"],
            ["SRC-GATE-2", "PARTY-2", "S-G", "CHEM", "20", "20260528140100", "BAD", "L2"],
            ["SRC-GATE-3", "PARTY-3", "S-G", "HEME", "30", "20260528140200", "RECEIVED", "L3"],
            ["SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140300", "RECEIVED", "L4"],
        ],
        [
            ["ACT-A", "SRC-GATE-1", "PARTY-1", "S-G", "CHEM", "10", "20260528140500", "SPLIT", "L1"],
            ["ACT-B", "SRC-GATE-1", "PARTY-1", "S-G", "CHEM", "10", "20260528140600", "SPLIT", "L1"],
            ["ACT-C", "SRC-GATE-2", "PARTY-2", "S-G", "CHEM", "20", "20260528140700", "SPLIT", "L2"],
            ["ACT-D", "SRC-GATE-3", "PARTY-X", "S-G", "HEME", "30", "20260528140700", "TEMPBREACH", "L3"],
            ["ACT-E", "SRC-GATE-3", "PARTY-3", "S-G", "HEME", "31", "20260528140700", "TEMPBREACH", "L3"],
            ["ACT-F", "SRC-GATE-3", "PARTY-3", "S-G", "HEME", "30", "20260528135959", "TEMPBREACH", "L3"],
            ["ACT-G", "SRC-GATE-3", "PARTY-3", "S-G", "HEME", "30", "20260528140700", "INFO", "L3"],
            ["ACT-H", "SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140700", "RECHECK", "L4"],
        ],
        [["S-G", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert rows[1]["package_type"] == ""
    assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 7, "unmatched_amount": 191}
