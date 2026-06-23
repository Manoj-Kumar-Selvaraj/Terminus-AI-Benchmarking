"""Verifier tests for the COBOL claim denial rollup batch."""

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


def test_cob_denial_matches_and_counts_positive_amount():
    """COB denials should match denied claims and add positive cents to matched totals."""
    compile_program()
    write_inputs(
        [
            "CCLM202604101MED0000012500MBR01001D",
            "CCLM202604102COB0000008800MBR01002D",
        ],
        [
            "ACLM2026041010000012500MBR01001",
            "ACLM2026041020000008800MBR01002",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["reason"] == "COB"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 21300
    assert summary["unmatched_count"] == 0


def test_claim_id_match_uses_all_12_characters():
    """An adjustment must not match a claim id that differs only in the final characters."""
    compile_program()
    write_inputs(
        [
            "CCLM777770001MED0000003300MBR02001D",
            "CCLM777770002MED0000003300MBR02001D",
        ],
        [
            "ACLM7777700030000003300MBR02001",
            "ACLM7777700020000003300MBR02001",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["reason"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_member_amount_status_and_reason_all_gate_matching():
    """Member id, amount, denied status, and allowed reason must all be satisfied."""
    compile_program()
    write_inputs(
        [
            "CCLM300000001MED0000001000MBR03001D",
            "CCLM300000002NEC0000002000MBR03002D",
            "CCLM300000003AUT0000003000MBR03003P",
            "CCLM300000004EXP0000004000MBR03004D",
            "CCLM300000005AUT0000005000MBR03005D",
        ],
        [
            "ACLM3000000010000001000MBR09999",
            "ACLM3000000020000002100MBR03002",
            "ACLM3000000030000003000MBR03003",
            "ACLM3000000040000004000MBR03004",
            "ACLM3000000050000005000MBR03005",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["reason"] == "AUT"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_adjustments_do_not_reuse_consumed_claim():
    """Only the earliest eligible adjustment may consume a matching denied claim."""
    compile_program()
    write_inputs(
        [
            "CCLM555500001COB0000007200MBR05551D",
            "CCLM555500002NEC0000004100MBR05552D",
        ],
        [
            "ACLM5555000010000007200MBR05551",
            "ACLM5555000010000007200MBR05551",
            "ACLM5555000020000004100MBR05552",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["reason"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 11300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7200


def test_report_schema_and_adjustment_input_order_are_stable():
    """The report should use the required schema and preserve adjustment input order."""
    compile_program()
    write_inputs(
        [
            "CCLM900000001MED0000000100MBR09001D",
            "CCLM900000002COB0000000200MBR09002D",
            "CCLM900000003AUT0000000300MBR09003D",
        ],
        [
            "ACLM9000000030000000300MBR09003",
            "ACLM9000000010000000100MBR09001",
            "ACLM9000000020000000200MBR09002",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "claim_id,member_id,reason,amount_cents,status"
    assert [row["claim_id"] for row in rows] == ["CLM900000003", "CLM900000001", "CLM900000002"]
    assert [row["member_id"] for row in rows] == ["MBR09003", "MBR09001", "MBR09002"]
    assert [row["amount_cents"] for row in rows] == ["0000000300", "0000000100", "0000000200"]
    assert summary["matched_count"] == 3
    assert summary["matched_amount_cents"] == 600
