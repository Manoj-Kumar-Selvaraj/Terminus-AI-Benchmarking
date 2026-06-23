# ruff: noqa: E501
"""Tests for account-scoped fiscal-window adjudication."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
POLICIES = APP / "data" / "policies.psv"
ADJUSTMENTS = APP / "data" / "adjustments.psv"
WINDOWS = APP / "config" / "fiscal_windows.psv"
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
WINDOW_HEADER = ["account_no", "open_ts", "close_ts", "state"]


def write_psv(path, headers, rows):
    """Write a pipe-separated fixture."""
    path.write_text(
        "|".join(headers) + "\n" + "\n".join("|".join(row) for row in rows) + "\n"
    )


def write_rules():
    """Install fiscal state, opcode, and alias rules for each scenario."""
    RULES.write_text(
        "DCL ELIGIBLE_STATE CHAR(12) INIT('READY');\n"
        "DCL OPEN_FISCAL_STATE CHAR(8) INIT('ACTIVE');\n"
        "DCL REASON_1 CHAR(12) INIT('OK');\n"
        "DCL REASON_2 CHAR(12) INIT('WATCH');\n"
        "DCL REASON_3 CHAR(12) INIT('DONE');\n"
        "DCL ALIAS_1 CHAR(20) INIT('F=>FED');\n"
        "DCL ALIAS_2 CHAR(20) INIT('A=>ACH');\n"
        "DCL ALIAS_3 CHAR(20) INIT('S=>SWIFT');\n"
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


class TestMilestone3:
    def test_both_timestamps_must_be_inside_same_account_window(self):
        """Valid rows require covered ingest and adjustment timestamps for the same account."""
        write_rules()
        write_psv(
            POLICIES,
            POLICY_HEADER,
            [
                ["P0", "100", "10", "F", "NYC", "20260612115900", "READY", "TM"],
                ["P1", "100", "10", "F", "NYC", "20260612120000", "READY", "TM"],
                ["P2", "200", "20", "A", "BOS", "20260612110000", "READY", "TM"],
                ["P3", "300", "30", "S", "SEA", "20260612120000", "READY", "TM"],
            ],
        )
        write_psv(
            ADJUSTMENTS,
            ADJUSTMENT_HEADER,
            [
                ["C0", "P0", "100", "10", "FED", "20260612123000", "OK", "NYC"],
                ["C1", "P1", "100", "10", "FED", "20260612120500", "OK", "NYC"],
                ["C2", "P2", "200", "20", "ACH", "20260612120500", "OK", "BOS"],
                ["C3", "P3", "300", "30", "SWIFT", "20260612130000", "OK", "SEA"],
            ],
        )
        write_psv(
            WINDOWS,
            WINDOW_HEADER,
            [
                ["100", "20260612115900", "20260612123000", "active"],
                ["200", "20260612115900", "20260612123000", "ACTIVE"],
                ["300", "20260612115900", "20260612123000", "ACTIVE"],
            ],
        )

        rows, summary = run_batch()

        assert [row["status"] for row in rows] == ["VALID", "VALID", "INVALID", "INVALID"]
        assert [row["risk_code"] for row in rows] == ["FED", "FED", "", ""]
        assert summary["valid_amount_cents"] == 20
        assert summary["invalid_amount_cents"] == 50

    def test_wrong_account_closed_and_malformed_windows_are_ineligible(self):
        """Wrong-account, non-open, malformed, and non-14-digit timestamps cannot authorize a match."""
        write_rules()
        write_psv(
            POLICIES,
            POLICY_HEADER,
            [
                ["P4", "400", "40", "FED", "NYC", "20260612120000", "READY", "TM"],
                ["P5", "500", "50", "FED", "NYC", "bad", "READY", "TM"],
                ["P13", "600", "60", "FED", "NYC", "2026061212000", "READY", "TM"],
                ["P15", "700", "70", "FED", "NYC", "20260612120000", "READY", "TM"],
            ],
        )
        write_psv(
            ADJUSTMENTS,
            ADJUSTMENT_HEADER,
            [
                ["C4", "P4", "400", "40", "FED", "20260612120500", "OK", "NYC"],
                ["C5", "P5", "500", "50", "FED", "20260612120500", "OK", "NYC"],
                ["C13", "P13", "600", "60", "FED", "20260612120500", "OK", "NYC"],
                ["C15", "P15", "700", "70", "FED", "202606121200000", "OK", "NYC"],
            ],
        )
        write_psv(
            WINDOWS,
            WINDOW_HEADER,
            [
                ["999", "20260612115900", "20260612123000", "ACTIVE"],
                ["400", "20260612115900", "20260612123000", "CLOSED"],
                ["500", "not-a-time", "20260612123000", "ACTIVE"],
                ["600", "20260612115900", "20260612123000", "ACTIVE"],
                ["700", "20260612115900", "20260612123000", "ACTIVE"],
            ],
        )

        rows, summary = run_batch()

        assert [row["status"] for row in rows] == ["INVALID", "INVALID", "INVALID", "INVALID"]
        assert summary["invalid_count"] == 4

    def test_latest_ingest_is_consumed_before_an_earlier_candidate(self):
        """Latest eligible ingest wins first so an earlier adjustment can consume the older row."""
        write_rules()
        write_psv(
            POLICIES,
            POLICY_HEADER,
            [
                ["PX", "600", "60", "FED", "NYC", "20260612120500", "READY", "TM"],
                ["PX", "600", "60", "FED", "NYC", "20260612122000", "READY", "TM"],
            ],
        )
        write_psv(
            ADJUSTMENTS,
            ADJUSTMENT_HEADER,
            [
                ["LATE", "PX", "600", "60", "FED", "20260612122500", "OK", "NYC"],
                ["EARLY", "PX", "600", "60", "FED", "20260612121000", "OK", "NYC"],
            ],
        )
        write_psv(
            WINDOWS,
            WINDOW_HEADER,
            [["600", "20260612120000", "20260612123000", "ACTIVE"]],
        )

        rows, summary = run_batch()

        assert [row["status"] for row in rows] == ["VALID", "VALID"]
        assert [row["claim_id"] for row in rows] == ["LATE", "EARLY"]
        assert summary["valid_count"] == 2

    def test_policy_ingest_later_than_adjustment_is_ineligible(self):
        """Policy ingest_ts must not be later than adjustment adj_ts even inside an open window."""
        write_rules()
        write_psv(
            POLICIES,
            POLICY_HEADER,
            [
                ["P6", "600", "60", "FED", "NYC", "20260612122000", "READY", "TM"],
                ["P7", "600", "60", "FED", "NYC", "20260612120000", "READY", "TM"],
            ],
        )
        write_psv(
            ADJUSTMENTS,
            ADJUSTMENT_HEADER,
            [
                ["LATE-INGEST", "P6", "600", "60", "FED", "20260612121000", "OK", "NYC"],
                ["OK-PAIR", "P7", "600", "60", "FED", "20260612120500", "OK", "NYC"],
            ],
        )
        write_psv(
            WINDOWS,
            WINDOW_HEADER,
            [["600", "20260612115900", "20260612123000", "ACTIVE"]],
        )

        rows, summary = run_batch()

        assert [row["status"] for row in rows] == ["INVALID", "VALID"]
        assert [row["risk_code"] for row in rows] == ["", "FED"]
        assert summary == {
            "valid_count": 1,
            "valid_amount_cents": 60,
            "invalid_count": 1,
            "invalid_amount_cents": 60,
        }
