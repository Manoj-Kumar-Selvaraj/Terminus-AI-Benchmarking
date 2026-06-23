"""Milestone 4 verifier tests for reasons.csv eligibility gating."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "folios.csv"
ACTION = APP / "data" / "refunds.csv"
WINDOWS = APP / "config" / "windows.csv"
REASONS = APP / "config" / "reasons.csv"
REPORT = APP / "out" / "concession_refund_report.csv"
SUMMARY = APP / "out" / "concession_refund_summary.txt"


def write_csv(path, header, rows):
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(source, action, windows, reasons):
    write_csv(
        SOURCE,
        ["folio_id", "fan_id", "property_id", "item_type", "amount", "sale_ts", "status", "stand"],
        source,
    )
    write_csv(
        ACTION,
        ["refund_id", "folio_id", "fan_id", "property_id", "item_type", "amount", "refund_ts", "reason", "stand"],
        action,
    )
    write_csv(WINDOWS, ["property_id", "open_ts", "close_ts", "state"], windows)
    write_csv(REASONS, ["reason", "eligible"], reasons)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    subprocess.run(["ruby", "/app/app/reconcile.rb"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        summary[key] = int(value)
    return rows, summary


class TestMilestone4:
    def test_eligible_reasons_required_from_config(self):
        """Only reasons listed with eligible=Y in reasons.csv may match."""
        write_inputs(
            [
                ["M4101", "FAN1", "S-P", "FOOD", "100", "20260528140000", "SOLD", "A1"],
                ["M4102", "FAN2", "S-P", "DRINK", "200", "20260528140100", "SOLD", "A2"],
                ["M4103", "FAN3", "S-P", "MERCH", "300", "20260528140200", "SOLD", "A3"],
            ],
            [
                ["R1", "M4101", "FAN1", "S-P", "FOOD", "100", "20260528140500", "SPOIL", "A1"],
                ["R2", "M4102", "FAN2", "S-P", "DRINK", "200", "20260528140600", "DUP", "A2"],
                ["R3", "M4103", "FAN3", "S-P", "MERCH", "300", "20260528140700", "INFO", "A3"],
            ],
            [["S-P", "20260528135900", "20260528143000", "OPEN"]],
            [["SPOIL", "Y"], ["DUP", "Y"], ["VOID", "N"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["item_type"] for row in rows] == ["FOOD", "DRINK", ""]
        assert summary == {
            "matched_count": 2,
            "matched_amount": 300,
            "unmatched_count": 1,
            "unmatched_amount": 300,
        }

    def test_missing_reason_row_is_ineligible(self):
        """Reason codes absent from reasons.csv must not match."""
        write_inputs(
            [["M4201", "FAN1", "S-Q", "FOOD", "90", "20260528150000", "SOLD", "B1"]],
            [["R1", "M4201", "FAN1", "S-Q", "FOOD", "90", "20260528150500", "VOID", "B1"]],
            [["S-Q", "20260528145900", "20260528153000", "OPEN"]],
            [["SPOIL", "Y"], ["DUP", "Y"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["item_type"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount"] == 90

    def test_eligible_flag_case_insensitive_with_whitespace(self):
        """eligible=Y should be recognized case-insensitively with surrounding spaces."""
        write_inputs(
            [["M4301", "FAN1", "S-R", "FOOD", "55", "20260528160000", "SOLD", "C1"]],
            [["R1", "M4301", "FAN1", "S-R", "FOOD", "55", "20260528160500", " spoil ", "C1"]],
            [["S-R", "20260528155900", "20260528163000", "OPEN"]],
            [[" spoil ", " y "]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["item_type"] == "FOOD"
        assert summary["matched_count"] == 1

    def test_reason_policy_does_not_bypass_window_gates(self):
        """Eligible reason alone cannot bypass closed or missing windows."""
        write_inputs(
            [["M4401", "FAN1", "S-C", "FOOD", "70", "20260528170000", "SOLD", "D1"]],
            [["R1", "M4401", "FAN1", "S-C", "FOOD", "70", "20260528170500", "SPOIL", "D1"]],
            [["S-C", "20260528165900", "20260528173000", "CLOS"]],
            [["SPOIL", "Y"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_blank_reason_or_eligible_rows_are_ignored(self):
        """Blank reason codes or blank eligible values must not enable matching."""
        write_inputs(
            [
                ["M4501", "FAN1", "S-B", "FOOD", "40", "20260528180000", "SOLD", "E1"],
                ["M4502", "FAN2", "S-B", "DRINK", "50", "20260528180100", "SOLD", "E2"],
            ],
            [
                ["R1", "M4501", "FAN1", "S-B", "FOOD", "40", "20260528180500", "DUP", "E1"],
                ["R2", "M4502", "FAN2", "S-B", "DRINK", "50", "20260528180600", "DUP", "E2"],
            ],
            [["S-B", "20260528175900", "20260528183000", "OPEN"]],
            [[",Y"], ["DUP", ""], ["SPOIL", "Y"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount"] == 90
