"""Milestone 4 tests for corrected ACH calendar status handling."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
SRC = APP / "src" / "ach_reconcile.cbl"
BIN = APP / "build" / "ach_reconcile"
SETTLEMENT = APP / "data" / "settlement.dat"
REVERSALS = APP / "data" / "reversals.dat"
CALENDAR = APP / "config" / "business_calendar.txt"
REPORT = APP / "out" / "reversal_report.csv"
SUMMARY = APP / "out" / "reversal_summary.txt"


class TestMilestone4:
    """Verify final calendar rows, missing dates, and open-date eligibility."""

    def compile_program(self):
        """Compile the COBOL reconciler for a scenario."""
        BIN.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["cobc", "-x", "-free", "-O2", "-o", str(BIN), str(SRC)], check=True, cwd=APP, timeout=60)

    def write_inputs(self, settlement_lines, reversal_lines, calendar_lines):
        """Write settlement, reversal, and business-calendar records for one scenario."""
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        SETTLEMENT.write_text("\n".join(settlement_lines) + "\n")
        REVERSALS.write_text("\n".join(reversal_lines) + "\n")
        CALENDAR.write_text("\n".join(calendar_lines) + "\n")
        REPORT.unlink(missing_ok=True)
        SUMMARY.unlink(missing_ok=True)

    def run_program(self):
        """Run the reconciler and parse report plus summary outputs."""
        subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
        with REPORT.open(newline="") as handle:
            rows = list(csv.DictReader(handle))
        summary = {}
        for line in SUMMARY.read_text().splitlines():
            key, value = line.split("=", 1)
            summary[key] = int(value)
        return rows, summary

    def test_last_calendar_row_wins_and_dates_must_be_open(self):
        """Duplicate calendar rows should use the final status and require open settlement/reversal dates."""
        self.compile_program()
        self.write_inputs(
            [
                "S933330000000001PPD0000000100C20260403COMP9001P",
                "S933330000000002CCD0000000200C20260406COMP9002P",
                "S933330000000003TEL0000000300C20260408COMP9003P",
                "S933330000000004WEB0000000400C20260409COMP9004P",
                "S933330000000005PPD0000000500C20260406COMP9005P",
            ],
            [
                "R933330000000001R01000000010020260406COMP9001",
                "R933330000000002R03000000020020260408COMP9002",
                "R933330000000003R10000000030020260410COMP9003",
                "R933330000000004R03000000040020260410COMP9004",
                "R933330000000005R03000000050020260411COMP9005",
            ],
            [
                "20260403 OPEN",
                "20260404 CLOSED",
                "20260405 CLOSED",
                "20260406 CLOSED",
                "20260406 OPEN",
                "20260407 OPEN",
                "20260408 OPEN",
                "20260408 CLOSED",
                "20260410 OPEN",
            ],
        )
        rows, summary = self.run_program()

        assert [row["status"] for row in rows] == [
            "MATCHED",
            "UNMATCHED",
            "UNMATCHED",
            "UNMATCHED",
            "UNMATCHED",
        ]
        assert rows[0]["sec"] == "PPD"
        assert rows[0]["amount_cents"] == "0000000100"
        assert [row["sec"] for row in rows[1:]] == ["", "", "", ""]
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 100
        assert summary["unmatched_count"] == 4
        assert summary["unmatched_amount_cents"] == 1400

    def test_duplicate_calendar_corrections_feed_window_and_latest_settlement_choice(self):
        """Calendar corrections should affect window counts before choosing the latest eligible settlement."""
        self.compile_program()
        self.write_inputs(
            [
                "S944440000000001PPD0000000700C20260401COMP9101P",
                "S944440000000001TEL0000000700C20260403COMP9101P",
                "S944440000000002CCD0000000800C20260403COMP9102P",
                "S944440000000002WEB0000000800C20260403COMP9102P",
            ],
            [
                "R944440000000001R03000000070020260407COMP9101",
                "R944440000000002R10000000080020260407COMP9102",
            ],
            [
                "20260401 OPEN",
                "20260402 OPEN",
                "20260403 OPEN",
                "20260404 CLOSED",
                "20260405 CLOSED",
                "20260406 OPEN",
                "20260406 CLOSED",
                "20260407 OPEN",
            ],
        )
        rows, summary = self.run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[0]["sec"] == "TEL"
        assert rows[1]["sec"] == "CCD"
        assert rows[1]["reason"] == "R10"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 1500
        assert summary["unmatched_count"] == 0

    def test_calendar_status_is_case_insensitive_and_missing_dates_block_matches(self):
        """Lowercase open dates should apply, while missing settlement/reversal dates are not open."""
        self.compile_program()
        self.write_inputs(
            [
                "S955550000000001WEB0000000300C20260401COMP9201P",
                "S955550000000002PPD0000000400C20260402COMP9202P",
                "S955550000000003CCD0000000500C20260404COMP9203P",
            ],
            [
                "R955550000000001R03000000030020260403COMP9201",
                "R955550000000002R01000000040020260403COMP9202",
                "R955550000000003R03000000050020260405COMP9203",
            ],
            [
                "20260401 open",
                "20260402 Open",
                "20260403 OPEN",
                "20260404 CLOSED",
            ],
        )
        rows, summary = self.run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["sec"] for row in rows] == ["WEB", "PPD", ""]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500
