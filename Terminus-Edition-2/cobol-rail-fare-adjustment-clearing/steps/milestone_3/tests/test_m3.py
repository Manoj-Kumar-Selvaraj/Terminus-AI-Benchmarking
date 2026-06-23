"""Verifier tests for the rail fare adjustment COBOL reconciler."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
SRC = APP / "src" / "fare_adjust_reconcile.cbl"
BIN = APP / "build" / "fare_adjust_reconcile"
SOURCE = APP / "data" / "rides.dat"
ACTION = APP / "data" / "adjustments.dat"
CALENDAR = APP / "config" / "service_calendar.txt"
REPORT = APP / "out" / "adjustment_report.csv"
SUMMARY = APP / "out" / "adjustment_summary.txt"
TRACE = APP / "out" / "source_consumption.csv"


def src(record_id, account, category, amount, date, status="C", branch="B001"):
    """Create one fixed-width source record."""
    return f"S{record_id:<12}{account:<8}{category:<3}{amount:010d}{date}{status}{branch:<4}"


def action(record_id, account, category, amount, date, reason, branch="B001"):
    """Create one fixed-width action record."""
    return f"A{record_id:<12}{account:<8}{category:<3}{amount:010d}{date}{reason:<3}{branch:<4}"


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
    return rows, summary


def read_trace():
    """Return the source rows selected for matched actions."""
    with TRACE.open(newline="") as handle:
        return list(csv.DictReader(handle))


def test_core_keys_status_reason_and_category_match_with_positive_totals():
    """Canonical categories should match through full keys, status, reason, and branch gates."""
    compile_program()
    write_inputs(
        [
            src("RF0000000001", "ACCT1001", "STD", 1200, "20260501", branch="BR01"),
            src("RF0000000002", "ACCT1002", "EXP", 3400, "20260502", branch="BR02"),
            src("RF0000000003", "ACCT1003", "SNR", 5600, "20260503", branch="BR03"),
        ],
        [
            action("RF0000000001", "ACCT1001", "STD", 1200, "20260504", "F01", branch="BR01"),
            action("RF0000000002", "ACCT1002", "EXP", 3400, "20260505", "F07", branch="BR02"),
            action("RF0000000003", "ACCT1003", "SNR", 5600, "20260506", "F11", branch="BR03"),
        ],
        ["20260501=OPEN", "20260502=OPEN", "20260503=OPEN"],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "record_id,account,fare_class,amount_cents,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["fare_class"] for row in rows] == ["STD", "EXP", "SNR"]
    assert [row["reason"] for row in rows] == ["F01", "F07", "F11"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 10200,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
def test_every_matching_gate_can_reject_a_candidate_without_reusing_rows():
    """Status, amount, account, branch, reason, date, category, and row consumption all gate matching."""
    compile_program()
    write_inputs(
        [
            src("RFGATE000001", "ACCT2001", "STD", 1000, "20260510", branch="BA01"),
            src("RFGATE000002", "ACCT2002", "STD", 2000, "20260510", status="X", branch="BA02"),
            src("RFGATE000003", "ACCT2003", "EXP", 3000, "20260511", branch="BA03"),
            src("RFGATE000004", "ACCT2004", "BAD", 4000, "20260512", branch="BA04"),
            src("RFGATE000005", "ACCT2005", "SNR", 5000, "20260513", branch="BA05"),
        ],
        [
            action("RFGATE000001", "ACCT2001", "STD", 1000, "20260514", "F01", branch="BA01"),
            action("RFGATE000001", "ACCT2001", "STD", 1000, "20260514", "F01", branch="BA01"),
            action("RFGATE000002", "ACCT2002", "STD", 2000, "20260514", "F01", branch="BA02"),
            action("RFGATE000003", "ACCT2999", "EXP", 3000, "20260514", "F07", branch="BA03"),
            action("RFGATE000003", "ACCT2003", "EXP", 3999, "20260514", "F07", branch="BA03"),
            action("RFGATE000003", "ACCT2003", "EXP", 3000, "20260509", "F07", branch="BA03"),
            action("RFGATE000003", "ACCT2003", "EXP", 3000, "20260514", "BAD", branch="BA03"),
            action("RFGATE000004", "ACCT2004", "BAD", 4000, "20260514", "F01", branch="BA04"),
            action("RFGATE000005", "ACCT2005", "SNR", 5000, "20260514", "F11", branch="ZZ99"),
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
    assert rows[1]["fare_class"] == ""
    assert rows[6]["reason"] == "BAD"
    assert rows[8]["account"] == "ACCT2005"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 1000
    assert summary["unmatched_count"] == 8
    assert summary["unmatched_amount_cents"] == 24999
def test_report_keeps_action_order_blank_unmatched_category_and_positive_totals():
    """Output should keep action order, blank unmatched categories, exact statuses, and positive cent totals."""
    compile_program()
    write_inputs(
        [
            src("RFORDER0001", "ACCT4001", "STD", 101, "20260601", branch="BD01"),
            src("RFORDER0002", "ACCT4002", "EXP", 202, "20260601", branch="BD02"),
            src("RFORDER0003", "ACCT4003", "SNR", 303, "20260601", branch="BD03"),
        ],
        [
            action("RFORDER0003", "ACCT4003", "SNR", 303, "20260602", "F11", branch="BD03"),
            action("RFORDER0002", "ACCT4002", "EXP", 999, "20260602", "F07", branch="BD02"),
            action("RFORDER0001", "ACCT4001", "STD", 101, "20260602", "F01", branch="BD01"),
        ],
        ["20260601=OPEN"],
    )
    rows, summary = run_program()

    assert [row["record_id"] for row in rows] == ["RFORDER0003", "RFORDER0002", "RFORDER0001"]
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["fare_class"] == ""
    assert [row["amount_cents"] for row in rows] == ["0000000303", "0000000999", "0000000101"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 404
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 999


def test_reason_column_always_reflects_action_adjustment_code():
    """Each report row should echo the action reason, whether matched or not."""
    compile_program()
    write_inputs(
        [
            src("RFREASON0001", "ACCT3001", "STD", 1000, "20260520", branch="BR01"),
            src("RFREASON0002", "ACCT3002", "EXP", 2000, "20260520", branch="BR02"),
        ],
        [
            action("RFREASON0001", "ACCT3001", "STD", 1000, "20260521", "F01", branch="BR01"),
            action("RFREASON0001", "ACCT3001", "STD", 9999, "20260521", "F07", branch="BR01"),
            action("RFREASON0002", "ACCT3002", "EXP", 2000, "20260521", "BAD", branch="BR02"),
        ],
        ["20260520=OPEN"],
    )
    rows, summary = run_program()

    assert [row["reason"] for row in rows] == ["F01", "F07", "BAD"]
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary["matched_count"] == 1
    assert summary["unmatched_count"] == 2


def test_report_record_id_excludes_type_prefix_and_trims_padding():
    """Report record_id and account must exclude the type byte and fixed-width padding."""
    compile_program()
    write_inputs(
        [src("RFTYPE9", "ACC9", "STD", 500, "20260701", branch="BE01")],
        [action("RFTYPE9", "ACC9", "STD", 500, "20260702", "F01", branch="BE01")],
        ["20260701=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["record_id"] == "RFTYPE9"
    assert rows[0]["account"] == "ACC9"
    assert not rows[0]["record_id"].startswith(("S", "A"))
    assert rows[0]["record_id"] == rows[0]["record_id"].strip()
    assert rows[0]["account"] == rows[0]["account"].strip()
    assert summary["matched_count"] == 1


def test_legacy_aliases_match_and_emit_canonical_categories():
    """Legacy aliases should normalize to canonical categories before matching and in the report."""
    compile_program()
    write_inputs(
        [
            src("RFAL00000001", "ACCT5001", "STD", 1500, "20260701", branch="BE01"),
            src("RFAL00000002", "ACCT5002", "EXP", 2500, "20260701", branch="BE02"),
            src("RFAL00000003", "ACCT5003", "SNR", 3500, "20260701", branch="BE03"),
        ],
        [
            action("RFAL00000001", "ACCT5001", "ST", 1500, "20260702", "F01", branch="BE01"),
            action("RFAL00000002", "ACCT5002", "EX", 2500, "20260702", "F07", branch="BE02"),
            action("RFAL00000003", "ACCT5003", "SR", 3500, "20260702", "F11", branch="BE03"),
        ],
        ["20260701=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["fare_class"] for row in rows] == ["STD", "EXP", "SNR"]
    assert summary["matched_count"] == 3
def test_duplicate_actions_do_not_reuse_the_same_source_row():
    """Only the first eligible action may consume a matching source row."""
    compile_program()
    write_inputs(
        [src("RFDUP0000001", "ACCT6001", "STD", 900, "20260710", branch="BF01")],
        [
            action("RFDUP0000001", "ACCT6001", "STD", 900, "20260711", "F01", branch="BF01"),
            action("RFDUP0000001", "ACCT6001", "STD", 900, "20260712", "F01", branch="BF01"),
        ],
        ["20260710=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert rows[1]["fare_class"] == ""
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 900,
        "unmatched_count": 1,
        "unmatched_amount_cents": 900,
    }
def test_closed_missing_and_malformed_calendar_dates_stay_unmatched():
    """Closed, missing, malformed, or unlisted source dates should never be treated as open."""
    compile_program()
    write_inputs(
        [
            src("RFCAL0000001", "ACCT3001", "STD", 1111, "20260520", branch="BC01"),
            src("RFCAL0000002", "ACCT3002", "EXP", 2222, "20260521", branch="BC02"),
            src("RFCAL0000003", "ACCT3003", "SNR", 3333, "20260522", branch="BC03"),
            src("RFCAL0000004", "ACCT3004", "STD", 4444, "BAD-DATE", branch="BC04"),
        ],
        [
            action("RFCAL0000001", "ACCT3001", "STD", 1111, "20260523", "F01", branch="BC01"),
            action("RFCAL0000002", "ACCT3002", "EXP", 2222, "20260523", "F07", branch="BC02"),
            action("RFCAL0000003", "ACCT3003", "SNR", 3333, "20260523", "F11", branch="BC03"),
            action("RFCAL0000004", "ACCT3004", "STD", 4444, "20260523", "F01", branch="BC04"),
        ],
        ["20260520=OPEN", "20260521=CLOS", "BAD-DATE=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary["matched_amount_cents"] == 1111
    assert summary["unmatched_amount_cents"] == 9999
def test_same_source_date_tie_prefers_earliest_input_row():
    """Equal-date candidates must be consumed in physical source order."""
    compile_program()
    write_inputs(
        [
            src("RFTIE0000001", "ACCT7101", "STD", 500, "20260805", branch="BG01"),
            src("RFTIE0000001", "ACCT7101", "STD", 500, "20260805", branch="BG01"),
        ],
        [
            action("RFTIE0000001", "ACCT7101", "STD", 500, "20260810", "F01", branch="BG01"),
            action("RFTIE0000001", "ACCT7101", "STD", 500, "20260810", "F01", branch="BG01"),
        ],
        ["20260805=OPEN", "20260810=OPEN"],
    )
    rows, summary = run_program()
    trace = read_trace()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["source_row"] for row in trace] == ["0001", "0002"]
    assert [row["source_date"] for row in trace] == ["20260805", "20260805"]
    assert summary == {
        "matched_count": 2,
        "matched_amount_cents": 1000,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_duplicate_record_id_rows_are_consumed_by_position():
    """Two source rows with the same record id must be independently consumable by amount."""
    compile_program()
    write_inputs(
        [
            src("RFPOS000001", "ACCT9001", "STD", 500, "20260810", branch="BX01"),
            src("RFPOS000001", "ACCT9001", "STD", 700, "20260810", branch="BX01"),
        ],
        [
            action("RFPOS000001", "ACCT9001", "STD", 500, "20260811", "F01", branch="BX01"),
            action("RFPOS000001", "ACCT9001", "STD", 700, "20260811", "F01", branch="BX01"),
        ],
        ["20260810=OPEN", "20260811=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["amount_cents"] for row in rows] == ["0000000500", "0000000700"]
    assert summary == {
        "matched_count": 2,
        "matched_amount_cents": 1200,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_calendar_open_state_is_case_insensitive():
    """Arbitrary casing of OPEN must allow the actual source date."""
    compile_program()
    write_inputs(
        [src("RFCASE000001", "ACCT9002", "STD", 500, "20260901", branch="BX02")],
        [action("RFCASE000001", "ACCT9002", "ST", 500, "20260902", "F01", branch="BX02")],
        ["20260901=oPeN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["fare_class"] == "STD"
    assert summary["matched_count"] == 1


def test_latest_source_date_wins_when_multiple_rows_qualify():
    """Otherwise identical candidates must be consumed from latest source date to oldest."""
    compile_program()
    write_inputs(
        [
            src("RFLAT0000001", "ACCT7001", "STD", 500, "20260801", branch="BG01"),
            src("RFLAT0000001", "ACCT7001", "STD", 500, "20260805", branch="BG01"),
        ],
        [
            action("RFLAT0000001", "ACCT7001", "STD", 500, "20260810", "F01", branch="BG01"),
            action("RFLAT0000001", "ACCT7001", "STD", 500, "20260810", "F01", branch="BG01"),
        ],
        ["20260801=OPEN", "20260805=OPEN", "20260810=OPEN"],
    )
    rows, summary = run_program()
    trace = read_trace()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["source_row"] for row in trace] == ["0002", "0001"]
    assert [row["source_date"] for row in trace] == ["20260805", "20260801"]
    assert summary == {
        "matched_count": 2,
        "matched_amount_cents": 1000,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_latest_source_date_consumes_newest_rows_before_exhausting_older_duplicates():
    """Three duplicate-eligible source rows should leave the oldest row for the final action."""
    compile_program()
    write_inputs(
        [
            src("RFLATEX001", "ACCT7101", "STD", 100, "20260801", branch="BG01"),
            src("RFLATEX001", "ACCT7101", "STD", 100, "20260805", branch="BG01"),
            src("RFLATEX001", "ACCT7101", "STD", 100, "20260803", branch="BG01"),
        ],
        [
            action("RFLATEX001", "ACCT7101", "STD", 100, "20260810", "F01", branch="BG01"),
            action("RFLATEX001", "ACCT7101", "STD", 100, "20260810", "F01", branch="BG01"),
            action("RFLATEX001", "ACCT7101", "STD", 100, "20260810", "F01", branch="BG01"),
            action("RFLATEX001", "ACCT7101", "STD", 100, "20260810", "F01", branch="BG01"),
        ],
        ["20260801=OPEN", "20260803=OPEN", "20260805=OPEN", "20260810=OPEN"],
    )
    rows, summary = run_program()
    trace = read_trace()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["source_date"] for row in trace] == ["20260805", "20260803", "20260801"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 300,
        "unmatched_count": 1,
        "unmatched_amount_cents": 100,
    }


def test_second_action_stays_unmatched_after_latest_source_row_is_consumed():
    """Once the only eligible source row is consumed, a second duplicate action must remain unmatched."""
    compile_program()
    write_inputs(
        [src("RFLAT0000002", "ACCT7002", "STD", 1000, "20260805", branch="BG01")],
        [
            action("RFLAT0000002", "ACCT7002", "ST", 1000, "20260810", "F01", branch="BG01"),
            action("RFLAT0000002", "ACCT7002", "ST", 1000, "20260811", "F01", branch="BG01"),
        ],
        ["20260805=OPEN", "20260810=OPEN", "20260811=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert summary["matched_count"] == 1
    assert summary["unmatched_amount_cents"] == 1000
def test_aliases_still_work_under_calendar_gates():
    """Alias normalization must still apply when calendar gates are enforced."""
    compile_program()
    write_inputs(
        [src("RFALM3000001", "ACCT8001", "SNR", 650, "20260901", branch="BH01")],
        [action("RFALM3000001", "ACCT8001", "SR", 650, "20260902", "F11", branch="BH01")],
        ["20260901=OPEN", "20260902=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["fare_class"] == "SNR"
    assert summary["matched_amount_cents"] == 650


def test_record_id_match_requires_full_twelve_characters_not_prefix():
    """A shared record-id prefix must not match when every other field is identical."""
    compile_program()
    write_inputs(
        [
            src("RFPREFIX0001", "ACCT2001", "STD", 1000, "20260601", branch="BP01"),
            src("RFPREFIX0002", "ACCT2001", "STD", 1000, "20260601", branch="BP01"),
        ],
        [
            action("RFPREFIX0001", "ACCT2001", "STD", 1000, "20260602", "F01", branch="BP01"),
            action("RFPREFIX000", "ACCT2001", "STD", 1000, "20260602", "F01", branch="BP01"),
        ],
        ["20260601=OPEN", "20260602=OPEN"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert rows[1]["fare_class"] == ""
    assert summary["matched_count"] == 1
    assert summary["unmatched_count"] == 1


def test_action_date_equal_to_source_date_still_matches():
    """An action dated exactly on the source date must still clear when all other gates pass."""
    compile_program()
    write_inputs(
        [src("RFEQDATE0001", "ACCT2101", "EXP", 750, "20260615", branch="BQ01")],
        [action("RFEQDATE0001", "ACCT2101", "EX", 750, "20260615", "F07", branch="BQ01")],
        ["20260615=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["fare_class"] == "EXP"
    assert summary["matched_count"] == 1


def test_unknown_action_alias_stays_unmatched():
    """Only the documented ST, EX, and SR aliases may normalize to canonical fare classes."""
    compile_program()
    write_inputs(
        [src("RFUNKAL00001", "ACCT5101", "STD", 1200, "20260705", branch="BE04")],
        [action("RFUNKAL00001", "ACCT5101", "XX", 1200, "20260706", "F01", branch="BE04")],
        ["20260705=OPEN", "20260706=OPEN"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["fare_class"] == ""
    assert rows[0]["reason"] == "F01"
    assert summary["matched_count"] == 0
    assert summary["unmatched_count"] == 1


def test_source_consumption_trace_schema_and_unmatched_omission():
    """Trace output must use the exact header, trimmed action ids, padded rows, and matched rows only."""
    compile_program()
    write_inputs(
        [src("RFTYPE9", "ACC9", "STD", 500, "20260701", branch="BE01")],
        [
            action("RFTYPE9", "ACC9", "STD", 500, "20260702", "F01", branch="BE01"),
            action("RFTYPE9", "ACC9", "STD", 999, "20260702", "F07", branch="BE01"),
        ],
        ["20260701=OPEN", "20260702=OPEN"],
    )
    rows, summary = run_program()
    trace = read_trace()

    assert TRACE.read_text().splitlines()[0] == "action_record_id,source_row,source_date"
    assert len(trace) == 1
    assert trace[0]["action_record_id"] == "RFTYPE9"
    assert trace[0]["source_row"] == "0001"
    assert trace[0]["source_date"] == "20260701"
    assert rows[1]["status"] == "UNMATCHED"
    assert summary["matched_count"] == 1
    assert summary["unmatched_count"] == 1
