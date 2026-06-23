"""Hospital claim denial reconciler milestone 2 tests."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
SRC = APP / "src" / "claim_denial_reconcile.cbl"
BIN = APP / "build" / "claim_denial_reconcile"
SOURCE = APP / "data" / "claims.dat"
ACTION = APP / "data" / "denials.dat"
CALENDAR = APP / "config" / "adjudication_calendar.txt"
REPORT = APP / "out" / "denial_report.csv"
SUMMARY = APP / "out" / "denial_summary.txt"


def src(record_id, account, service, amount, date, status="A", branch="B001"):
    """Create one fixed-width source record."""
    return f"S{record_id:<12}{account:<8}{service:<3}{amount:010d}{date}{status}{branch:<4}"


def action(record_id, account, service, amount, date, reason, branch="B001"):
    """Create one fixed-width action record."""
    return f"A{record_id:<12}{account:<8}{service:<3}{amount:010d}{date}{reason:<3}{branch:<4}"


def compile_program():
    """Compile the COBOL program before each scenario."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cobc", "-x", "-free", "-O2", "-o", str(BIN), str(SRC)], check=True, cwd=APP, timeout=60)


def write_inputs(source_lines, action_lines, calendar_lines):
    """Replace input files so outputs cannot be precomputed from shipped fixtures."""
    SOURCE.write_text("\n".join(source_lines) + "\n")
    ACTION.write_text("\n".join(action_lines) + "\n")
    CALENDAR.write_text("\n".join(calendar_lines) + "\n")
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


class TestMilestone2:
    def test_core_keys_status_reason_and_service_match_with_positive_totals(self):
        """Canonical services should match through full keys, status, reason, and branch gates."""
        compile_program()
        write_inputs(
            [
                src("HC0000000001", "ACCT1001", "ER", 1200, "20260501", branch="BR01"),
                src("HC0000000002", "ACCT1002", "LAB", 3400, "20260502", branch="BR02"),
                src("HC0000000003", "ACCT1003", "IMG", 5600, "20260503", branch="BR03"),
            ],
            [
                action("HC0000000001", "ACCT1001", "ER", 1200, "20260504", "D01", branch="BR01"),
                action("HC0000000002", "ACCT1002", "LAB", 3400, "20260505", "D02", branch="BR02"),
                action("HC0000000003", "ACCT1003", "IMG", 5600, "20260506", "D17", branch="BR03"),
            ],
            ["20260501=OPEN", "20260502=OPEN", "20260503=OPEN"],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "record_id,account,service,amount_cents,reason,status"
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["service"] for row in rows] == ["ER", "LAB", "IMG"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 10200,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_every_matching_gate_can_reject_a_candidate_without_reusing_rows(self):
        """Status, amount, account, branch, reason, date, service, and row consumption all gate matching."""
        compile_program()
        write_inputs(
            [
                src("HCGATE000001", "ACCT2001", "ER", 1000, "20260510", branch="BA01"),
                src("HCGATE000002", "ACCT2002", "ER", 2000, "20260510", status="X", branch="BA02"),
                src("HCGATE000003", "ACCT2003", "LAB", 3000, "20260511", branch="BA03"),
                src("HCGATE000004", "ACCT2004", "BAD", 4000, "20260512", branch="BA04"),
                src("HCGATE000005", "ACCT2005", "IMG", 5000, "20260513", branch="BA05"),
            ],
            [
                action("HCGATE000001", "ACCT2001", "ER", 1000, "20260514", "D01", branch="BA01"),
                action("HCGATE000001", "ACCT2001", "ER", 1000, "20260514", "D01", branch="BA01"),
                action("HCGATE000002", "ACCT2002", "ER", 2000, "20260514", "D01", branch="BA02"),
                action("HCGATE000003", "ACCT2999", "LAB", 3000, "20260514", "D02", branch="BA03"),
                action("HCGATE000003", "ACCT2003", "LAB", 3999, "20260514", "D02", branch="BA03"),
                action("HCGATE000003", "ACCT2003", "LAB", 3000, "20260509", "D02", branch="BA03"),
                action("HCGATE000003", "ACCT2003", "LAB", 3000, "20260514", "BAD", branch="BA03"),
                action("HCGATE000004", "ACCT2004", "BAD", 4000, "20260514", "D01", branch="BA04"),
                action("HCGATE000005", "ACCT2005", "IMG", 5000, "20260514", "D17", branch="ZZ99"),
            ],
            ["20260510=OPEN", "20260511=OPEN", "20260512=OPEN", "20260513=OPEN"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == [
            "MATCHED",
            "UNMATCHED",
            "UNMATCHED",
            "UNMATCHED",
            "UNMATCHED",
            "UNMATCHED",
            "UNMATCHED",
            "UNMATCHED",
            "UNMATCHED",
        ]
        assert rows[1]["service"] == ""
        raw_line = REPORT.read_text().splitlines()[2]
        assert raw_line.split(",")[2] == ""
        assert rows[8]["account"] == "ACCT2005"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 1000
        assert summary["unmatched_count"] == 8
        assert summary["unmatched_amount_cents"] == 24999

    def test_report_keeps_action_order_blank_unmatched_service_and_positive_totals(self):
        """Output should keep action order, blank unmatched services, exact statuses, and positive cent totals."""
        compile_program()
        write_inputs(
            [
                src("HCORDER0001", "ACCT4001", "ER", 101, "20260601", branch="BD01"),
                src("HCORDER0002", "ACCT4002", "LAB", 202, "20260601", branch="BD02"),
                src("HCORDER0003", "ACCT4003", "IMG", 303, "20260601", branch="BD03"),
            ],
            [
                action("HCORDER0003", "ACCT4003", "IMG", 303, "20260602", "D17", branch="BD03"),
                action("HCORDER0002", "ACCT4002", "LAB", 999, "20260602", "D02", branch="BD02"),
                action("HCORDER0001", "ACCT4001", "ER", 101, "20260602", "D01", branch="BD01"),
            ],
            ["20260601=OPEN"],
        )
        rows, summary = run_program()

        assert [row["record_id"] for row in rows] == ["HCORDER0003", "HCORDER0002", "HCORDER0001"]
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["service"] == ""
        raw_line = REPORT.read_text().splitlines()[2]
        assert raw_line.split(",")[2] == ""
        assert [row["amount_cents"] for row in rows] == ["0000000303", "0000000999", "0000000101"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 404
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 999

    def test_legacy_aliases_match_and_emit_canonical_services(self):
        """Legacy aliases should normalize to canonical services before matching and in the report."""
        compile_program()
        write_inputs(
            [
                src("HCAL00000001", "ACCT5001", "ER", 1500, "20260701", branch="BE01"),
                src("HCAL00000002", "ACCT5002", "LAB", 2500, "20260701", branch="BE02"),
                src("HCAL00000003", "ACCT5003", "IMG", 3500, "20260701", branch="BE03"),
            ],
            [
                action("HCAL00000001", "ACCT5001", "E1", 1500, "20260702", "D01", branch="BE01"),
                action("HCAL00000002", "ACCT5002", "LB", 2500, "20260702", "D02", branch="BE02"),
                action("HCAL00000003", "ACCT5003", "XR", 3500, "20260702", "D17", branch="BE03"),
            ],
            ["20260701=OPEN"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["service"] for row in rows] == ["ER", "LAB", "IMG"]
        assert summary["matched_count"] == 3

    def test_source_side_alias_values_are_not_canonical_services(self):
        """Source-side alias-like service values must stay ineligible even when actions use aliases."""
        compile_program()
        write_inputs(
            [
                src("HCSRCALIAS1", "ACCT5101", "E1", 1100, "20260703", branch="BE11"),
                src("HCSRCALIAS2", "ACCT5102", "LB", 2200, "20260703", branch="BE12"),
                src("HCSRCALIAS3", "ACCT5103", "XR", 3300, "20260703", branch="BE13"),
            ],
            [
                action("HCSRCALIAS1", "ACCT5101", "E1", 1100, "20260704", "D01", branch="BE11"),
                action("HCSRCALIAS2", "ACCT5102", "LB", 2200, "20260704", "D02", branch="BE12"),
                action("HCSRCALIAS3", "ACCT5103", "XR", 3300, "20260704", "D17", branch="BE13"),
            ],
            ["20260703=OPEN"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert [row["service"] for row in rows] == ["", "", ""]
        assert all(line.split(",")[2] == "" for line in REPORT.read_text().splitlines()[1:])
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 3,
            "unmatched_amount_cents": 6600,
        }

    def test_duplicate_actions_do_not_reuse_the_same_source_row(self):
        """Only the first eligible action may consume a matching source row."""
        compile_program()
        write_inputs(
            [src("HCDUP0000001", "ACCT6001", "ER", 900, "20260710", branch="BF01")],
            [
                action("HCDUP0000001", "ACCT6001", "ER", 900, "20260711", "D01", branch="BF01"),
                action("HCDUP0000001", "ACCT6001", "ER", 900, "20260712", "D01", branch="BF01"),
            ],
            ["20260710=OPEN"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[1]["service"] == ""
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 900,
            "unmatched_count": 1,
            "unmatched_amount_cents": 900,
        }
