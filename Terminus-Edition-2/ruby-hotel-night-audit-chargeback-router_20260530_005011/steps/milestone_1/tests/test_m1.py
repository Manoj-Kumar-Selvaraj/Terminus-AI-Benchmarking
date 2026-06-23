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


def test_all_gates_consumption_and_positive_unmatched_totals():
    """Every identity, status, timestamp, reason, and consumption gate should reject bad candidates."""
    build_program()
    write_inputs(
        [
            # ACT-A: valid source consumed by the first matching correction.
            ["SRC-GATE-1", "PARTY-1", "S-G", "CARD", "10", "20260528140000", "POSTED", "L1"],
            # ACT-C: source status gate rejects non-POSTED rows.
            ["SRC-GATE-2", "PARTY-2", "S-G", "CARD", "20", "20260528140100", "BAD", "L2"],
            # ACT-D through ACT-G share this source to isolate identity, amount, timestamp, and reason gates.
            ["SRC-GATE-3", "PARTY-3", "S-G", "CASH", "30", "20260528140200", "POSTED", "L3"],
            # ACT-H: canonical kind gate rejects unknown kind values.
            ["SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140300", "POSTED", "L4"],
            # ACT-I: numeric timestamp gate rejects malformed source timestamps.
            ["SRC-GATE-5", "PARTY-5", "S-G", "CARD", "50", "not-a-time", "POSTED", "L5"],
            # ACT-J: window close gate rejects corrections after close_ts.
            ["SRC-GATE-6", "PARTY-6", "S-G", "CARD", "60", "20260528140400", "POSTED", "L6"],
        ],
        [
            # Valid match.
            ["ACT-A", "SRC-GATE-1", "PARTY-1", "S-G", "CARD", "10", "20260528140500", "DISPUTE", "L1"],
            # Consumption: ACT-A already used SRC-GATE-1.
            ["ACT-B", "SRC-GATE-1", "PARTY-1", "S-G", "CARD", "10", "20260528140600", "DISPUTE", "L1"],
            # Status: source status is BAD.
            ["ACT-C", "SRC-GATE-2", "PARTY-2", "S-G", "CARD", "20", "20260528140700", "DISPUTE", "L2"],
            # Identity: guest_id differs.
            ["ACT-D", "SRC-GATE-3", "PARTY-X", "S-G", "CASH", "30", "20260528140700", "DUPLICATE", "L3"],
            # Amount: action amount differs.
            ["ACT-E", "SRC-GATE-3", "PARTY-3", "S-G", "CASH", "31", "20260528140700", "DUPLICATE", "L3"],
            # Timestamp ordering: action_ts is before source_ts.
            ["ACT-F", "SRC-GATE-3", "PARTY-3", "S-G", "CASH", "30", "20260528135959", "DUPLICATE", "L3"],
            # Reason: INFO is not eligible.
            ["ACT-G", "SRC-GATE-3", "PARTY-3", "S-G", "CASH", "30", "20260528140700", "INFO", "L3"],
            # Kind: BAD is not canonical.
            ["ACT-H", "SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140700", "NOAUTH", "L4"],
            # Numeric timestamp: source_ts is malformed.
            ["ACT-I", "SRC-GATE-5", "PARTY-5", "S-G", "CARD", "50", "20260528140700", "NOAUTH", "L5"],
            # Window close: action_ts is after close_ts.
            ["ACT-J", "SRC-GATE-6", "PARTY-6", "S-G", "CARD", "60", "20260528143100", "NOAUTH", "L6"],
        ],
        [["S-G", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert REPORT.read_text().splitlines()[0] == "action_id,folio_id,guest_id,property_id,kind,amount,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert rows[0] == {"action_id": "ACT-A", "folio_id": "SRC-GATE-1", "guest_id": "PARTY-1", "property_id": "S-G", "kind": "CARD", "amount": "10", "reason": "DISPUTE", "status": "MATCHED"}
    assert all(row["kind"] == "" for row in rows[1:])
    assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 9, "unmatched_amount": 301}
