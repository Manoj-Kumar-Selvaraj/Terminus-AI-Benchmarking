"""Verifier tests for branch-level courier service policy controls."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
SRC = APP / "src" / "parcel_credit_reconcile.cbl"
BIN = APP / "build" / "parcel_credit_reconcile"
SOURCE = APP / "data" / "shipments.dat"
ACTION = APP / "data" / "credits.dat"
CALENDAR = APP / "config" / "dispatch_calendar.txt"
POLICY = APP / "config" / "service_policy.csv"
REPORT = APP / "out" / "surcharge_credit_report.csv"
SUMMARY = APP / "out" / "surcharge_credit_summary.txt"


def src(record_id, account, category, amount, date, status="S", branch="B001"):
    """Create one fixed-width source record."""
    return f"S{record_id:<12}{account:<8}{category:<3}{amount:010d}{date}{status}{branch:<4}"


def action(record_id, account, category, amount, date, reason, branch="B001"):
    """Create one fixed-width action record."""
    return f"A{record_id:<12}{account:<8}{category:<3}{amount:010d}{date}{reason:<3}{branch:<4}"


def policy(branch, category, enabled, maximum, priority):
    """Create one service policy row."""
    return f"{branch},{category},{enabled},{maximum},{priority}"


def compile_program():
    """Compile the real COBOL program for a verifier scenario."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["cobc", "-x", "-free", "-O2", "-o", str(BIN), str(SRC)],
        check=True,
        cwd=APP,
        timeout=60,
    )


def write_inputs(source_lines, action_lines, calendar_lines, policy_lines):
    """Replace every runtime input and remove stale output artifacts."""
    SOURCE.write_text("\n".join(source_lines) + "\n")
    ACTION.write_text("\n".join(action_lines) + "\n")
    CALENDAR.write_text("\n".join(calendar_lines) + "\n")
    POLICY.write_text(
        "branch,service_tier,enabled,max_credit_cents,priority\n"
        + "\n".join(policy_lines)
        + "\n"
    )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the reconciler and parse its report and summary."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {}
    for raw in SUMMARY.read_text().splitlines():
        key, value = raw.split("=", 1)
        summary[key] = int(value)
    return rows, summary


class TestMilestone4:
    """Exercise policy filtering and deterministic wildcard selection."""

    def test_named_tiers_require_valid_enabled_covering_policy(self):
        """Disabled, missing, malformed, and under-limit policies must not enable matching."""
        compile_program()
        write_inputs(
            [
                src("CPPOL0000001", "ACCT9001", "STD", 1000, "20261001", branch="BK01"),
                src("CPPOL0000002", "ACCT9002", "NXT", 2000, "20261001", branch="BK02"),
                src("CPPOL0000003", "ACCT9003", "SAM", 3000, "20261001", branch="BK03"),
                src("CPPOL0000004", "ACCT9004", "STD", 4000, "20261001", branch="BK04"),
                src("CPPOL0000005", "ACCT9005", "NXT", 5000, "20261001", branch="BK05"),
            ],
            [
                action("CPPOL0000001", "ACCT9001", "ST", 1000, "20261002", "P03", branch="BK01"),
                action("CPPOL0000002", "ACCT9002", "NX", 2000, "20261002", "P08", branch="BK02"),
                action("CPPOL0000003", "ACCT9003", "SM", 3000, "20261002", "P21", branch="BK03"),
                action("CPPOL0000004", "ACCT9004", "ST", 4000, "20261002", "P03", branch="BK04"),
                action("CPPOL0000005", "ACCT9005", "NX", 5000, "20261002", "P08", branch="BK05"),
            ],
            ["20261001=OpEn"],
            [
                policy("BK01", "STD", "y", "1000", "10"),
                policy("BK02", "NXT", "N", "9999", "10"),
                policy("BK03", "SAM", "Y", "BAD", "10"),
                policy("BK04", "STD", "Y", "3999", "10"),
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == [
            "MATCHED",
            "UNMATCHED",
            "UNMATCHED",
            "UNMATCHED",
            "UNMATCHED",
        ]
        assert [row["service_tier"] for row in rows] == ["STD", "", "", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 4,
            "unmatched_amount_cents": 14000,
        }

    def test_any_prefers_latest_source_date_before_policy_priority(self):
        """ANY must choose the latest eligible source even when an older tier has better priority."""
        compile_program()
        write_inputs(
            [
                src("CPANY0000001", "ACCT9101", "STD", 800, "20261001", branch="BL01"),
                src("CPANY0000001", "ACCT9101", "NXT", 800, "20261005", branch="BL01"),
            ],
            [
                action("CPANY0000001", "ACCT9101", "ANY", 800, "20261010", "P03", branch="BL01"),
                action("CPANY0000001", "ACCT9101", "ANY", 800, "20261002", "P08", branch="BL01"),
            ],
            ["20261001=OPEN", "20261005=OPEN"],
            [
                policy("BL01", "STD", "Y", "9999", "1"),
                policy("BL01", "NXT", "Y", "9999", "50"),
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["service_tier"] for row in rows] == ["NXT", "STD"]
        assert summary["matched_amount_cents"] == 1600

    def test_any_ties_use_policy_priority_then_source_order(self):
        """Equal-date wildcard candidates rank by priority and then physical source order."""
        compile_program()
        write_inputs(
            [
                src("CPANY0000002", "ACCT9201", "STD", 900, "20261020", branch="BM01"),
                src("CPANY0000002", "ACCT9201", "NXT", 900, "20261020", branch="BM01"),
                src("CPANY0000002", "ACCT9201", "SAM", 900, "20261020", branch="BM01"),
            ],
            [
                action("CPANY0000002", "ACCT9201", "ANY", 900, "20261021", "P03", branch="BM01"),
                action("CPANY0000002", "ACCT9201", "ANY", 900, "20261021", "P08", branch="BM01"),
                action("CPANY0000002", "ACCT9201", "ANY", 900, "20261021", "P21", branch="BM01"),
            ],
            ["20261020=opeN"],
            [
                policy("BM01", "STD", "Y", "9999", "20"),
                policy("BM01", "NXT", "Y", "9999", "5"),
                policy("BM01", "SAM", "Y", "9999", "5"),
            ],
        )
        rows, summary = run_program()

        assert [row["service_tier"] for row in rows] == ["NXT", "SAM", "STD"]
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert summary["matched_count"] == 3

    def test_policy_and_any_do_not_bypass_existing_gates_or_consume_on_failure(self):
        """Policy eligibility cannot bypass status, calendar, identity, or one-time consumption gates."""
        compile_program()
        write_inputs(
            [
                src("CPCARRY00001", "ACCT9301", "STD", 700, "20261030", status="X", branch="BN01"),
                src("CPCARRY00001", "ACCT9301", "NXT", 700, "20261029", branch="BN01"),
            ],
            [
                action("CPCARRY00001", "ACCT9301", "ANY", 700, "20261031", "P03", branch="BN01"),
                action("CPCARRY00001", "ACCT9301", "NX", 700, "20261031", "P08", branch="BN01"),
            ],
            ["20261029=OPEn", "20261030=OPEN"],
            [
                policy("BN01", "STD", "Y", "9999", "1"),
                policy("BN01", "NXT", "Y", "9999", "10"),
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["service_tier"] for row in rows] == ["NXT", ""]
        assert summary["matched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700
