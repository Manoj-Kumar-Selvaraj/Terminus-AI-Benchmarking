"""Milestone 2 tests for realtime courier COD remittance reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "deliveries.csv"
ACTION = APP / "data" / "remittances.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "cod_remittance_report.csv"
SUMMARY = APP / "out" / "cod_remittance_summary.txt"


def build_program():
    """Prepare the reconciler for one reconciliation scenario."""
    pass


def write_csv(path, header, rows):
    """Write one CSV fixture."""
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(source, action, windows):
    """Overwrite all input files at runtime."""
    write_csv(SOURCE, ["parcel_id", "courier_id", "station_id", "kind", "amount", "source_ts", "status", "location"], source)
    write_csv(ACTION, ["action_id", "parcel_id", "courier_id", "station_id", "kind", "amount", "action_ts", "reason", "location"], action)
    write_csv(WINDOWS, ["station_id", "open_ts", "close_ts", "state"], windows)
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
    def test_all_gates_consumption_and_positive_unmatched_totals(self):
        """Every identity, status, timestamp, reason, and consumption gate should reject bad candidates."""
        build_program()
        write_inputs(
            [
                ["SRC-GATE-1", "PARTY-1", "S-G", "CASH", "10", "20260528140000", "DELIVERED", "L1"],
                ["SRC-GATE-2", "PARTY-2", "S-G", "CASH", "20", "20260528140100", "BAD", "L2"],
                ["SRC-GATE-3", "PARTY-3", "S-G", "UPI", "30", "20260528140200", "DELIVERED", "L3"],
                ["SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140300", "DELIVERED", "L4"],
            ],
            [
                ["ACT-A", "SRC-GATE-1", "PARTY-1", "S-G", "CASH", "10", "20260528140500", "RETURN", "L1"],
                ["ACT-B", "SRC-GATE-1", "PARTY-1", "S-G", "CASH", "10", "20260528140600", "RETURN", "L1"],
                ["ACT-C", "SRC-GATE-2", "PARTY-2", "S-G", "CASH", "20", "20260528140700", "RETURN", "L2"],
                ["ACT-D", "SRC-GATE-3", "PARTY-X", "S-G", "UPI", "30", "20260528140700", "SHORT", "L3"],
                ["ACT-E", "SRC-GATE-3", "PARTY-3", "S-G", "UPI", "31", "20260528140700", "SHORT", "L3"],
                ["ACT-F", "SRC-GATE-3", "PARTY-3", "S-G", "UPI", "30", "20260528135959", "SHORT", "L3"],
                ["ACT-G", "SRC-GATE-3", "PARTY-3", "S-G", "UPI", "30", "20260528140700", "INFO", "L3"],
                ["ACT-H", "SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140700", "ADJUST", "L4"],
            ],
            [["S-G", "20260528135900", "20260528143000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert rows[1]["kind"] == ""
        assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 7, "unmatched_amount": 191}


    def test_location_mismatch_still_blocks_alias_aware_matching(self):
        """Alias normalization must not weaken the location identity gate."""
        build_program()
        write_inputs(
            [["SRC-LOC-M2", "PARTY-LOC", "S-LOC", "CARD", "44", "20260528140000", "DELIVERED", "LOCKER-A"]],
            [["ACT-LOC-M2", "SRC-LOC-M2", "PARTY-LOC", "S-LOC", "CC", "44", "20260528140500", "ADJUST", "LOCKER-B"]],
            [["S-LOC", "20260528135900", "20260528143000", "OPEN"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 44}


    def test_aliases_full_keys_and_canonical_output(self):
        """Aliases should match full source keys and emit canonical kind values."""
        build_program()
        write_inputs(
            [
                ["SRC-100000001", "PARTY-1", "S-A", "CASH", "12", "20260528120500", "DELIVERED", "LOC-1"],
                ["SRC-100000002", "PARTY-2", "S-A", "UPI", "34", "20260528120600", "DELIVERED", "LOC-2"],
                ["SRC-100000003", "PARTY-3", "S-B", "CARD", "56", "20260528130500", "DELIVERED", "LOC-3"],
            ],
            [
                ["ACT-1", "SRC-100000001", "PARTY-1", "S-A", "CSH", "12", "20260528121000", "RETURN", "LOC-1"],
                ["ACT-2", "SRC-100000002", "PARTY-2", "S-A", "QR", "34", "20260528121100", "SHORT", "LOC-2"],
                ["ACT-3", "SRC-100000003", "PARTY-3", "S-B", "CC", "56", "20260528131000", "ADJUST", "LOC-3"],
            ],
            [["S-A", "20260528120000", "20260528123000", "OPEN"], ["S-B", "20260528130000", "20260528133000", "OPEN"]],
        )
        rows, summary = run_program()
        assert REPORT.read_text().splitlines()[0] == "action_id,parcel_id,courier_id,station_id,kind,amount,reason,status"
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["kind"] for row in rows] == ["CASH", "UPI", "CARD"]
        assert summary == {"matched_count": 3, "matched_amount": 102, "unmatched_count": 0, "unmatched_amount": 0}


    def test_kind_aliases_trim_and_case_fold_before_matching(self):
        """Legacy kind aliases should normalize after trimming and case folding."""
        build_program()
        write_inputs(
            [
                ["SRC-A1", "PARTY-1", "S-A", " CASH ", "12", "20260528120500", "DELIVERED", "LOC-1"],
                ["SRC-A2", "PARTY-2", "S-A", "upi", "34", "20260528120600", "DELIVERED", "LOC-2"],
                ["SRC-A3", "PARTY-3", "S-B", "CaRd", "56", "20260528130500", "DELIVERED", "LOC-3"],
            ],
            [
                ["ACT-1", "SRC-A1", "PARTY-1", "S-A", " csh ", "12", "20260528121000", "RETURN", "LOC-1"],
                ["ACT-2", "SRC-A2", "PARTY-2", "S-A", " qr ", "34", "20260528121100", "SHORT", "LOC-2"],
                ["ACT-3", "SRC-A3", "PARTY-3", "S-B", " Cc ", "56", "20260528131000", "ADJUST", "LOC-3"],
            ],
            [["S-A", "20260528120000", "20260528123000", "OPEN"], ["S-B", "20260528130000", "20260528133000", "OPEN"]],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["kind"] for row in rows] == ["CASH", "UPI", "CARD"]
        assert summary == {"matched_count": 3, "matched_amount": 102, "unmatched_count": 0, "unmatched_amount": 0}

    def test_closed_missing_malformed_windows_still_reject_with_aliases(self):
        """Closed, malformed, unlisted windows and late action_ts must stay unmatched after alias normalization."""
        build_program()
        write_inputs(
            [
                ["SRC-OPEN", "P1", "S-O", "CASH", "10", "20260528150000", "DELIVERED", "L1"],
                ["SRC-CLOSED", "P2", "S-C", "UPI", "20", "20260528150000", "DELIVERED", "L2"],
                ["SRC-BAD", "P3", "S-M", "CARD", "30", "bad-time", "DELIVERED", "L3"],
                ["SRC-NOWIN", "P4", "S-X", "CASH", "40", "20260528150000", "DELIVERED", "L4"],
                ["SRC-LATE", "P5", "S-O", "UPI", "15", "20260528152000", "DELIVERED", "L5"],
            ],
            [
                ["ACT-OPEN", "SRC-OPEN", "P1", "S-O", "CSH", "10", "20260528150500", "RETURN", "L1"],
                ["ACT-CLOSED", "SRC-CLOSED", "P2", "S-C", "QR", "20", "20260528150500", "SHORT", "L2"],
                ["ACT-BAD", "SRC-BAD", "P3", "S-M", "CC", "30", "20260528150500", "ADJUST", "L3"],
                ["ACT-NOWIN", "SRC-NOWIN", "P4", "S-X", "CSH", "40", "20260528150500", "RETURN", "L4"],
                ["ACT-LATE", "SRC-LATE", "P5", "S-O", "QR", "15", "20260528153100", "SHORT", "L5"],
            ],
            [
                ["S-O", "20260528145900", "20260528153000", "OPEN"],
                ["S-C", "20260528145900", "20260528153000", "CLOS"],
                ["S-M", "bad-time", "20260528153000", "OPEN"],
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert rows[0]["kind"] == "CASH"
        assert all(row["kind"] == "" for row in rows[1:])
        assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 4, "unmatched_amount": 105}
