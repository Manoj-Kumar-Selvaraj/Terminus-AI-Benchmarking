"""Verifier tests for realtime clinic referral claim reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "appointments.csv"
ACTION = APP / "data" / "claims.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "claim_route_report.csv"
SUMMARY = APP / "out" / "claim_route_summary.txt"


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
    write_csv(SOURCE, ["referral_id", "member_id", "site_id", "kind", "amount", "source_ts", "status", "location"], source)
    write_csv(ACTION, ["action_id", "referral_id", "member_id", "site_id", "kind", "amount", "action_ts", "reason", "location"], action)
    write_csv(WINDOWS, ["site_id", "open_ts", "close_ts", "state"], windows)
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
            ["SRC-GATE-1", "PARTY-1", "S-G", "PCP", "10", "20260528140000", "COMPLETE", "L1"],
            ["SRC-GATE-2", "PARTY-2", "S-G", "PCP", "20", "20260528140100", "BAD", "L2"],
            ["SRC-GATE-3", "PARTY-3", "S-G", "SPEC", "30", "20260528140200", "COMPLETE", "L3"],
            ["SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140300", "COMPLETE", "L4"],
        ],
        [
            ["ACT-A", "SRC-GATE-1", "PARTY-1", "S-G", "PCP", "10", "20260528140500", "AUTH", "L1"],
            ["ACT-B", "SRC-GATE-1", "PARTY-1", "S-G", "PCP", "10", "20260528140600", "AUTH", "L1"],
            ["ACT-C", "SRC-GATE-2", "PARTY-2", "S-G", "PCP", "20", "20260528140700", "AUTH", "L2"],
            ["ACT-D", "SRC-GATE-3", "PARTY-X", "S-G", "SPEC", "30", "20260528140700", "REBILL", "L3"],
            ["ACT-E", "SRC-GATE-3", "PARTY-3", "S-G", "SPEC", "31", "20260528140700", "REBILL", "L3"],
            ["ACT-F", "SRC-GATE-3", "PARTY-3", "S-G", "SPEC", "30", "20260528135959", "REBILL", "L3"],
            ["ACT-G", "SRC-GATE-3", "PARTY-3", "S-G", "SPEC", "30", "20260528140700", "INFO", "L3"],
            ["ACT-H", "SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140700", "TRANSFER", "L4"],
        ],
        [["S-G", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert rows[1]["kind"] == ""
    assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 7, "unmatched_amount": 191}
def test_aliases_full_keys_and_canonical_output():
    """Aliases should match full source keys and emit canonical kind values."""
    build_program()
    write_inputs(
        [
            ["SRC-100000001", "PARTY-1", "S-A", "PCP", "12", "20260528120500", "COMPLETE", "LOC-1"],
            ["SRC-100000002", "PARTY-2", "S-A", "SPEC", "34", "20260528120600", "COMPLETE", "LOC-2"],
            ["SRC-100000003", "PARTY-3", "S-B", "LAB", "56", "20260528130500", "COMPLETE", "LOC-3"],
        ],
        [
            ["ACT-1", "SRC-100000001", "PARTY-1", "S-A", "PRIMARY", "12", "20260528121000", "AUTH", "LOC-1"],
            ["ACT-2", "SRC-100000002", "PARTY-2", "S-A", "SPECIAL", "34", "20260528121100", "REBILL", "LOC-2"],
            ["ACT-3", "SRC-100000003", "PARTY-3", "S-B", "LABORATORY", "56", "20260528131000", "TRANSFER", "LOC-3"],
        ],
        [["S-A", "20260528120000", "20260528123000", "OPEN"], ["S-B", "20260528130000", "20260528133000", "OPEN"]],
    )
    rows, summary = run_program()
    assert REPORT.read_text().splitlines()[0] == "action_id,referral_id,member_id,site_id,kind,amount,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["kind"] for row in rows] == ["PCP", "SPEC", "LAB"]
    assert summary == {"matched_count": 3, "matched_amount": 102, "unmatched_count": 0, "unmatched_amount": 0}
