"""Tests for the scooter ride surcharge reversal COBOL reconciler."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
SRC = APP / "src" / "scooter_surcharge_reconcile.cbl"
BIN = APP / "build" / "scooter_surcharge_reconcile"
SOURCE = APP / "data" / "ride_charges.dat"
ACTION = APP / "data" / "surcharge_reversals.dat"
CALENDAR = APP / "config" / "fleet_calendar.txt"
REASONS = APP / "config" / "reasons.csv"
CATEGORIES = APP / "config" / "categories.csv"
REPORT = APP / "out" / "scooter_surcharge_report.csv"
SUMMARY = APP / "out" / "scooter_surcharge_summary.txt"


def src(record_id, account, category, amount, date, status="Z", branch="B001"):
    """Create one fixed-width source record."""
    amount_text = f"{amount:010d}" if isinstance(amount, int) else str(amount).ljust(10)[:10]
    return f"S{record_id:<12}{account:<8}{category:<3}{amount_text}{date:<8}{status}{branch:<4}"


def action(record_id, account, category, amount, date, reason, branch="B001"):
    """Create one fixed-width action record."""
    amount_text = f"{amount:010d}" if isinstance(amount, int) else str(amount).ljust(10)[:10]
    return f"A{record_id:<12}{account:<8}{category:<3}{amount_text}{date:<8}{reason:<3}{branch:<4}"


def compile_program():
    """Compile the COBOL program for one test scenario."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cobc", "-x", "-free", "-O2", "-o", str(BIN), str(SRC)], check=True, cwd=APP, timeout=60)


def write_inputs(source_lines, action_lines, calendar_lines, reason_lines=None, category_lines=None):
    """Replace input files so outputs cannot be precomputed from shipped fixtures."""
    SOURCE.write_text("\n".join(source_lines) + "\n")
    ACTION.write_text("\n".join(action_lines) + "\n")
    CALENDAR.write_text("\n".join(calendar_lines) + "\n")
    if reason_lines is not None:
        REASONS.write_text("\n".join(reason_lines) + "\n")
    if category_lines is not None:
        CATEGORIES.write_text("\n".join(category_lines) + "\n")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)

def run_program():
    """Run the reconciler and return parsed report and summary data."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {}
    for raw in SUMMARY.read_text().splitlines():
        key, value = raw.split("=", 1)
        summary[key] = int(value)
    return rows, summary


class TestMilestone1:
    """Verify base fixed-width matching gates, output schemas, positive totals, and source consumption."""

    def test_core_keys_status_reason_and_category_match_with_positive_totals(self):
        """Canonical categories should match through full keys, status, reason, and branch gates."""
        compile_program()
        write_inputs(
            [
                src("SC0000000001", "ACCT1001", "CBD", 1200, "20260501", branch="BR01"),
                src("SC0000000002", "ACCT1002", "RES", 3400, "20260502", branch="BR02"),
                src("SC0000000003", "ACCT1003", "UNI", 5600, "20260503", branch="BR03"),
            ],
            [
                action("SC0000000001", "ACCT1001", "CBD", 1200, "20260504", "S02", branch="BR01"),
                action("SC0000000002", "ACCT1002", "RES", 3400, "20260505", "S07", branch="BR02"),
                action("SC0000000003", "ACCT1003", "UNI", 5600, "20260506", "S15", branch="BR03"),
            ],
            ["20260501=OPEN", "20260502=OPEN", "20260503=OPEN"],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "record_id,account,zone_code,amount_cents,reason,status"
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["zone_code"] for row in rows] == ["CBD", "RES", "UNI"]
        assert [row["reason"] for row in rows] == ["S02", "S07", "S15"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 10200,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_every_matching_gate_can_reject_a_candidate_without_reusing_rows(self):
        """Status, amount, account, branch, reason, date, category, and row consumption all gate matching."""
        compile_program()
        write_inputs(
            [
                src("SCGATE000001", "ACCT2001", "CBD", 1000, "20260510", branch="BA01"),
                src("SCGATE000002", "ACCT2002", "CBD", 2000, "20260510", status="X", branch="BA02"),
                src("SCGATE000003", "ACCT2003", "RES", 3000, "20260511", branch="BA03"),
                src("SCGATE000004", "ACCT2004", "BAD", 4000, "20260512", branch="BA04"),
                src("SCGATE000005", "ACCT2005", "UNI", 5000, "20260513", branch="BA05"),
            ],
            [
                action("SCGATE000001", "ACCT2001", "CBD", 1000, "20260514", "S02", branch="BA01"),
                action("SCGATE000001", "ACCT2001", "CBD", 1000, "20260514", "S02", branch="BA01"),
                action("SCGATE000002", "ACCT2002", "CBD", 2000, "20260514", "S02", branch="BA02"),
                action("SCGATE000003", "ACCT2999", "RES", 3000, "20260514", "S07", branch="BA03"),
                action("SCGATE000003", "ACCT2003", "RES", 3999, "20260514", "S07", branch="BA03"),
                action("SCGATE000003", "ACCT2003", "RES", 3000, "20260509", "S07", branch="BA03"),
                action("SCGATE000003", "ACCT2003", "RES", 3000, "20260514", "BAD", branch="BA03"),
                action("SCGATE000004", "ACCT2004", "BAD", 4000, "20260514", "S02", branch="BA04"),
                action("SCGATE000005", "ACCT2005", "UNI", 5000, "20260514", "S15", branch="ZZ99"),
            ],
            ["20260510=OPEN", "20260511=OPEN", "20260512=OPEN", "20260513=OPEN"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == [
            "MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED",
            "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED",
        ]
        assert rows[1]["zone_code"] == ""
        assert rows[8]["account"] == "ACCT2005"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 1000
        assert summary["unmatched_count"] == 8
        assert summary["unmatched_amount_cents"] == 24999

    def test_report_keeps_action_order_blank_unmatched_category_and_positive_totals(self):
        """Output should keep action order, blank unmatched categories, exact statuses, and positive cent totals."""
        compile_program()
        write_inputs(
            [
                src("SCORDER0001", "ACCT4001", "CBD", 101, "20260601", branch="BD01"),
                src("SCORDER0002", "ACCT4002", "RES", 202, "20260601", branch="BD02"),
                src("SCORDER0003", "ACCT4003", "UNI", 303, "20260601", branch="BD03"),
            ],
            [
                action("SCORDER0003", "ACCT4003", "UNI", 303, "20260602", "S15", branch="BD03"),
                action("SCORDER0002", "ACCT4002", "RES", 999, "20260602", "S07", branch="BD02"),
                action("SCORDER0001", "ACCT4001", "CBD", 101, "20260602", "S02", branch="BD01"),
            ],
            ["20260601=OPEN"],
        )
        rows, summary = run_program()

        assert [row["record_id"] for row in rows] == ["SCORDER0003", "SCORDER0002", "SCORDER0001"]
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["zone_code"] == ""
        assert [row["amount_cents"] for row in rows] == ["0000000303", "0000000999", "0000000101"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 404
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 999

    def test_full_record_account_and_branch_are_independent_rejection_gates(self):
        """A candidate must fail when only record id, account, or branch differs."""
        compile_program()
        write_inputs(
            [
                src("SCIDFULL0001", "ACCT8001", "CBD", 111, "20260610", branch="BK01"),
                src("SCACCT000001", "ACCT8002", "RES", 222, "20260610", branch="BK02"),
                src("SCBRCH000001", "ACCT8003", "UNI", 333, "20260610", branch="BK03"),
            ],
            [
                action("SCIDFULL9999", "ACCT8001", "CBD", 111, "20260611", "S02", branch="BK01"),
                action("SCACCT000001", "ACCT9999", "RES", 222, "20260611", "S07", branch="BK02"),
                action("SCBRCH000001", "ACCT8003", "UNI", 333, "20260611", "S15", branch="ZZ99"),
                action("SCIDFULL0001", "ACCT8001", "CBD", 111, "20260611", "S02", branch="BK01"),
            ],
            ["20260610=OPEN", "20260611=OPEN"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[0]["zone_code"] == rows[1]["zone_code"] == rows[2]["zone_code"] == ""
        assert summary["matched_count"] == 1
        assert summary["unmatched_amount_cents"] == 666

    def test_trimmed_record_id_and_account_in_csv_output(self):
        """Shorter fixed-width ids and accounts must lose trailing spaces in CSV output."""
        compile_program()
        write_inputs(
            [src("SHORTID", "ACC1", "CBD", 500, "20260601", branch="BR01")],
            [action("SHORTID", "ACC1", "CBD", 500, "20260602", "S02", branch="BR01")],
            ["20260601=OPEN"],
        )
        rows, summary = run_program()

        assert rows[0]["record_id"] == "SHORTID"
        assert rows[0]["account"] == "ACC1"
        assert rows[0]["status"] == "MATCHED"
        assert summary["matched_count"] == 1
