"""Milestone 2 tests for legacy claim denial reason aliases."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
SRC = APP / "src" / "claim_rollup.cbl"
BIN = APP / "build" / "claim_rollup"
CLAIMS = APP / "data" / "claims.dat"
ADJUSTMENTS = APP / "data" / "adjustments.dat"
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


def write_inputs(claim_lines, adjustment_lines):
    """Write fixed-width claim and adjustment files for a test scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    CLAIMS.write_text("\n".join(claim_lines) + "\n")
    ADJUSTMENTS.write_text("\n".join(adjustment_lines) + "\n")
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


def test_legacy_reason_aliases_match_and_report_canonical_reasons():
    """BIL, AUN, and CLN claim reasons should match as COB, AUT, and NEC."""
    compile_program()
    write_inputs(
        [
            "CCLM810000001BIL0000001500MBR08101D",
            "CCLM810000002AUN0000002500MBR08102D",
            "CCLM810000003CLN0000003500MBR08103D",
            "CCLM810000004MED0000004500MBR08104D",
        ],
        [
            "ACLM8100000010000001500MBR08101",
            "ACLM8100000020000002500MBR08102",
            "ACLM8100000030000003500MBR08103",
            "ACLM8100000040000004500MBR08104",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "MATCHED"]
    assert [row["member_id"] for row in rows] == ["MBR08101", "MBR08102", "MBR08103", "MBR08104"]
    assert [row["reason"] for row in rows] == ["COB", "AUT", "NEC", "MED"]
    assert [row["amount_cents"] for row in rows] == [
        "0000001500",
        "0000002500",
        "0000003500",
        "0000004500",
    ]
    assert summary["matched_count"] == 4
    assert summary["matched_amount_cents"] == 12000
    assert summary["unmatched_count"] == 0


def test_direct_cob_and_full_claim_id_matching_survive_alias_extension():
    """Direct COB claims must match, and the full 12-character claim id must be used."""
    compile_program()
    write_inputs(
        [
            "CCLM8300000A1MED0000005000MBR08301D",
            "CCLM8300000A2COB0000005000MBR08301D",
        ],
        [
            "ACLM8300000A20000005000MBR08301",
        ],
    )
    rows, summary = run_program()

    assert [row["claim_id"] for row in rows] == ["CLM8300000A2"]
    assert [row["member_id"] for row in rows] == ["MBR08301"]
    assert [row["status"] for row in rows] == ["MATCHED"]
    assert [row["reason"] for row in rows] == ["COB"]
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 0


def test_unknown_reason_stays_unmatched_and_duplicate_alias_does_not_reuse_claim():
    """Unknown reasons should not match, and duplicate alias adjustments cannot reuse a claim."""
    compile_program()
    write_inputs(
        [
            "CCLM820000001BIL0000006000MBR08201D",
            "CCLM820000002XYZ0000007000MBR08202D",
        ],
        [
            "ACLM8200000010000006000MBR08201",
            "ACLM8200000010000006000MBR08201",
            "ACLM8200000020000007000MBR08202",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "claim_id,member_id,reason,amount_cents,status"
    assert [row["claim_id"] for row in rows] == ["CLM820000001", "CLM820000001", "CLM820000002"]
    assert [row["member_id"] for row in rows] == ["MBR08201", "MBR08201", "MBR08202"]
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED"]
    assert [row["reason"] for row in rows] == ["COB", "", ""]
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 6000
    assert summary["unmatched_count"] == 2
    assert summary["unmatched_amount_cents"] == 13000


def test_duplicate_claim_rows_are_consumed_individually_not_by_claim_id():
    """Two eligible claim rows with the same id may each be consumed once in input order."""
    compile_program()
    write_inputs(
        [
            "CCLM840000001BIL0000001400MBR08401D",
            "CCLM840000001MED0000001400MBR08401D",
            "CCLM840000002CLN0000001600MBR08402D",
        ],
        [
            "ACLM8400000010000001400MBR08401",
            "ACLM8400000010000001400MBR08401",
            "ACLM8400000010000001400MBR08401",
            "ACLM8400000020000001600MBR08402",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
    assert [row["reason"] for row in rows] == ["COB", "MED", "", "NEC"]
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
