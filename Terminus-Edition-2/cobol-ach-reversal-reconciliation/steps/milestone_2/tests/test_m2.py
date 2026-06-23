"""Milestone 2 tests for settlement consumption."""

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


class TestMilestone2:
    """Verify that matched settlements are consumed exactly once."""

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

    def test_duplicate_reversals_do_not_reuse_one_settlement(self):
        """Only the earliest reversal should consume a single matching settlement."""
        self.compile_program()
        self.write_inputs(
            [
                "S812340000000001WEB0000000700C20260402COMP5001P",
                "S812340000000002TEL0000000800C20260402COMP5002P",
            ],
            [
                "R812340000000001R01000000070020260403COMP5001",
                "R812340000000001R01000000070020260403COMP5001",
                "R812340000000002R10000000080020260403COMP5002",
            ],
        )
        rows, summary = self.run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["amount_cents"] for row in rows] == ["0000000700", "0000000700", "0000000800"]
        assert rows[1]["sec"] == ""
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 1500
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_later_duplicate_counts_as_unmatched_without_changing_order(self):
        """A duplicate in the middle of the file should stay in order and count as unmatched."""
        self.compile_program()
        self.write_inputs(
            [
                "S777770000000001PPD0000001100C20260402COMP7001P",
                "S777770000000002CCD0000002200C20260402COMP7002P",
                "S777770000000003WEB0000003300C20260402COMP7003P",
            ],
            [
                "R777770000000001R01000000110020260403COMP7001",
                "R777770000000002R02000000220020260403COMP7002",
                "R777770000000001R01000000110020260403COMP7001",
                "R777770000000003R03000000330020260403COMP7003",
            ],
        )
        rows, summary = self.run_program()

        assert [row["trace"] for row in rows] == [
            "777770000000001",
            "777770000000002",
            "777770000000001",
            "777770000000003",
        ]
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["amount_cents"] for row in rows] == [
            "0000001100",
            "0000002200",
            "0000001100",
            "0000003300",
        ]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 6600
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1100

    def test_duplicate_settlement_rows_are_consumed_individually_not_by_trace(self):
        """Two eligible settlement rows with the same trace may each be consumed once."""
        self.compile_program()
        self.write_inputs(
            [
                "S888880000000001PPD0000001400C20260402COMP8801P",
                "S888880000000001WEB0000001400C20260402COMP8801P",
                "S888880000000002CCD0000001600C20260402COMP8802P",
            ],
            [
                "R888880000000001R01000000140020260403COMP8801",
                "R888880000000001R01000000140020260403COMP8801",
                "R888880000000001R01000000140020260403COMP8801",
                "R888880000000002R02000000160020260403COMP8802",
            ],
        )
        rows, summary = self.run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["sec"] for row in rows] == ["PPD", "WEB", "", "CCD"]
        assert [row["amount_cents"] for row in rows] == [
            "0000001400",
            "0000001400",
            "0000001400",
            "0000001600",
        ]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 4400
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1400
