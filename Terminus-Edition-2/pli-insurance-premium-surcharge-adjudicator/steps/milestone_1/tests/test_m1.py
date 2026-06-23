# ruff: noqa: E501
"""Tests for strict premium-surcharge adjustment matching."""

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
    """Write a pipe-separated fixture with the supplied headers and rows."""
    body = "\n".join("|".join(row) for row in rows)
    path.write_text("|".join(headers) + "\n" + body + "\n")


def write_rules():
    """Install runtime rule values that differ from the shipped defaults."""
    RULES.write_text(
        "DCL ELIGIBLE_STATE CHAR(12) INIT('LIVE');\n"
        "DCL OPEN_FISCAL_STATE CHAR(8) INIT('OPEN');\n"
        "DCL REASON_1 CHAR(12) INIT('OK');\n"
        "DCL REASON_2 CHAR(12) INIT('WATCH');\n"
        "DCL REASON_3 CHAR(12) INIT('DONE');\n"
        "DCL ALIAS_1 CHAR(20) INIT('R3=>HIGH');\n"
        "DCL ALIAS_2 CHAR(20) INIT('B=>BETA');\n"
        "DCL ALIAS_3 CHAR(20) INIT('X=>XLINK');\n"
    )


def run_batch():
    """Run the adjudicator and parse both output artifacts."""
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


class TestMilestone1:
    def test_full_key_state_reason_consumption_and_totals(self):
        """All five keys, source state, opcode, and one-time consumption gate validity."""
        write_rules()
        write_psv(
            POLICIES,
            POLICY_HEADER,
            [
                ["POL-1", "991100", "10", "FED", "NYC", "20260612120000", "LIVE", "TM"],
                ["POL-2", "991200", "20", "ACH", "NYC", "20260612120100", "BAD", "TM"],
                ["POL-3", "991300", "30", "SWIFT", "BOS", "20260612120200", "LIVE", "TM"],
            ],
        )
        write_psv(
            ADJUSTMENTS,
            ADJUSTMENT_HEADER,
            [
                ["C1", "POL-1", "991100", "10", "fed", "20260612120500", "ok", "NYC"],
                ["C2", "POL-1", "991100", "10", "FED", "20260612120600", "OK", "NYC"],
                ["C3", "POL-2", "991200", "20", "ACH", "20260612120700", "OK", "NYC"],
                ["C4", "POL-3", "991300", "30", "SWIFT", "20260612120700", "Watch", "BOS"],
                ["C5", "POL-3", "991300", "31", "SWIFT", "20260612120700", "WATCH", "BOS"],
                ["C6", "POL-3", "991300", "30", "SWIFT", "20260612120700", "NOPE", "BOS"],
            ],
        )

        rows, summary = run_batch()

        assert [row["status"] for row in rows] == [
            "VALID", "INVALID", "INVALID", "VALID", "INVALID", "INVALID"
        ]
        assert [row["risk_code"] for row in rows] == ["FED", "", "", "SWIFT", "", ""]
        assert summary == {
            "valid_count": 2,
            "valid_amount_cents": 40,
            "invalid_count": 4,
            "invalid_amount_cents": 91,
        }

    def test_each_identity_field_is_required_in_full(self):
        """Prefix IDs and isolated account, amount, risk, or branch mismatches stay invalid."""
        write_rules()
        write_psv(
            POLICIES,
            POLICY_HEADER,
            [["POL-ABCDE-1", "810001", "500", "FED", "DAL", "20260612120000", "LIVE", "TM"]],
        )
        write_psv(
            ADJUSTMENTS,
            ADJUSTMENT_HEADER,
            [
                ["I1", "POL-ABCDE-2", "810001", "500", "FED", "20260612120500", "OK", "DAL"],
                ["I2", "POL-ABCDE-1", "810002", "500", "FED", "20260612120500", "OK", "DAL"],
                ["I3", "POL-ABCDE-1", "810001", "501", "FED", "20260612120500", "OK", "DAL"],
                ["I4", "POL-ABCDE-1", "810001", "500", "ACH", "20260612120500", "OK", "DAL"],
                ["I5", "POL-ABCDE-1", "810001", "500", "FED", "20260612120500", "OK", "AUS"],
            ],
        )

        rows, summary = run_batch()

        assert [row["status"] for row in rows] == ["INVALID"] * 5
        assert all(row["risk_code"] == "" for row in rows)
        assert summary["invalid_amount_cents"] == 2501

    def test_report_schema_order_and_summary_keys_are_exact(self):
        """Outputs use the documented pipe header, adjustment order, and summary keys."""
        write_rules()
        write_psv(
            POLICIES,
            POLICY_HEADER,
            [
                ["P2", "2", "20", "ACH", "B2", "20260612120000", "LIVE", "TM"],
                ["P1", "1", "10", "FED", "B1", "20260612120000", "LIVE", "TM"],
            ],
        )
        write_psv(
            ADJUSTMENTS,
            ADJUSTMENT_HEADER,
            [
                ["SECOND", "P1", "1", "10", "FED", "20260612120500", "OK", "B1"],
                ["FIRST", "P2", "2", "20", "ACH", "20260612120500", "OK", "B2"],
            ],
        )

        rows, summary = run_batch()

        assert REPORT.read_text().splitlines()[0] == (
            "claim_id|policy_id|account_no|branch_id|risk_code|premium_cents|opcode|status"
        )
        assert [row["claim_id"] for row in rows] == ["SECOND", "FIRST"]
        assert list(summary) == [
            "valid_count", "valid_amount_cents", "invalid_count", "invalid_amount_cents"
        ]

    def test_equal_ingest_tie_uses_file_order_and_consumes_physical_rows(self):
        """Equal timestamps select the earliest physical row before consuming the next row."""
        write_rules()
        write_psv(
            POLICIES,
            POLICY_HEADER,
            [
                ["PX", "600", "60", "FeD", "NYC", "20260612122000", "LIVE", "TM"],
                ["PX", "600", "60", "FED", "NYC", "20260612122000", "LIVE", "TM"],
            ],
        )
        write_psv(
            ADJUSTMENTS,
            ADJUSTMENT_HEADER,
            [
                ["FIRST", "PX", "600", "60", "FED", "20260612122500", "OK", "NYC"],
                ["SECOND", "PX", "600", "60", "FED", "20260612122500", "OK", "NYC"],
            ],
        )

        rows, summary = run_batch()

        assert [row["status"] for row in rows] == ["VALID", "VALID"]
        assert [row["risk_code"] for row in rows] == ["FeD", "FED"]
        assert summary == {
            "valid_count": 2,
            "valid_amount_cents": 120,
            "invalid_count": 0,
            "invalid_amount_cents": 0,
        }

    def test_latest_ingest_ts_wins_when_multiple_policies_qualify(self):
        """Latest ingest_ts selects the newer policy row so the reported risk_code differs."""
        write_rules()
        write_psv(
            POLICIES,
            POLICY_HEADER,
            [
                ["PX", "700", "70", "FED", "NYC", "20260612120500", "LIVE", "TM"],
                ["PX", "700", "70", "BETA", "NYC", "20260612122000", "LIVE", "TM"],
            ],
        )
        write_psv(
            ADJUSTMENTS,
            ADJUSTMENT_HEADER,
            [
                ["LATE", "PX", "700", "70", "beta", "20260612122500", "OK", "NYC"],
                ["EARLY", "PX", "700", "70", "fed", "20260612121000", "OK", "NYC"],
            ],
        )

        rows, summary = run_batch()

        assert [row["status"] for row in rows] == ["VALID", "VALID"]
        assert [row["claim_id"] for row in rows] == ["LATE", "EARLY"]
        assert [row["risk_code"] for row in rows] == ["BETA", "FED"]
        assert summary["valid_count"] == 2
