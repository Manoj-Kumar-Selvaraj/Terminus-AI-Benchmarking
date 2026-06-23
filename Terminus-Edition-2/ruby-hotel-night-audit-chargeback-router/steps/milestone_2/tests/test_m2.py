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


class TestMilestone2:
    def test_aliases_full_keys_and_canonical_output(self):
        """Aliases should match full source keys and emit canonical kind values."""
        build_program()
        write_inputs(
            [
                ["SRC-100000001", "PARTY-1", "S-A", "CARD", "12", "20260528120500", "POSTED", "LOC-1"],
                ["SRC-100000002", "PARTY-2", "S-A", "CASH", "34", "20260528120600", "POSTED", "LOC-2"],
                ["SRC-100000003", "PARTY-3", "S-B", "POINTS", "56", "20260528130500", "POSTED", "LOC-3"],
            ],
            [
                ["ACT-1", "SRC-100000001", "PARTY-1", "S-A", "CC", "12", "20260528121000", "DISPUTE", "LOC-1"],
                ["ACT-2", "SRC-100000002", "PARTY-2", "S-A", "CSH", "34", "20260528121100", "DUPLICATE", "LOC-2"],
                ["ACT-3", "SRC-100000003", "PARTY-3", "S-B", "PTS", "56", "20260528131000", "NOAUTH", "LOC-3"],
            ],
            [["S-A", "20260528120000", "20260528123000", "OPEN"], ["S-B", "20260528130000", "20260528133000", "OPEN"]],
        )
        rows, summary = run_program()
        assert REPORT.read_text().splitlines()[0] == "action_id,folio_id,guest_id,property_id,kind,amount,reason,status"
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["kind"] for row in rows] == ["CARD", "CASH", "POINTS"]
        assert summary == {"matched_count": 3, "matched_amount": 102, "unmatched_count": 0, "unmatched_amount": 0}

    def test_unknown_kind_alias_stays_unmatched(self):
        """Shared unknown kind aliases must not match from milestone 2 onward."""
        build_program()
        write_inputs(
            [["SRC-UNK", "PARTY-U", "S-U", "BAD", "18", "20260528170000", "POSTED", "L1"]],
            [["ACT-UNK", "SRC-UNK", "PARTY-U", "S-U", "BAD", "18", "20260528170100", "DISPUTE", "L1"]],
            [["S-U", "20260528165900", "20260528173000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary["matched_count"] == 0

    def test_location_mismatch_blocks_alias_match(self):
        """Location must still gate matching after alias normalization."""
        build_program()
        write_inputs(
            [["SRC-LOC", "PARTY-L", "S-A", "CARD", "25", "20260528140000", "POSTED", "L-ORIG"]],
            [["ACT-LOC", "SRC-LOC", "PARTY-L", "S-A", "CC", "25", "20260528140500", "DISPUTE", "L-OTHER"]],
            [["S-A", "20260528135900", "20260528143000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary["unmatched_amount"] == 25
