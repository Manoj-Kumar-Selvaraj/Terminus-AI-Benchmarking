"""Verifier tests for the hospital claim denial COBOL reconciler."""

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
    """Compile the COBOL program for a verifier scenario."""
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


class TestMilestone3:
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
        assert [row["record_id"] for row in rows] == ["HC0000000001", "HC0000000002", "HC0000000003"]
        assert [row["account"] for row in rows] == ["ACCT1001", "ACCT1002", "ACCT1003"]
        assert [row["service"] for row in rows] == ["ER", "LAB", "IMG"]
        assert [row["reason"] for row in rows] == ["D01", "D02", "D17"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 10200,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

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

    def test_closed_missing_and_malformed_calendar_dates_stay_unmatched(self):
        """Closed, missing, malformed, or unlisted source dates should never be treated as open."""
        compile_program()
        write_inputs(
            [
                src("HCCAL0000001", "ACCT3001", "ER", 1111, "20260520", branch="BC01"),
                src("HCCAL0000002", "ACCT3002", "LAB", 2222, "20260521", branch="BC02"),
                src("HCCAL0000003", "ACCT3003", "IMG", 3333, "20260522", branch="BC03"),
                src("HCCAL0000004", "ACCT3004", "ER", 4444, "BAD-DATE", branch="BC04"),
            ],
            [
                action("HCCAL0000001", "ACCT3001", "ER", 1111, "20260523", "D01", branch="BC01"),
                action("HCCAL0000002", "ACCT3002", "LAB", 2222, "20260523", "D02", branch="BC02"),
                action("HCCAL0000003", "ACCT3003", "IMG", 3333, "20260523", "D17", branch="BC03"),
                action("HCCAL0000004", "ACCT3004", "ER", 4444, "20260523", "D01", branch="BC04"),
            ],
            ["20260520=OPEN", "20260521=CLOS", "BAD-DATE=OPEN"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary["matched_amount_cents"] == 1111
        assert summary["unmatched_amount_cents"] == 9999

    def test_latest_source_date_wins_and_leaves_older_row_for_later_action(self):
        """Latest open source date must be consumed first so an older eligible row remains available."""
        compile_program()
        write_inputs(
            [
                src("HCLAT0000001", "ACCT7001", "ER", 500, "20260801", branch="BG01"),
                src("HCLAT0000001", "ACCT7001", "ER", 500, "20260805", branch="BG01"),
            ],
            [
                action("HCLAT0000001", "ACCT7001", "E1", 500, "20260810", "D01", branch="BG01"),
                action("HCLAT0000001", "ACCT7001", "E1", 500, "20260804", "D01", branch="BG01"),
            ],
            ["20260801=OPEN", "20260805=OPEN"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["record_id"] for row in rows] == ["HCLAT0000001", "HCLAT0000001"]
        assert [row["account"] for row in rows] == ["ACCT7001", "ACCT7001"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1000,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_same_source_date_tie_prefers_earliest_input_row(self):
        """When source dates tie, the earliest source input row must be consumed first."""
        compile_program()
        write_inputs(
            [
                src("HCTIE0000001", "ACCT7101", "ER", 500, "20260805", branch="BG01"),
                src("HCTIE0000001", "ACCT7101", "ER", 500, "20260805", branch="BG01"),
            ],
            [
                action("HCTIE0000001", "ACCT7101", "E1", 500, "20260810", "D01", branch="BG01"),
                action("HCTIE0000001", "ACCT7101", "E1", 500, "20260810", "D01", branch="BG01"),
            ],
            ["20260805=OPEN", "20260810=OPEN"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1000,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_duplicate_record_id_rows_are_consumed_by_position(self):
        """Two source rows with the same record id must be independently consumable by amount."""
        compile_program()
        write_inputs(
            [
                src("HCPOS000001", "ACCT9001", "ER", 500, "20260810", branch="BX01"),
                src("HCPOS000001", "ACCT9001", "ER", 700, "20260810", branch="BX01"),
            ],
            [
                action("HCPOS000001", "ACCT9001", "ER", 500, "20260811", "D01", branch="BX01"),
                action("HCPOS000001", "ACCT9001", "ER", 700, "20260811", "D01", branch="BX01"),
            ],
            ["20260810=OPEN", "20260811=OPEN"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1200,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_calendar_open_state_is_case_insensitive(self):
        """Mixed-case OPEN calendar states must still allow eligible source dates."""
        compile_program()
        write_inputs(
            [src("HCCASE000001", "ACCT9002", "ER", 500, "20260901", branch="BX02")],
            [action("HCCASE000001", "ACCT9002", "E1", 500, "20260902", "D01", branch="BX02")],
            ["20260901=Open", "20260902=OPEN"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service"] == "ER"
        assert summary["matched_count"] == 1

    def test_action_date_does_not_require_an_open_calendar_entry(self):
        """A valid action date may match when only the source date is listed as open."""
        compile_program()
        write_inputs(
            [src("HCACT0000001", "ACCT9003", "LAB", 725, "20260910", branch="BX03")],
            [action("HCACT0000001", "ACCT9003", "LB", 725, "20260912", "D02", branch="BX03")],
            ["20260910=OPEN"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service"] == "LAB"
        assert rows[0]["reason"] == "D02"
        assert summary["matched_amount_cents"] == 725

    def test_second_action_stays_unmatched_after_latest_source_row_is_consumed(self):
        """Once the only eligible source row is consumed, a second duplicate action must remain unmatched."""
        compile_program()
        write_inputs(
            [src("HCLAT0000002", "ACCT7002", "ER", 1000, "20260805", branch="BG01")],
            [
                action("HCLAT0000002", "ACCT7002", "E1", 1000, "20260810", "D01", branch="BG01"),
                action("HCLAT0000002", "ACCT7002", "E1", 1000, "20260811", "D01", branch="BG01"),
            ],
            ["20260805=OPEN", "20260810=OPEN", "20260811=OPEN"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_aliases_still_work_under_calendar_gates(self):
        """Alias normalization must still apply when calendar gates are enforced."""
        compile_program()
        write_inputs(
            [src("HCALM3000001", "ACCT8001", "IMG", 650, "20260901", branch="BH01")],
            [action("HCALM3000001", "ACCT8001", "XR", 650, "20260902", "D17", branch="BH01")],
            ["20260901=OPEN", "20260902=OPEN"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service"] == "IMG"
        assert summary["matched_amount_cents"] == 650

    def test_both_blank_dates_still_clear_like_undated_records(self):
        """When source and action dates are both blank, matching should follow the undated path."""
        compile_program()
        write_inputs(
            [
                src("HCBLANK00001", "ACCT9101", "ER", 900, "        ", branch="BY01"),
                src("HCBLANK00002", "ACCT9102", "LAB", 800, "20261001", branch="BY02"),
            ],
            [
                action("HCBLANK00001", "ACCT9101", "ER", 900, "        ", "D01", branch="BY01"),
                action("HCBLANK00002", "ACCT9102", "LB", 800, "20261002", "D02", branch="BY02"),
            ],
            ["20261001=OPEN", "20261002=OPEN"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service"] == "ER"
        assert rows[1]["status"] == "MATCHED"
        assert rows[1]["service"] == "LAB"
        assert summary["matched_count"] == 2

    def test_one_side_blank_date_pairs_are_ineligible(self):
        """A blank date on only the source side or only the action side must not clear."""
        compile_program()
        write_inputs(
            [
                src("HCONESIDE001", "ACCT9201", "ER", 600, "        ", branch="BZ01"),
                src("HCONESIDE002", "ACCT9202", "LAB", 700, "20261010", branch="BZ02"),
                src("HCONESIDE003", "ACCT9203", "IMG", 800, "20261010", branch="BZ03"),
            ],
            [
                action("HCONESIDE001", "ACCT9201", "ER", 600, "20261011", "D01", branch="BZ01"),
                action("HCONESIDE002", "ACCT9202", "LB", 700, "        ", "D02", branch="BZ02"),
                action("HCONESIDE003", "ACCT9203", "XR", 800, "20261011", "D17", branch="BZ03"),
            ],
            ["20261010=OPEN", "20261011=OPEN"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "MATCHED"]
        assert [row["service"] for row in rows] == ["", "", "IMG"]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 2,
            "unmatched_amount_cents": 1300,
        }
