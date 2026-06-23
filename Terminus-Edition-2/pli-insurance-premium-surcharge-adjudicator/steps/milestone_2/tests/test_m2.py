# ruff: noqa: E501
"""Tests for alias-aware premium risk-code matching."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
POLICIES = APP / "data" / "policies.psv"
ADJUSTMENTS = APP / "data" / "adjustments.psv"
RULES = APP / "src" / "premium_rules.pli"
REPORT = APP / "out" / "premium_report.csv"
SUMMARY = APP / "out" / "premium_summary.txt"

POLICY_HEADER = [
    "policy_id", "account_no", "premium_cents", "risk_code",
    "branch_id", "ingest_ts", "state", "kind_code",
]
ADJUSTMENT_HEADER = [
    "claim_id", "policy_id", "account_no", "premium_cents",
    "risk_code", "adj_ts", "opcode", "branch_id",
]


def write_psv(path, headers, rows):
    """Write a pipe-separated fixture."""
    path.write_text(
        "|".join(headers) + "\n" + "\n".join("|".join(row) for row in rows) + "\n"
    )


def write_rules():
    """Install mixed-case and whitespace-bearing alias declarations."""
    RULES.write_text(
        "DCL ELIGIBLE_STATE CHAR(12) INIT('LIVE');\n"
        "DCL OPEN_FISCAL_STATE CHAR(8) INIT('OPEN');\n"
        "DCL REASON_1 CHAR(12) INIT('GO');\n"
        "DCL REASON_2 CHAR(12) INIT('CHK');\n"
        "DCL REASON_3 CHAR(12) INIT('WAIT');\n"
        "DCL ALIAS_1 CHAR(20) INIT(' f => FeD ');\n"
        "DCL ALIAS_2 CHAR(20) INIT('a=>ACH');\n"
        "DCL ALIAS_3 CHAR(20) INIT('s=>SWIFT');\n"
    )


def run_batch():
    """Run the adjudicator and parse report and summary outputs."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=30)
    with REPORT.open(newline="") as report_file:
        rows = list(csv.DictReader(report_file, delimiter="|"))
    summary = {
        key: int(value)
        for key, value in (
            line.split("=", 1) for line in SUMMARY.read_text().splitlines()
        )
    }
    return rows, summary


class TestMilestone2:
    def test_aliases_normalize_both_input_sides_and_emit_canonical_values(self):
        """Mixed-case aliases on either side compare canonically and report canonical codes."""
        write_rules()
        write_psv(
            POLICIES,
            POLICY_HEADER,
            [
                ["R-1", "991100", "99", " F ", "NYC", "20260612120000", "LIVE", "TM"],
                ["R-2", "991200", "88", "ACH", "BOS", "20260612120100", "LIVE", "TM"],
                ["R-3", "991300", "77", "s", "SEA", "20260612120200", "LIVE", "TM"],
            ],
        )
        write_psv(
            ADJUSTMENTS,
            ADJUSTMENT_HEADER,
            [
                ["C1", "R-1", "991100", "99", "fed", "20260612120500", "go", "NYC"],
                ["C2", "R-2", "991200", "88", " A ", "20260612120500", "GO", "BOS"],
                ["C3", "R-3", "991300", "77", "Swift", "20260612120500", "Go", "SEA"],
            ],
        )

        rows, summary = run_batch()

        assert [row["status"] for row in rows] == ["VALID", "VALID", "VALID"]
        assert [row["risk_code"] for row in rows] == ["FeD", "ACH", "SWIFT"]
        assert summary["valid_amount_cents"] == 264

    def test_unknown_and_cross_alias_values_remain_invalid(self):
        """Unknown or differently canonicalized risk codes do not match and stay blank."""
        write_rules()
        write_psv(
            POLICIES,
            POLICY_HEADER,
            [
                ["R-4", "991400", "66", "F", "NYC", "20260612120000", "LIVE", "TM"],
                ["R-5", "991500", "55", "UNKNOWN", "NYC", "20260612120000", "LIVE", "TM"],
            ],
        )
        write_psv(
            ADJUSTMENTS,
            ADJUSTMENT_HEADER,
            [
                ["C4", "R-4", "991400", "66", "ACH", "20260612120500", "GO", "NYC"],
                ["C5", "R-5", "991500", "55", "OTHER", "20260612120500", "GO", "NYC"],
            ],
        )

        rows, summary = run_batch()

        assert [row["status"] for row in rows] == ["INVALID", "INVALID"]
        assert [row["risk_code"] for row in rows] == ["", ""]
        assert summary == {
            "valid_count": 0,
            "valid_amount_cents": 0,
            "invalid_count": 2,
            "invalid_amount_cents": 121,
        }
