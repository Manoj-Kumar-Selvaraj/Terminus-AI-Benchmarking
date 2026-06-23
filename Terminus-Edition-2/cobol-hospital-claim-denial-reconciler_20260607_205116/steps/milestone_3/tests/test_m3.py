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
TRACE = APP / "out" / "source_consumption.csv"


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
    TRACE.unlink(missing_ok=True)


def run_program():
    """Run the reconciler and return parsed report and summary data."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {}
    for raw in SUMMARY.read_text().splitlines():
        key, value = raw.split("=", 1)
        summary[key] = int(value)
    trace_rows = []
    if TRACE.exists():
        with TRACE.open(newline="") as handle:
            trace_rows = list(csv.DictReader(handle))
    return rows, summary, trace_rows


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
        rows, summary, trace_rows = run_program()

        assert REPORT.read_text().splitlines()[0] == "record_id,account,service,amount_cents,reason,status"
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["service"] for row in rows] == ["ER", "LAB", "IMG"]
        assert [row["reason"] for row in rows] == ["D01", "D02", "D17"]
        assert [row["source_row"] for row in trace_rows] == ["0001", "0002", "0003"]
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
        rows, summary, trace_rows = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["service"] for row in rows] == ["ER", "LAB", "IMG"]
        assert [row["reason"] for row in rows] == ["D01", "D02", "D17"]
        assert [row["source_date"] for row in trace_rows] == ["20260701", "20260701", "20260701"]
        assert summary["matched_count"] == 3

    def test_source_side_alias_values_remain_ineligible_under_calendar_gates(self):
        """Alias normalization applies only to action services, not source services."""
        compile_program()
        write_inputs(
            [
                src("HCM3ALIAS01", "ACCT5201", "E1", 1100, "20260703", branch="BE21"),
                src("HCM3ALIAS02", "ACCT5202", "LB", 2200, "20260703", branch="BE22"),
                src("HCM3ALIAS03", "ACCT5203", "XR", 3300, "20260703", branch="BE23"),
            ],
            [
                action("HCM3ALIAS01", "ACCT5201", "E1", 1100, "20260704", "D01", branch="BE21"),
                action("HCM3ALIAS02", "ACCT5202", "LB", 2200, "20260704", "D02", branch="BE22"),
                action("HCM3ALIAS03", "ACCT5203", "XR", 3300, "20260704", "D17", branch="BE23"),
            ],
            ["20260703=OPEN", "20260704=OPEN"],
        )
        rows, summary, trace_rows = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert [row["service"] for row in rows] == ["", "", ""]
        assert [row["reason"] for row in rows] == ["D01", "D02", "D17"]
        assert all(line.split(",")[2] == "" for line in REPORT.read_text().splitlines()[1:])
        assert trace_rows == []
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 6600

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
        rows, summary, trace_rows = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[1]["service"] == ""
        assert [row["reason"] for row in rows] == ["D01", "D01"]
        raw_line = REPORT.read_text().splitlines()[2]
        assert raw_line.split(",")[2] == ""
        assert [row["source_row"] for row in trace_rows] == ["0001"]
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
        rows, summary, trace_rows = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert [row["reason"] for row in rows] == ["D01", "D02", "D17", "D01"]
        assert [row["source_row"] for row in trace_rows] == ["0001"]
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
                action("HCLAT0000001", "ACCT7001", "E1", 500, "20260803", "D01", branch="BG01"),
            ],
            ["20260801=OPEN", "20260805=OPEN", "20260803=OPEN", "20260810=OPEN"],
        )
        rows, summary, trace_rows = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["reason"] for row in rows] == ["D01", "D01"]
        assert trace_rows == [
            {"action_record_id": "HCLAT0000001", "source_row": "0002", "source_date": "20260805"},
            {"action_record_id": "HCLAT0000001", "source_row": "0001", "source_date": "20260801"},
        ]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1000,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_latest_source_date_wins_with_distinct_amounts(self):
        """Latest open source date must bind each distinct action amount even when an earlier row appears first."""
        compile_program()
        write_inputs(
            [
                src("HCLAT0000003", "ACCT7003", "ER", 1000, "20260801", branch="BG01"),
                src("HCLAT0000003", "ACCT7003", "ER", 1500, "20260805", branch="BG01"),
                src("HCLAT0000003", "ACCT7003", "ER", 1200, "20260803", branch="BG01"),
            ],
            [
                action("HCLAT0000003", "ACCT7003", "E1", 1500, "20260810", "D01", branch="BG01"),
                action("HCLAT0000003", "ACCT7003", "E1", 1000, "20260811", "D02", branch="BG01"),
            ],
            ["20260801=OPEN", "20260803=OPEN", "20260805=OPEN", "20260810=OPEN", "20260811=OPEN"],
        )
        rows, summary, trace_rows = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["amount_cents"] for row in rows] == ["0000001500", "0000001000"]
        assert [row["reason"] for row in rows] == ["D01", "D02"]
        assert trace_rows == [
            {"action_record_id": "HCLAT0000003", "source_row": "0002", "source_date": "20260805"},
            {"action_record_id": "HCLAT0000003", "source_row": "0001", "source_date": "20260801"},
        ]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 2500,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_latest_source_date_consumes_newest_rows_before_exhausting_older_duplicates(self):
        """Among equal-amount candidates, latest source dates must be consumed before older duplicates."""
        compile_program()
        write_inputs(
            [
                src("HCLATEX001", "ACCT7101", "ER", 500, "20260801", branch="BG01"),
                src("HCLATEX001", "ACCT7101", "ER", 500, "20260805", branch="BG01"),
                src("HCLATEX001", "ACCT7101", "ER", 500, "20260803", branch="BG01"),
            ],
            [
                action("HCLATEX001", "ACCT7101", "E1", 500, "20260810", "D01", branch="BG01"),
                action("HCLATEX001", "ACCT7101", "E1", 500, "20260810", "D02", branch="BG01"),
                action("HCLATEX001", "ACCT7101", "E1", 500, "20260810", "D17", branch="BG01"),
                action("HCLATEX001", "ACCT7101", "E1", 500, "20260810", "D01", branch="BG01"),
            ],
            ["20260801=OPEN", "20260803=OPEN", "20260805=OPEN", "20260810=OPEN"],
        )
        rows, summary, trace_rows = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["reason"] for row in rows] == ["D01", "D02", "D17", "D01"]
        assert [row["source_row"] for row in trace_rows] == ["0002", "0003", "0001"]
        assert [row["source_date"] for row in trace_rows] == ["20260805", "20260803", "20260801"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 1500,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_same_source_date_tie_prefers_earliest_input_row(self):
        """Same-date duplicate candidates must consume the earliest physical source row first."""
        compile_program()
        write_inputs(
            [
                src("HCTIE0000001", "ACCT7101", "ER", 500, "20260805", branch="BG01"),
                src("HCTIE0000001", "ACCT7101", "ER", 500, "20260805", branch="BG01"),
            ],
            [
                action("HCTIE0000001", "ACCT7101", "E1", 500, "20260810", "D01", branch="BG01"),
                action("HCTIE0000001", "ACCT7101", "E1", 500, "20260810", "D02", branch="BG01"),
            ],
            ["20260805=OPEN", "20260810=OPEN"],
        )
        rows, summary, trace_rows = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["reason"] for row in rows] == ["D01", "D02"]
        assert [row["amount_cents"] for row in rows] == ["0000000500", "0000000500"]
        assert [row["source_row"] for row in trace_rows] == ["0001", "0002"]
        assert [row["source_date"] for row in trace_rows] == ["20260805", "20260805"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1000,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_same_source_date_tie_prefers_earliest_input_row_with_distinct_amounts(self):
        """Equal-date candidates with distinct amounts must still consume earliest source rows first."""
        compile_program()
        write_inputs(
            [
                src("HCTIE0000002", "ACCT7102", "ER", 1500, "20260805", branch="BG01"),
                src("HCTIE0000002", "ACCT7102", "ER", 1600, "20260805", branch="BG01"),
                src("HCTIE0000002", "ACCT7102", "ER", 1700, "20260805", branch="BG01"),
            ],
            [
                action("HCTIE0000002", "ACCT7102", "E1", 1500, "20260810", "D01", branch="BG01"),
                action("HCTIE0000002", "ACCT7102", "E1", 1600, "20260811", "D02", branch="BG01"),
                action("HCTIE0000002", "ACCT7102", "E1", 1700, "20260812", "D17", branch="BG01"),
            ],
            ["20260805=OPEN", "20260810=OPEN", "20260811=OPEN", "20260812=OPEN"],
        )
        rows, summary, trace_rows = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["amount_cents"] for row in rows] == ["0000001500", "0000001600", "0000001700"]
        assert [row["reason"] for row in rows] == ["D01", "D02", "D17"]
        assert [row["source_row"] for row in trace_rows] == ["0001", "0002", "0003"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 4800,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_duplicate_record_id_rows_are_consumed_by_position(self):
        """Duplicate source rows with the same amount must be consumed independently by physical row position."""
        compile_program()
        write_inputs(
            [
                src("HCPOS000001", "ACCT9001", "ER", 500, "20260810", branch="BX01"),
                src("HCPOS000001", "ACCT9001", "ER", 500, "20260810", branch="BX01"),
            ],
            [
                action("HCPOS000001", "ACCT9001", "ER", 500, "20260811", "D01", branch="BX01"),
                action("HCPOS000001", "ACCT9001", "ER", 500, "20260811", "D02", branch="BX01"),
                action("HCPOS000001", "ACCT9001", "ER", 500, "20260812", "D17", branch="BX01"),
            ],
            ["20260810=OPEN", "20260811=OPEN", "20260812=OPEN"],
        )
        rows, summary, trace_rows = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["reason"] for row in rows] == ["D01", "D02", "D17"]
        assert [row["amount_cents"] for row in rows] == ["0000000500", "0000000500", "0000000500"]
        assert [row["source_row"] for row in trace_rows] == ["0001", "0002"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1000,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_duplicate_record_id_rows_are_consumed_by_position_with_distinct_amounts(self):
        """Distinct amounts on duplicate record ids must still map to independent source row positions."""
        compile_program()
        write_inputs(
            [
                src("HCPOS000002", "ACCT9002", "ER", 500, "20260810", branch="BX01"),
                src("HCPOS000002", "ACCT9002", "ER", 700, "20260810", branch="BX01"),
            ],
            [
                action("HCPOS000002", "ACCT9002", "ER", 500, "20260811", "D01", branch="BX01"),
                action("HCPOS000002", "ACCT9002", "ER", 700, "20260811", "D02", branch="BX01"),
            ],
            ["20260810=OPEN", "20260811=OPEN"],
        )
        rows, summary, trace_rows = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[0]["record_id"] == "HCPOS000002"
        assert rows[0]["account"] == "ACCT9002"
        assert [row["reason"] for row in rows] == ["D01", "D02"]
        assert [row["amount_cents"] for row in rows] == ["0000000500", "0000000700"]
        assert [row["source_row"] for row in trace_rows] == ["0001", "0002"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1200,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_report_record_id_and_account_are_trimmed_in_milestone_3(self):
        """Milestone 3 output must still omit type bytes and fixed-width padding."""
        compile_program()
        write_inputs(
            [src("HCTRIM9", "ACC9", "ER", 500, "20260901", branch="BZ01")],
            [action("HCTRIM9", "ACC9", "E1", 500, "20260902", "D01", branch="BZ01")],
            ["20260901=OPEN", "20260902=OPEN"],
        )
        rows, summary, trace_rows = run_program()

        assert rows[0]["record_id"] == "HCTRIM9"
        assert rows[0]["account"] == "ACC9"
        assert rows[0]["reason"] == "D01"
        assert not rows[0]["record_id"].startswith(("S", "A"))
        assert rows[0]["record_id"] == rows[0]["record_id"].strip()
        assert rows[0]["account"] == rows[0]["account"].strip()
        assert trace_rows[0]["source_row"] == "0001"
        assert summary["matched_count"] == 1

    def test_calendar_open_state_is_case_insensitive(self):
        """Mixed-case OPEN calendar states must still allow eligible source dates."""
        compile_program()
        write_inputs(
            [src("HCCASE000001", "ACCT9002", "ER", 500, "20260901", branch="BX02")],
            [action("HCCASE000001", "ACCT9002", "E1", 500, "20260902", "D01", branch="BX02")],
            ["20260901=Open", "20260902=OPEN"],
        )
        rows, summary, trace_rows = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service"] == "ER"
        assert rows[0]["reason"] == "D01"
        assert trace_rows[0]["source_date"] == "20260901"
        assert summary["matched_count"] == 1

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
        rows, summary, trace_rows = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["reason"] for row in rows] == ["D01", "D01"]
        assert [row["source_row"] for row in trace_rows] == ["0001"]
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
        rows, summary, trace_rows = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service"] == "IMG"
        assert rows[0]["reason"] == "D17"
        assert trace_rows[0]["source_row"] == "0001"
        assert summary["matched_amount_cents"] == 650

    def test_action_before_source_date_and_inactive_status_are_rejected(self):
        """Calendar eligibility must not bypass date ordering or active source status."""
        compile_program()
        write_inputs(
            [
                src("HCDATEORD001", "ACCT9301", "ER", 500, "20261105", branch="BJ01"),
                src("HCSTATUS0001", "ACCT9302", "LAB", 600, "20261101", status="X", branch="BJ02"),
            ],
            [
                action("HCDATEORD001", "ACCT9301", "E1", 500, "20261104", "D01", branch="BJ01"),
                action("HCSTATUS0001", "ACCT9302", "LB", 600, "20261102", "D02", branch="BJ02"),
            ],
            ["20261101=OPEN", "20261105=OPEN"],
        )
        rows, summary, trace_rows = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert [row["service"] for row in rows] == ["", ""]
        assert [row["reason"] for row in rows] == ["D01", "D02"]
        assert summary["unmatched_amount_cents"] == 1100
        assert trace_rows == []

    def test_one_sided_blank_dates_are_ineligible(self):
        """A blank date on only one side must not fall through to the undated matching path."""
        compile_program()
        write_inputs(
            [
                src("HCBLANKSIDE1", "ACCT9201", "ER", 900, "        ", branch="BY11"),
                src("HCBLANKSIDE2", "ACCT9202", "LAB", 800, "20261001", branch="BY12"),
            ],
            [
                action("HCBLANKSIDE1", "ACCT9201", "ER", 900, "20261002", "D01", branch="BY11"),
                action("HCBLANKSIDE2", "ACCT9202", "LB", 800, "        ", "D02", branch="BY12"),
            ],
            ["20261001=OPEN", "20261002=OPEN"],
        )
        rows, summary, trace_rows = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert [row["service"] for row in rows] == ["", ""]
        assert [row["reason"] for row in rows] == ["D01", "D02"]
        assert all(line.split(",")[2] == "" for line in REPORT.read_text().splitlines()[1:])
        assert trace_rows == []
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 2,
            "unmatched_amount_cents": 1700,
        }

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
        rows, summary, trace_rows = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["service"] == "ER"
        assert rows[0]["reason"] == "D01"
        assert rows[1]["status"] == "MATCHED"
        assert rows[1]["service"] == "LAB"
        assert rows[1]["reason"] == "D02"
        assert [row["source_row"] for row in trace_rows] == ["0001", "0002"]
        assert summary["matched_count"] == 2
