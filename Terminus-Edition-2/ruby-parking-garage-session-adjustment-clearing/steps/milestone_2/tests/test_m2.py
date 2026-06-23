"""Verifier tests for parking garage session adjustment clearing milestone 2."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "sessions.csv"
ACTION = APP / "data" / "adjustments.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "cod_parking_adjustment_report.csv"
SUMMARY = APP / "out" / "cod_parking_adjustment_summary.txt"


def write_csv(path, header, rows):
    """Write one CSV fixture."""
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(source, action, windows):
    """Overwrite all input files at runtime."""
    write_csv(SOURCE, ["parcel_id", "plate_id", "station_id", "rate_type", "amount", "entry_ts", "status", "level"], source)
    write_csv(ACTION, ["adjustment_id", "parcel_id", "plate_id", "station_id", "rate_type", "amount", "adjust_ts", "reason", "level"], action)
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
    for line in SUMMARY.read_text().strip().splitlines():
        key, value = line.strip().split("=", 1)
        summary[key.strip()] = int(value.strip())
    return rows, summary


class TestMilestone2:
    def test_aliases_full_keys_and_canonical_output(self):
        """Aliases should match full source keys and emit canonical rate_type values."""
        write_inputs(
            [
                ["SRC-100000001", "PARTY-1", "S-A", "HOURLY", "12", "20260528120500", "CLOSED", "LOC-1"],
                ["SRC-100000002", "PARTY-2", "S-A", "DAILY", "34", "20260528120600", "CLOSED", "LOC-2"],
                ["SRC-100000003", "PARTY-3", "S-B", "EVENT", "56", "20260528130500", "CLOSED", "LOC-3"],
            ],
            [
                ["ACT-1", "SRC-100000001", "PARTY-1", "S-A", "HR", "12", "20260528121000", "REFUND", "LOC-1"],
                ["ACT-2", "SRC-100000002", "PARTY-2", "S-A", "QR", "34", "20260528121100", "SHORT", "LOC-2"],
                ["ACT-3", "SRC-100000003", "PARTY-3", "S-B", "CC", "56", "20260528131000", "WAIVE", "LOC-3"],
            ],
            [["S-A", "20260528120000", "20260528123000", "OPEN"], ["S-B", "20260528130000", "20260528133000", "OPEN"]],
        )
        rows, summary = run_program()
        assert REPORT.read_text().splitlines()[0] == "adjustment_id,parcel_id,plate_id,station_id,rate_type,amount,reason,status"
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["rate_type"] for row in rows] == ["HOURLY", "DAILY", "EVENT"]
        assert summary == {"matched_count": 3, "matched_amount": 102, "unmatched_count": 0, "unmatched_amount": 0}

    def test_unknown_rate_type_stays_unmatched_even_when_both_sides_match(self):
        """Shared unknown rate_type values must not match from milestone 2 onward."""
        write_inputs(
            [["SRC-UNK-1", "PARTY-U", "S-U", "BAD", "18", "20260528170000", "CLOSED", "L1"]],
            [["ACT-UNK-1", "SRC-UNK-1", "PARTY-U", "S-U", "BAD", "18", "20260528170100", "REFUND", "L1"]],
            [["S-U", "20260528165900", "20260528173000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_inactive_source_with_alias_kind_remains_unmatched(self):
        """Milestone 1 status gating must still apply after alias normalization."""
        write_inputs(
            [["SRC-400", "PARTY-7", "S-A", "HOURLY", "1000", "20260528100000", "BAD", "L1"]],
            [["ACT-400", "SRC-400", "PARTY-7", "S-A", "HR", "1000", "20260528100500", "REFUND", "L1"]],
            [["S-A", "20260528090000", "20260528103000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["rate_type"] == ""
        assert summary["matched_count"] == 0

    def test_alias_case_folding_and_trim_are_required(self):
        """Aliases must normalize after trimming and case folding on both sides."""
        write_inputs(
            [
                ["SRC-CF1", "P-CF", "S-CF", "HOURLY", "10", "20260528140000", "CLOSED", "L1"],
                ["SRC-CF2", "P-CF", "S-CF", "DAILY", "20", "20260528140100", "CLOSED", "L1"],
                ["SRC-CF3", "P-CF", "S-CF", "EVENT", "30", "20260528140200", "CLOSED", "L1"],
            ],
            [
                ["ACT-CF1", "SRC-CF1", "P-CF", "S-CF", " hr ", "10", "20260528140500", "REFUND", "L1"],
                ["ACT-CF2", "SRC-CF2", "P-CF", "S-CF", " qr ", "20", "20260528140600", "SHORT", "L1"],
                ["ACT-CF3", "SRC-CF3", "P-CF", "S-CF", " cc ", "30", "20260528140700", "WAIVE", "L1"],
            ],
            [["S-CF", "20260528135900", "20260528143000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["rate_type"] for row in rows] == ["HOURLY", "DAILY", "EVENT"]
        assert summary == {"matched_count": 3, "matched_amount": 60, "unmatched_count": 0, "unmatched_amount": 0}

    def test_source_alias_normalization_matches_canonical_correction(self):
        """Source rows with alias rate_type values must normalize before matching."""
        write_inputs(
            [
                ["SRC-ALIAS-SRC", "PARTY-X", "S-A", "HR", "12", "20260528120500", "CLOSED", "LOC-1"],
                ["SRC-CANON", "PARTY-Y", "S-A", "DAILY", "34", "20260528120600", "CLOSED", "LOC-2"],
            ],
            [
                ["ACT-1", "SRC-ALIAS-SRC", "PARTY-X", "S-A", "HOURLY", "12", "20260528121000", "REFUND", "LOC-1"],
                ["ACT-2", "SRC-CANON", "PARTY-Y", "S-A", "QR", "34", "20260528121100", "SHORT", "LOC-2"],
            ],
            [["S-A", "20260528120000", "20260528123000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["rate_type"] for row in rows] == ["HOURLY", "DAILY"]
        assert summary == {"matched_count": 2, "matched_amount": 46, "unmatched_count": 0, "unmatched_amount": 0}

    def test_level_mismatch_blocks_otherwise_valid_alias_match(self):
        """Level must independently match in milestone 2."""
        write_inputs(
            [["SRC-LVL", "PARTY-L", "S-G", "HOURLY", "15", "20260528140000", "CLOSED", "LEVEL-A"]],
            [["ACT-LVL", "SRC-LVL", "PARTY-L", "S-G", "HR", "15", "20260528140500", "REFUND", "LEVEL-B"]],
            [["S-G", "20260528135900", "20260528143000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["rate_type"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 15}

    def test_cc_alias_consumption_blocks_second_adjustment(self):
        """Alias-normalized EVENT rows must still obey one-session-per-parcel consumption."""
        write_inputs(
            [["SRC-CON", "PARTY-C", "S-W", "EVENT", "55", "20260528160000", "CLOSED", "L1"]],
            [
                ["ACT-1", "SRC-CON", "PARTY-C", "S-W", "CC", "55", "20260528160500", "REFUND", "L1"],
                ["ACT-2", "SRC-CON", "PARTY-C", "S-W", "CC", "55", "20260528160600", "WAIVE", "L1"],
            ],
            [["S-W", "20260528155900", "20260528163000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["rate_type"] for row in rows] == ["EVENT", ""]
        assert summary == {"matched_count": 1, "matched_amount": 55, "unmatched_count": 1, "unmatched_amount": 55}

    def test_closed_window_rejects_otherwise_valid_alias_match(self):
        """Closed windows must reject matches even when alias normalization and other keys align."""
        write_inputs(
            [["SRC-W", "P-W", "S-W", "HR", "40", "20260528140000", "CLOSED", "L1"]],
            [["ACT-W", "SRC-W", "P-W", "S-W", "HOURLY", "40", "20260528140500", "REFUND", "L1"]],
            [["S-W", "20260528120000", "20260528130000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["rate_type"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 40}
