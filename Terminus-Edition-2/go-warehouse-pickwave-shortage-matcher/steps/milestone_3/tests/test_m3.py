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


def write_inputs(source, action, windows):
    """Overwrite all input files at runtime."""
    write_csv(SOURCE, ["pick_id", "sku", "wave_id", "kind", "amount", "source_ts", "status", "location"], source)
    write_csv(ACTION, ["action_id", "pick_id", "sku", "wave_id", "kind", "amount", "action_ts", "reason", "location"], action)
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


class TestMilestone3:
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
            [["S-G", "20260528135900", "20260528143000", "OPEN"]],
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
            [["S-A", "20260528120000", "20260528123000", "OPEN"], ["S-B", "20260528130000", "20260528133000", "OPEN"]],
        )
        rows, summary = run_program()
        assert REPORT.read_text().splitlines()[0] == "action_id,pick_id,sku,wave_id,kind,amount,reason,status"
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["kind"] for row in rows] == ["EACH", "CASE", "PALLET"]
        assert summary == {"matched_count": 3, "matched_amount": 102, "unmatched_count": 0, "unmatched_amount": 0}

    def test_closed_window_blocks_match(self):
        """Closed reservation windows must reject otherwise valid matches."""
        build_program()
        write_inputs(
            [["SRC-WIN-2", "PARTY-2", "S-C", "EACH", "2", "20260528150000", "FULFILLED", "L2"]],
            [["ACT-2", "SRC-WIN-2", "PARTY-2", "S-C", "EACH", "2", "20260528150500", "DAMAGE", "L2"]],
            [["S-C", "20260528145900", "20260528153000", "CLOS"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary["matched_count"] == 0

    def test_malformed_window_times_block_match(self):
        """Malformed source timestamps must stay unmatched even when a window row exists."""
        build_program()
        write_inputs(
            [["SRC-WIN-3", "PARTY-3", "S-M", "CASE", "3", "bad-time", "FULFILLED", "L3"]],
            [["ACT-3", "SRC-WIN-3", "PARTY-3", "S-M", "CASE", "3", "20260528150500", "MISSING", "L3"]],
            [["S-M", "bad-time", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary["matched_count"] == 0

    def test_window_state_malformed_times_latest_candidate_and_order(self):
        """Integration check for open-window match, closed/malformed rejection, and correction order."""
        build_program()
        write_inputs(
            [
                ["SRC-WIN-1", "PARTY-1", "S-O", "EACH", "1", "20260528150000", "FULFILLED", "L1"],
                ["SRC-WIN-2", "PARTY-2", "S-C", "EACH", "2", "20260528150000", "FULFILLED", "L2"],
                ["SRC-WIN-3", "PARTY-3", "S-M", "CASE", "3", "bad-time", "FULFILLED", "L3"],
                ["SRC-DUPE", "PARTY-4", "S-O", "EACH", "4", "20260528150100", "FULFILLED", "L4"],
                ["SRC-DUPE", "PARTY-4", "S-O", "CASE", "4", "20260528150200", "FULFILLED", "L4"],
            ],
            [
                ["ACT-1", "SRC-WIN-1", "PARTY-1", "S-O", "EACH", "1", "20260528150500", "DAMAGE", "L1"],
                ["ACT-2", "SRC-WIN-2", "PARTY-2", "S-C", "EACH", "2", "20260528150500", "DAMAGE", "L2"],
                ["ACT-3", "SRC-WIN-3", "PARTY-3", "S-M", "CASE", "3", "20260528150500", "MISSING", "L3"],
                ["ACT-4", "SRC-DUPE", "PARTY-4", "S-O", "CS", "4", "20260528150600", "MISROUTE", "L4"],
            ],
            [["S-O", "20260528145900", "20260528153000", "OPEN"], ["S-C", "20260528145900", "20260528153000", "CLOS"], ["S-M", "bad-time", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["action_id"] for row in rows] == ["ACT-1", "ACT-2", "ACT-3", "ACT-4"]
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert [row["kind"] for row in rows] == ["EACH", "", "", "CASE"]
        assert summary == {"matched_count": 2, "matched_amount": 5, "unmatched_count": 2, "unmatched_amount": 5}

    def test_latest_source_ts_selects_distinguishable_kind(self):
        """Latest source timestamp must win when duplicate keys differ only by kind and ts."""
        build_program()
        write_inputs(
            [
                ["SRC-TB", "PARTY-TB", "S-TB", "EACH", "8", "20260528150100", "FULFILLED", "L1"],
                ["SRC-TB", "PARTY-TB", "S-TB", "CASE", "8", "20260528150200", "FULFILLED", "L1"],
            ],
            [["ACT-TB", "SRC-TB", "PARTY-TB", "S-TB", "CS", "8", "20260528150600", "DAMAGE", "L1"]],
            [["S-TB", "20260528145900", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["kind"] == "CASE"
        assert summary["matched_count"] == 1

    def test_action_timestamp_after_window_close_is_unmatched(self):
        """Corrections after the window close must stay unmatched even when other keys align."""
        build_program()
        write_inputs(
            [["SRC-LATE-1", "PARTY-1", "S-LATE", "EACH", "14", "20260528150000", "FULFILLED", "L1"]],
            [["ACT-LATE", "SRC-LATE-1", "PARTY-1", "S-LATE", "EACH", "14", "20260528153100", "DAMAGE", "L1"]],
            [["S-LATE", "20260528145900", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount"] == 14

    def test_latest_source_ts_wins_when_multiple_rows_qualify(self):
        """Among same-amount candidates, the latest source_ts row must be consumed first."""
        build_program()
        write_inputs(
            [
                ["SRC-LAT-1", "PARTY-L", "S-L", "EACH", "1000", "20260801000000", "FULFILLED", "L1"],
                ["SRC-LAT-1", "PARTY-L", "S-L", "EACH", "1000", "20260805000000", "FULFILLED", "L1"],
                ["SRC-LAT-1", "PARTY-L", "S-L", "EACH", "1000", "20260803000000", "FULFILLED", "L1"],
            ],
            [
                ["ACT-LAT-1", "SRC-LAT-1", "PARTY-L", "S-L", "EACH", "1000", "20260806000000", "DAMAGE", "L1"],
                ["ACT-LAT-2", "SRC-LAT-1", "PARTY-L", "S-L", "EACH", "1000", "20260807000000", "DAMAGE", "L1"],
                ["ACT-LAT-3", "SRC-LAT-1", "PARTY-L", "S-L", "EACH", "1000", "20260808000000", "DAMAGE", "L1"],
            ],
            [
                ["S-L", "20260801000000", "20260809000000", "OPEN"],
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["kind"] for row in rows] == ["EACH", "EACH", "EACH"]
        assert summary == {
            "matched_count": 3,
            "matched_amount": 3000,
            "unmatched_count": 0,
            "unmatched_amount": 0,
        }

    def test_equal_source_ts_tie_uses_earliest_source_row(self):
        """When source_ts ties, distinct kinds must map to the earliest-positioned source row first."""
        build_program()
        write_inputs(
            [
                ["SRC-TIE-1", "PARTY-T", "S-TIE", "EACH", "33", "20260528200000", "FULFILLED", "L1"],
                ["SRC-TIE-1", "PARTY-T", "S-TIE", "CASE", "33", "20260528200000", "FULFILLED", "L1"],
            ],
            [
                ["ACT-TIE-1", "SRC-TIE-1", "PARTY-T", "S-TIE", "EA", "33", "20260528200100", "MISROUTE", "L1"],
                ["ACT-TIE-2", "SRC-TIE-1", "PARTY-T", "S-TIE", "CS", "33", "20260528200200", "MISROUTE", "L1"],
            ],
            [["S-TIE", "20260528195900", "20260528203000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["kind"] for row in rows] == ["EACH", "CASE"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount"] == 66

    def test_action_ts_equals_source_ts_is_matched(self):
        """Corrections with action_ts equal to source_ts must still match inside an open window."""
        build_program()
        write_inputs(
            [["SRC-EQ", "P1", "S-EQ", "EACH", "5", "20260528140000", "FULFILLED", "L1"]],
            [["ACT-EQ", "SRC-EQ", "P1", "S-EQ", "EACH", "5", "20260528140000", "DAMAGE", "L1"]],
            [["S-EQ", "20260528135900", "20260528143000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["kind"] == "EACH"
        assert summary["matched_count"] == 1

    def test_pick_id_wave_id_and_location_mismatch_stay_unmatched(self):
        """Window-aware matching still requires exact pick_id, wave_id, and location."""
        build_program()
        write_inputs(
            [["SRC-ID-1", "PARTY-1", "S-ID", "EACH", "9", "20260528140000", "FULFILLED", "LOC-1"]],
            [
                ["ACT-PFX", "SRC-ID", "PARTY-1", "S-ID", "EACH", "9", "20260528140500", "DAMAGE", "LOC-1"],
                ["ACT-WAVE", "SRC-ID-1", "PARTY-1", "S-OTHER", "EACH", "9", "20260528140500", "DAMAGE", "LOC-1"],
                ["ACT-LOC", "SRC-ID-1", "PARTY-1", "S-ID", "EACH", "9", "20260528140500", "DAMAGE", "LOC-2"],
            ],
            [["S-ID", "20260528135900", "20260528143000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 0

    def test_nonnumeric_timestamps_are_ineligible_with_windows(self):
        """Malformed source or action timestamps must fail window gates."""
        build_program()
        write_inputs(
            [["SRC-BAD", "PARTY-1", "S-T", "CASE", "7", "20260528140000", "FULFILLED", "L1"]],
            [["ACT-BAD", "SRC-BAD", "PARTY-1", "S-T", "CS", "7", "not-numeric", "MISSING", "L1"]],
            [["S-T", "20260528135900", "20260528143000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0
