"""Milestone 1 tests for core ACH reversal matching."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
SRC = APP / "src" / "ach_reconcile.cbl"
BIN = APP / "build" / "ach_reconcile"
SETTLEMENT = APP / "data" / "settlement.dat"
REVERSALS = APP / "data" / "reversals.dat"
REPORT = APP / "out" / "reversal_report.csv"
SUMMARY = APP / "out" / "reversal_summary.txt"


class TestMilestone1:
    """Verify core matching, sign, and report schema behavior."""

    def compile_program(self):
        """Compile the COBOL reconciler for a scenario."""
        BIN.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["cobc", "-x", "-free", "-O2", "-o", str(BIN), str(SRC)], check=True, cwd=APP, timeout=60)

    def write_inputs(self, settlement_lines, reversal_lines):
        """Write settlement and reversal records for one scenario."""
        REPORT.parent.mkdir(parents=True, exist_ok=True)
        SETTLEMENT.write_text("\n".join(settlement_lines) + "\n")
        REVERSALS.write_text("\n".join(reversal_lines) + "\n")
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

    def test_web_and_tel_reversals_match_with_positive_totals(self):
        """WEB and TEL settlements should match eligible reversals and count positive cents."""
        self.compile_program()
        self.write_inputs(
            [
                "S813000000000101WEB0000020100C20260402COMP1001P",
                "S813000000000102TEL0000004500C20260402COMP1002P",
            ],
            [
                "R813000000000101R02000002010020260403COMP1001",
                "R813000000000102R10000000450020260403COMP1002",
            ],
        )
        rows, summary = self.run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["company"] for row in rows] == ["COMP1001", "COMP1002"]
        assert [row["sec"] for row in rows] == ["WEB", "TEL"]
        assert [row["reason"] for row in rows] == ["R02", "R10"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 24600
        assert summary["unmatched_count"] == 0

    def test_full_trace_reason_company_direction_status_and_sec_all_gate_matching(self):
        """Full trace, company, reason, direction, status, and SEC code should all gate matching."""
        self.compile_program()
        self.write_inputs(
            [
                "S555000000000111PPD0000003300C20260402COMP2001P",
                "S555000000000112PPD0000003300C20260402COMP2001P",
                "S700000000000001CCD0000001000D20260402COMP3001P",
                "S700000000000002PPD0000002000C20260402COMP3002R",
                "S700000000000003CTX0000003000C20260402COMP3003P",
                "S700000000000004CCD0000004000C20260402COMP3004P",
                "S581300000000201PPD0000005000C20260402COMP5001P",
                "S600000000000001PPD0000001000C20260402COMP6001P",
            ],
            [
                "R555000000000113R01000000330020260403COMP2001",
                "R555000000000112R01000000330020260403COMP2001",
                "R700000000000001R02000000100020260403COMP3001",
                "R700000000000002R03000000200020260403COMP3002",
                "R700000000000003R01000000300020260403COMP3003",
                "R700000000000004R06000000400020260403COMP3004",
                "R700000000000004R03000000400020260403COMP3004",
                "R581300000000201R01000000990020260403COMP5001",
                "R600000000000001R01000000100020260403COMP6099",
            ],
        )
        rows, summary = self.run_program()

        assert [row["status"] for row in rows] == [
            "UNMATCHED",
            "MATCHED",
            "UNMATCHED",
            "UNMATCHED",
            "UNMATCHED",
            "UNMATCHED",
            "MATCHED",
            "UNMATCHED",
            "UNMATCHED",
        ]
        assert rows[0]["sec"] == ""
        assert rows[6]["sec"] == "CCD"
        assert rows[7]["company"] == "COMP5001"
        assert rows[7]["amount_cents"] == "0000009900"
        assert rows[8]["company"] == "COMP6099"
        assert rows[8]["reason"] == "R01"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 7300
        assert summary["unmatched_count"] == 7
        assert summary["unmatched_amount_cents"] == 24200

    def test_report_schema_order_and_zero_padded_amounts(self):
        """Report rows should keep schema, reversal order, and zero-padded amounts."""
        self.compile_program()
        self.write_inputs(
            [
                "S900000000000001PPD0000000100C20260402COMP9001P",
                "S900000000000002WEB0000000200C20260402COMP9002P",
                "S900000000000003CCD0000000300C20260402COMP9003P",
            ],
            [
                "R900000000000003R03000000030020260403COMP9003",
                "R900000000000001R01000000010020260403COMP9001",
                "R900000000000002R02000000020020260403COMP9002",
            ],
        )
        rows, summary = self.run_program()

        assert REPORT.read_text().splitlines()[0] == "trace,company,sec,amount_cents,reason,status"
        assert [row["trace"] for row in rows] == [
            "900000000000003",
            "900000000000001",
            "900000000000002",
        ]
        assert [row["amount_cents"] for row in rows] == ["0000000300", "0000000100", "0000000200"]
        assert [row["company"] for row in rows] == ["COMP9003", "COMP9001", "COMP9002"]
        assert [row["reason"] for row in rows] == ["R03", "R01", "R02"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 600
