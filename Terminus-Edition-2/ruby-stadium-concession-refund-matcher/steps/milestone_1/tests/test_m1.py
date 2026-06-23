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
OPEN_WINDOW = [["S-G", "20260528135900", "20260528143000", "OPEN"]]


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


class TestMilestone1:
    def test_consumption_prevents_second_match(self):
        """A consumed source row must not match a second correction."""
        build_program()
        write_inputs(
            [["SRC-CON", "PARTY-1", "S-G", "FOOD", "10", "20260528140000", "SOLD", "L1"]],
            [
                ["ACT-1", "SRC-CON", "PARTY-1", "S-G", "FOOD", "10", "20260528140500", "SPOIL", "L1"],
                ["ACT-2", "SRC-CON", "PARTY-1", "S-G", "FOOD", "10", "20260528140600", "SPOIL", "L1"],
            ],
            OPEN_WINDOW,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[1]["item_type"] == ""
        assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 1, "unmatched_amount": 10}

    def test_wrong_stand_blocks_match(self):
        """Stand must match exactly; a wrong stand keeps an otherwise valid correction unmatched."""
        build_program()
        write_inputs(
            [["SRC-STAND", "PARTY-1", "S-G", "FOOD", "25", "20260528140000", "SOLD", "L1"]],
            [["ACT-STAND", "SRC-STAND", "PARTY-1", "S-G", "FOOD", "25", "20260528140500", "SPOIL", "L9"]],
            OPEN_WINDOW,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["item_type"] == ""
        assert summary["matched_count"] == 0

    def test_item_type_mismatch_blocks_match(self):
        """Canonical item_type values must match between source and correction."""
        build_program()
        write_inputs(
            [["SRC-TYPE", "PARTY-1", "S-G", "FOOD", "30", "20260528140000", "SOLD", "L1"]],
            [["ACT-TYPE", "SRC-TYPE", "PARTY-1", "S-G", "DRINK", "30", "20260528140500", "SPOIL", "L1"]],
            OPEN_WINDOW,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["item_type"] == ""
        assert summary["unmatched_amount"] == 30

    def test_non_canonical_item_type_blocks_match(self):
        """Corrections with non-canonical item_type values must stay UNMATCHED."""
        build_program()
        write_inputs(
            [["SRC-BADTYPE", "PARTY-1", "S-G", "FOOD", "30", "20260528140000", "SOLD", "L1"]],
            [["ACT-BADTYPE", "SRC-BADTYPE", "PARTY-1", "S-G", "SNACK", "30", "20260528140500", "SPOIL", "L1"]],
            OPEN_WINDOW,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["item_type"] == ""
        assert summary["unmatched_amount"] == 30

    def test_nonnumeric_sale_ts_blocks_match(self):
        """Malformed source sale_ts values must keep corrections UNMATCHED."""
        build_program()
        write_inputs(
            [["SRC-BADTS", "PARTY-1", "S-G", "FOOD", "40", "bad-time", "SOLD", "L1"]],
            [["ACT-BADSRC", "SRC-BADTS", "PARTY-1", "S-G", "FOOD", "40", "20260528140500", "SPOIL", "L1"]],
            OPEN_WINDOW,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_nonnumeric_refund_ts_blocks_match(self):
        """Malformed correction refund_ts values must keep corrections UNMATCHED."""
        build_program()
        write_inputs(
            [["SRC-OKTS", "PARTY-2", "S-G", "DRINK", "50", "20260528140100", "SOLD", "L2"]],
            [["ACT-BADACT", "SRC-OKTS", "PARTY-2", "S-G", "DRINK", "50", "not-a-ts", "DUP", "L2"]],
            OPEN_WINDOW,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_closed_or_after_close_window_blocks_match(self):
        """Milestone 1 already requires an OPEN property window that contains sale and refund timestamps."""
        build_program()
        write_inputs(
            [
                ["SRC-CLOSED", "PARTY-3", "S-C", "FOOD", "60", "20260528140000", "SOLD", "L3"],
                ["SRC-LATE", "PARTY-4", "S-G", "DRINK", "70", "20260528140100", "SOLD", "L4"],
            ],
            [
                ["ACT-CLOSED", "SRC-CLOSED", "PARTY-3", "S-C", "FOOD", "60", "20260528140500", "SPOIL", "L3"],
                ["ACT-LATE", "SRC-LATE", "PARTY-4", "S-G", "DRINK", "70", "20260528143100", "DUP", "L4"],
            ],
            [
                ["S-C", "20260528135900", "20260528143000", "CLOSED"],
                ["S-G", "20260528135900", "20260528143000", "OPEN"],
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert rows[0]["item_type"] == ""
        assert rows[1]["item_type"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 2, "unmatched_amount": 130}

    def test_report_schema_and_positive_summary_totals(self):
        """Valid matches must emit the exact report schema and positive summary totals."""
        build_program()
        write_inputs(
            [["SRC-OK", "PARTY-1", "S-G", "FOOD", "10", "20260528140000", "SOLD", "L1"]],
            [["ACT-OK", "SRC-OK", "PARTY-1", "S-G", "FOOD", "10", "20260528140500", "SPOIL", "L1"]],
            OPEN_WINDOW,
        )
        rows, summary = run_program()
        assert REPORT.read_text().splitlines()[0] == "refund_id,folio_id,fan_id,property_id,item_type,amount,reason,status"
        assert rows[0] == {
            "refund_id": "ACT-OK",
            "folio_id": "SRC-OK",
            "fan_id": "PARTY-1",
            "property_id": "S-G",
            "item_type": "FOOD",
            "amount": "10",
            "reason": "SPOIL",
            "status": "MATCHED",
        }
        assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 0, "unmatched_amount": 0}
