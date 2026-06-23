"""Milestone 3 tests for claim cycle-calendar controls."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
SRC = APP / "src" / "claim_rollup.cbl"
BIN = APP / "build" / "claim_rollup"
CLAIMS = APP / "data" / "claims.dat"
ADJUSTMENTS = APP / "data" / "adjustments.dat"
CALENDAR = APP / "config" / "cycle_calendar.txt"
REPORT = APP / "out" / "denial_report.csv"
SUMMARY = APP / "out" / "denial_summary.txt"


def assert_cobol_binary():
    """Verify the batch still comes from the COBOL compile path."""
    compile_script = (APP / "scripts" / "compile.sh").read_text().lower()
    assert "cobc" in compile_script
    assert ".cbl" in compile_script
    assert any((APP / "src").glob("*.cbl"))
    assert (APP / "build" / "batch").read_bytes().startswith(b"\x7fELF")


def compile_program():
    """Compile the COBOL denial rollup before each scenario."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cobc", "-x", "-free", "-O2", "-o", str(BIN), str(SRC)], check=True, cwd=APP, timeout=60)


def write_inputs(claim_lines, adjustment_lines, calendar_lines):
    """Write fixed-width claim/adjustment files and cycle calendar rows."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    CLAIMS.write_text("\n".join(claim_lines) + "\n")
    ADJUSTMENTS.write_text("\n".join(adjustment_lines) + "\n")
    CALENDAR.write_text("\n".join(calendar_lines) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled rollup and return parsed report and summary data."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        summary[key] = int(value)
    return rows, summary


def test_cycle_calendar_last_row_wins_and_status_is_case_insensitive():
    """Calendar corrections and case-insensitive OPEN status should control eligibility."""
    compile_program()
    write_inputs(
        [
            "CCLM202604011BIL0000001000MBR09101D",
            "CCLM202604022AUN0000002000MBR09102D",
            "CCLM202604033CLN0000003000MBR09103D",
            "CCLM202604044MED0000004000MBR09104D",
        ],
        [
            "ACLM2026040110000001000MBR09101",
            "ACLM2026040220000002000MBR09102",
            "ACLM2026040330000003000MBR09103",
            "ACLM2026040440000004000MBR09104",
        ],
        [
            "20260401 CLOSED",
            "20260401 open",
            "20260402 OPEN",
            "20260402 CLOSED",
            "20260403 Open",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED", "UNMATCHED"]
    assert [row["reason"] for row in rows] == ["COB", "", "NEC", ""]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 4000
    assert summary["unmatched_count"] == 2
    assert summary["unmatched_amount_cents"] == 6000


def test_calendar_gate_preserves_row_consumption_and_report_order():
    """Closed duplicate rows should not consume open rows, and report order must stay by adjustment."""
    compile_program()
    write_inputs(
        [
            "CCLM202604061MED0000000500MBR09201D",
            "CCLM202604061COB0000000500MBR09201D",
            "CCLM202604052AUN0000000700MBR09202D",
            "CCLM202604063XYZ0000000900MBR09203D",
        ],
        [
            "ACLM2026040610000000500MBR09201",
            "ACLM2026040520000000700MBR09202",
            "ACLM2026040610000000500MBR09201",
            "ACLM2026040630000000900MBR09203",
        ],
        [
            "20260405 CLOSED",
            "20260406 OPEN",
        ],
    )
    rows, summary = run_program()

    assert [row["claim_id"] for row in rows] == [
        "CLM202604061",
        "CLM202604052",
        "CLM202604061",
        "CLM202604063",
    ]
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED", "UNMATCHED"]
    assert [row["reason"] for row in rows] == ["MED", "", "COB", ""]
    assert [row["amount_cents"] for row in rows] == [
        "0000000500",
        "0000000700",
        "0000000500",
        "0000000900",
    ]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 1000
    assert summary["unmatched_count"] == 2
    assert summary["unmatched_amount_cents"] == 1600
