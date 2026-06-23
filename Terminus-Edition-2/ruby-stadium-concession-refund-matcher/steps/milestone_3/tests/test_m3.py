"""Verifier tests for realtime stadium concession refund reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "folios.csv"
ACTION = APP / "data" / "refunds.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "concession_refund_report.csv"
SUMMARY = APP / "out" / "concession_refund_summary.txt"


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
    write_csv(SOURCE, ["folio_id", "fan_id", "property_id", "item_type", "amount", "sale_ts", "status", "stand"], source)
    write_csv(ACTION, ["refund_id", "folio_id", "fan_id", "property_id", "item_type", "amount", "refund_ts", "reason", "stand"], action)
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


class TestMilestone3:
    def test_all_gates_consumption_and_positive_unmatched_totals(self):
        """Every identity, status, timestamp, reason, and consumption gate should reject bad candidates."""
        build_program()
        write_inputs(
            [
                ["SRC-GATE-1", "PARTY-1", "S-G", "FOOD", "10", "20260528140000", "SOLD", "L1"],
                ["SRC-GATE-2", "PARTY-2", "S-G", "FOOD", "20", "20260528140100", "BAD", "L2"],
                ["SRC-GATE-3", "PARTY-3", "S-G", "DRINK", "30", "20260528140200", "SOLD", "L3"],
                ["SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140300", "SOLD", "L4"],
            ],
            [
                ["ACT-A", "SRC-GATE-1", "PARTY-1", "S-G", "FOOD", "10", "20260528140500", "SPOIL", "L1"],
                ["ACT-B", "SRC-GATE-1", "PARTY-1", "S-G", "FOOD", "10", "20260528140600", "SPOIL", "L1"],
                ["ACT-C", "SRC-GATE-2", "PARTY-2", "S-G", "FOOD", "20", "20260528140700", "SPOIL", "L2"],
                ["ACT-D", "SRC-GATE-3", "PARTY-X", "S-G", "DRINK", "30", "20260528140700", "DUP", "L3"],
                ["ACT-E", "SRC-GATE-3", "PARTY-3", "S-G", "DRINK", "31", "20260528140700", "DUP", "L3"],
                ["ACT-F", "SRC-GATE-3", "PARTY-3", "S-G", "DRINK", "30", "20260528135959", "DUP", "L3"],
                ["ACT-G", "SRC-GATE-3", "PARTY-3", "S-G", "DRINK", "30", "20260528140700", "INFO", "L3"],
                ["ACT-H", "SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140700", "VOID", "L4"],
            ],
            [["S-G", "20260528135900", "20260528143000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert rows[1]["item_type"] == ""
        assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 7, "unmatched_amount": 191}

    def test_aliases_full_keys_and_canonical_output(self):
        """Aliases should match full source keys and emit canonical item_type values."""
        build_program()
        write_inputs(
            [
                ["SRC-100000001", "PARTY-1", "S-A", "FOOD", "12", "20260528120500", "SOLD", "LOC-1"],
                ["SRC-100000002", "PARTY-2", "S-A", "DRINK", "34", "20260528120600", "SOLD", "LOC-2"],
                ["SRC-100000003", "PARTY-3", "S-B", "MERCH", "56", "20260528130500", "SOLD", "LOC-3"],
            ],
            [
                ["ACT-1", "SRC-100000001", "PARTY-1", "S-A", "FD", "12", "20260528121000", "SPOIL", "LOC-1"],
                ["ACT-2", "SRC-100000002", "PARTY-2", "S-A", "DR", "34", "20260528121100", "DUP", "LOC-2"],
                ["ACT-3", "SRC-100000003", "PARTY-3", "S-B", "MR", "56", "20260528131000", "VOID", "LOC-3"],
            ],
            [["S-A", "20260528120000", "20260528123000", "OPEN"], ["S-B", "20260528130000", "20260528133000", "OPEN"]],
        )
        rows, summary = run_program()
        assert REPORT.read_text().splitlines()[0] == "refund_id,folio_id,fan_id,property_id,item_type,amount,reason,status"
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["item_type"] for row in rows] == ["FOOD", "DRINK", "MERCH"]
        assert summary == {"matched_count": 3, "matched_amount": 102, "unmatched_count": 0, "unmatched_amount": 0}

    def test_window_state_malformed_times_latest_candidate_and_order(self):
        """Window eligibility, malformed times, latest candidate selection, order, and blank unmatched item_type should hold."""
        build_program()
        write_inputs(
            [
                ["SRC-WIN-1", "PARTY-1", "S-O", "FOOD", "1", "20260528150000", "SOLD", "L1"],
                ["SRC-WIN-2", "PARTY-2", "S-C", "FOOD", "2", "20260528150000", "SOLD", "L2"],
                ["SRC-WIN-3", "PARTY-3", "S-M", "DRINK", "3", "bad-time", "SOLD", "L3"],
                ["SRC-DUPE", "PARTY-4", "S-O", "MERCH", "4", "20260528150100", "SOLD", "L4"],
                ["SRC-DUPE", "PARTY-4", "S-O", "MERCH", "4", "20260528150200", "SOLD", "L4"],
            ],
            [
                ["ACT-1", "SRC-WIN-1", "PARTY-1", "S-O", "FOOD", "1", "20260528150500", "SPOIL", "L1"],
                ["ACT-2", "SRC-WIN-2", "PARTY-2", "S-C", "FOOD", "2", "20260528150500", "SPOIL", "L2"],
                ["ACT-3", "SRC-WIN-3", "PARTY-3", "S-M", "DRINK", "3", "20260528150500", "DUP", "L3"],
                ["ACT-4", "SRC-DUPE", "PARTY-4", "S-O", "MERCH", "4", "20260528150600", "VOID", "L4"],
            ],
            [["S-O", "20260528145900", "20260528153000", "OPEN"], ["S-C", "20260528145900", "20260528153000", "CLOS"], ["S-M", "bad-time", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["refund_id"] for row in rows] == ["ACT-1", "ACT-2", "ACT-3", "ACT-4"]
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert [row["item_type"] for row in rows] == ["FOOD", "", "", "MERCH"]
        assert summary == {"matched_count": 2, "matched_amount": 5, "unmatched_count": 2, "unmatched_amount": 5}

    def test_latest_sale_ts_wins_with_distinct_amounts(self):
        """Latest sale_ts must win when multiple unused rows qualify; distinct amounts block first-fit."""
        build_program()
        write_inputs(
            [
                ["SRC-L1", "PARTY-1", "S-W", "FOOD", "500", "20260528160000", "SOLD", "L1"],
                ["SRC-L2", "PARTY-1", "S-W", "FOOD", "800", "20260528170000", "SOLD", "L1"],
                ["SRC-L3", "PARTY-1", "S-W", "FOOD", "1200", "20260528180000", "SOLD", "L1"],
            ],
            [
                ["ACT-L1", "SRC-L3", "PARTY-1", "S-W", "FOOD", "1200", "20260528180500", "SPOIL", "L1"],
                ["ACT-L2", "SRC-L1", "PARTY-1", "S-W", "FOOD", "500", "20260528161000", "DUP", "L1"],
            ],
            [["S-W", "20260528150000", "20260528190000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert summary == {
            "matched_count": 2,
            "matched_amount": 1700,
            "unmatched_count": 0,
            "unmatched_amount": 0,
        }

    def test_refund_after_window_close_is_unmatched(self):
        """A correction timestamp after the property window close must stay UNMATCHED."""
        build_program()
        write_inputs(
            [["SRC-CLOSE", "PARTY-1", "S-C", "FOOD", "60", "20260528150000", "SOLD", "L1"]],
            [["ACT-CLOSE", "SRC-CLOSE", "PARTY-1", "S-C", "FOOD", "60", "20260528153100", "SPOIL", "L1"]],
            [["S-C", "20260528145900", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["item_type"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount": 0,
            "unmatched_count": 1,
            "unmatched_amount": 60,
        }

    def test_equal_sale_ts_tie_uses_earliest_source_row(self):
        """When sale_ts ties on duplicate qualifying rows, consume earliest source input row first."""
        build_program()
        write_inputs(
            [
                ["SRC-TIE", "PARTY-1", "S-W", "FOOD", "500", "20260528160000", "SOLD", "L1"],
                ["SRC-TIE", "PARTY-1", "S-W", "FOOD", "500", "20260528160000", "SOLD", "L1"],
            ],
            [
                ["ACT-TIE-1", "SRC-TIE", "PARTY-1", "S-W", "FOOD", "500", "20260528160500", "SPOIL", "L1"],
                ["ACT-TIE-2", "SRC-TIE", "PARTY-1", "S-W", "FOOD", "500", "20260528160600", "DUP", "L1"],
            ],
            [["S-W", "20260528150000", "20260528190000", "OPEN"]],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["item_type"] for row in rows] == ["FOOD", "FOOD"]
        assert summary == {
            "matched_count": 2,
            "matched_amount": 1000,
            "unmatched_count": 0,
            "unmatched_amount": 0,
        }
