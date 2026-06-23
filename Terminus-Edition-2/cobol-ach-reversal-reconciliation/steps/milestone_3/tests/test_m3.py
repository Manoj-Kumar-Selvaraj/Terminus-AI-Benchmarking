"""Milestone 3 tests for ACH business-calendar return windows."""

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


class TestMilestone3:
    """Verify business-day windows and latest eligible settlement selection."""

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

    def test_business_days_ignore_closed_dates_and_pick_latest_eligible_settlement(self):
        """Closed dates should not count, and the latest eligible settlement date should win."""
        self.compile_program()
        self.write_inputs(
            [
                "S811110000000001PPD0000000100C20260401COMP6001P",
                "S811110000000001PPD0000000100C20260403COMP6001P",
                "S811110000000002CCD0000000200C20260402COMP6002P",
                "S811110000000003TEL0000000300C20260402COMP6003P",
                "S811110000000004WEB0000000400C20260406COMP6004P",
                "S811110000000005PPD0000000500C20260403COMP6005P",
                "S811110000000006CCD0000000600C20260403COMP6006P",
                "S811110000000007TEL0000000700C20260403COMP6007P",
                "S811110000000008PPD0000000800C20260402COMP6008P",
                "S811110000000008CCD0000000800C20260403COMP6008P",
                "S811110000000009PPD0000000900C20260403COMP6009P",
                "S811110000000010CCD0000001000C20260403COMP6010P",
                "S811110000000011PPD0000001100C20260407COMP6011P",
                "S811110000000012PPD0000001200C20260403COMP6012P",
                "S811110000000012TEL0000001200C20260403COMP6012P",
            ],
            [
                "R811110000000001R01000000010020260406COMP6001",
                "R811110000000001R01000000010020260406COMP6001",
                "R811110000000002R02000000020020260406COMP6002",
                "R811110000000003R03000000030020260406COMP6003",
                "R811110000000004R10000000040020260404COMP6004",
                "R811110000000005R01000000050020260406COMP6005",
                "R811110000000006R01000000060020260407COMP6006",
                "R811110000000007R03000000070020260407COMP6007",
                "R811110000000008R03000000080020260406COMP6008",
                "R811110000000009R02000000090020260406COMP6009",
                "R811110000000010R10000000100020260407COMP6010",
                "R811110000000011R03000000110020260406COMP6011",
                "R811110000000012R03000000120020260407COMP6012",
            ],
            [
                "20260401 OPEN",
                "20260402 OPEN",
                "20260403 OPEN",
                "20260404 CLOSED",
                "20260405 CLOSED",
                "20260406 OPEN",
                "20260407 OPEN",
            ],
        )
        rows, summary = self.run_program()

        assert [row["status"] for row in rows] == [
            "MATCHED",
            "UNMATCHED",
            "UNMATCHED",
            "MATCHED",
            "UNMATCHED",
            "MATCHED",
            "UNMATCHED",
            "MATCHED",
            "MATCHED",
            "MATCHED",
            "MATCHED",
            "UNMATCHED",
            "MATCHED",
        ]
        assert rows[0]["sec"] == "PPD"
        assert rows[3]["sec"] == "TEL"
        assert rows[5]["sec"] == "PPD"
        assert rows[7]["sec"] == "TEL"
        assert rows[8]["sec"] == "CCD"
        assert rows[8]["reason"] == "R03"
        assert rows[9]["reason"] == "R02"
        assert rows[9]["status"] == "MATCHED"
        assert rows[10]["reason"] == "R10"
        assert rows[10]["status"] == "MATCHED"
        assert rows[11]["status"] == "UNMATCHED"
        assert rows[11]["sec"] == ""
        assert rows[12]["sec"] == "PPD"
        assert rows[12]["reason"] == "R03"
        assert summary["matched_count"] == 8
        assert summary["matched_amount_cents"] == 5500
        assert summary["unmatched_count"] == 5
        assert summary["unmatched_amount_cents"] == 2400

    def test_calendar_file_controls_window_outcome(self):
        """Changing closed dates in the business calendar should change return-window eligibility."""
        self.compile_program()
        self.write_inputs(
            [
                "S922220000000001WEB0000000900C20260403COMP8001P",
                "S922220000000002TEL0000001000C20260403COMP8002P",
            ],
            [
                "R922220000000001R01000000090020260406COMP8001",
                "R922220000000002R03000000100020260407COMP8002",
            ],
            [
                "20260403 OPEN",
                "20260404 CLOSED",
                "20260405 CLOSED",
                "20260406 OPEN",
                "20260407 OPEN",
            ],
        )
        rows, summary = self.run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 1900

    def test_r03_and_r10_reject_after_three_open_business_days(self):
        """R03/R10 reversals more than two open business days after settlement should be unmatched."""
        self.compile_program()
        self.write_inputs(
            [
                "S933330000000001WEB0000001300C20260401COMP9001P",
                "S933330000000002TEL0000001400C20260401COMP9002P",
            ],
            [
                "R933330000000001R03000000130020260406COMP9001",
                "R933330000000002R10000000140020260406COMP9002",
            ],
            [
                "20260401 OPEN",
                "20260402 OPEN",
                "20260403 OPEN",
                "20260404 CLOSED",
                "20260405 CLOSED",
                "20260406 OPEN",
            ],
        )
        rows, summary = self.run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert [row["sec"] for row in rows] == ["", ""]
        assert summary["matched_count"] == 0
        assert summary["matched_amount_cents"] == 0
        assert summary["unmatched_count"] == 2
        assert summary["unmatched_amount_cents"] == 2700
