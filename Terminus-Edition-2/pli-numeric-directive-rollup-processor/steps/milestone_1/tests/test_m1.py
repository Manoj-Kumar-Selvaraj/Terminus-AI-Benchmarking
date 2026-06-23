# ruff: noqa: E501
"""Verifier tests for directive validation, aliases, and signed opcode rollup."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
DIRECTIVES = APP / "data/directives.psv"
ACCUMULATORS = APP / "data/accumulators.psv"
WINDOWS = APP / "config/rollup_windows.psv"
RULES = APP / "src/rollup_rules.pli"
REPORT = APP / "out/rollup_report.csv"
SUMMARY = APP / "out/rollup_summary.txt"

DIR_HDR = [
    "line_id",
    "stream_id",
    "value_cents",
    "base_radix",
    "segment_id",
    "ingest_ts",
    "state",
    "kind_code",
    "seq_no",
]
ACC_HDR = [
    "claim_id",
    "line_id",
    "stream_id",
    "value_cents",
    "base_radix",
    "rollup_ts",
    "opcode",
    "segment_id",
    "expected_seq",
    "netting_key",
]


def write_psv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.write_text("|".join(header) + "\n" + "\n".join("|".join(row) for row in rows) + "\n")


def write_rules(state="LIVE", reasons=("ADD", "WATCH", "DONE"), negative="REVERSE,ADJUST"):
    RULES.write_text(
        "\n".join(
            [
                f"DCL ELIGIBLE_STATE CHAR(12) INIT('{state}');",
                "DCL OPEN_ROLLUP_STATE CHAR(8) INIT('OPEN');",
                f"DCL REASON_1 CHAR(12) INIT('{reasons[0]}');",
                f"DCL REASON_2 CHAR(12) INIT('{reasons[1]}');",
                f"DCL REASON_3 CHAR(12) INIT('{reasons[2]}');",
                f"DCL NEGATIVE_OPCODE_CODES CHAR(40) INIT('{negative}');",
                "DCL ALIAS_1 CHAR(20) INIT('hex=>HEX');",
                "DCL ALIAS_2 CHAR(20) INIT('B=>BETA');",
                "DCL ALIAS_3 CHAR(20) INIT('X=>XLINK');",
            ]
        )
        + "\n"
    )


def write_inputs(directives, accumulators):
    write_psv(DIRECTIVES, DIR_HDR, directives)
    write_psv(ACCUMULATORS, ACC_HDR, accumulators)
    write_psv(
        WINDOWS,
        ["stream_id", "open_ts", "close_ts", "state"],
        [["991100", "20260612115900", "20260612123000", "OPEN"]],
    )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    for path in [REPORT, SUMMARY]:
        path.unlink(missing_ok=True)


def run_program():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter="|")
        rows = list(reader)
        columns = reader.fieldnames
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        summary[key] = int(value)
    return rows, summary, columns


def test_validation_strict_keys_consumption_and_totals():
    """Strict matching rolls valid rows and skips malformed numeric, timestamp, state, and opcode cases."""
    write_rules(state="LIVE", reasons=("ADD", "WATCH", "DONE"))
    write_inputs(
        [
            ["R-1", "991100", "10", "FED", "NYC", "20260612120000", "LIVE", "TM", ""],
            ["R-1", "991100", "10", "FED", "NYC", "20260612120100", "LIVE", "TM", ""],
            ["R-2", "991100", "20", "ACH", "NYC", "20260612120200", "BAD", "TM", ""],
            ["R-3", "991100", "30", "SWIFT", "BOS", "BADTS", "LIVE", "TM", ""],
            ["R-4", "991100", "40", "FED", "CHI", "20260612120400", "LIVE", "TM", ""],
        ],
        [
            ["C1", "R-1", "991100", "10", "FED", "20260612120500", " add ", "NYC", "", ""],
            ["C2", "R-1", "991100", "10", "FED", "20260612120600", "ADD", "NYC", "", ""],
            ["C3", "R-2", "991100", "20", "ACH", "20260612120700", "ADD", "NYC", "", ""],
            ["C4", "R-3", "991100", "30", "SWIFT", "20260612120800", "WATCH", "BOS", "", ""],
            ["C5", "R-4", "991100", "XX", "FED", "20260612120900", "ADD", "CHI", "", ""],
            ["C6", "R-4", "991100", "40", "FED", "BADTS", "ADD", "CHI", "", ""],
            ["C7", "R-4", "991100", "40", "FED", "20260612121000", "NOPE", "CHI", "", ""],
        ],
    )

    rows, summary, columns = run_program()

    assert columns == [
        "claim_id",
        "line_id",
        "stream_id",
        "check_segment",
        "segment_id",
        "value_cents",
        "opcode",
        "status",
    ]
    assert [row["status"] for row in rows] == ["ROLLED", "ROLLED", "SKIPPED", "SKIPPED", "SKIPPED", "SKIPPED", "SKIPPED"]
    assert [row["segment_id"] for row in rows] == ["NYC", "NYC", "", "", "", "", ""]
    assert summary == {
        "rolled_count": 2,
        "rolled_total_cents": 20,
        "skipped_count": 5,
        "skipped_total_cents": 130,
    }


def test_full_key_prevents_prefix_stream_and_segment_shortcuts():
    """Prefix line matches and nonmatching stream or segment values remain skipped."""
    write_rules()
    write_inputs(
        [
            ["ABCDE-REAL", "991100", "70", "FED", "NYC", "20260612120000", "LIVE", "TM", ""],
            ["R-2", "991200", "80", "FED", "LAX", "20260612120100", "LIVE", "TM", ""],
        ],
        [
            ["PFX", "ABCDE-NOPE", "991100", "70", "FED", "20260612120500", "ADD", "NYC", "", ""],
            ["STREAM", "R-2", "991999", "80", "FED", "20260612120500", "ADD", "LAX", "", ""],
            ["SEG", "R-2", "991200", "80", "FED", "20260612120500", "ADD", "NYC", "", ""],
        ],
    )

    rows, summary, _ = run_program()

    assert [row["status"] for row in rows] == ["SKIPPED", "SKIPPED", "SKIPPED"]
    assert all(row["segment_id"] == "" for row in rows)
    assert summary["skipped_total_cents"] == 230


def test_signed_opcode_direction_and_absolute_summary_totals():
    """Negative opcodes require negative cents; summary totals use absolute values."""
    write_rules(state="LIVE", reasons=("ADD", "REVERSE", "DONE"))
    write_inputs(
        [
            ["R-P", "991100", "25", "FED", "NYC", "20260612120000", "LIVE", "TM", ""],
            ["R-N", "991100", "-15", "FED", "NYC", "20260612120100", "LIVE", "TM", ""],
        ],
        [
            ["POS", "R-P", "991100", "25", "FED", "20260612120500", "ADD", "NYC", "", ""],
            ["NEG", "R-N", "991100", "-15", "FED", "20260612120600", "REVERSE", "NYC", "", ""],
            ["BAD", "R-P", "991100", "-25", "FED", "20260612120700", "ADD", "NYC", "", ""],
        ],
    )

    rows, summary, _ = run_program()

    assert [row["status"] for row in rows] == ["ROLLED", "ROLLED", "SKIPPED"]
    assert summary == {
        "rolled_count": 2,
        "rolled_total_cents": 40,
        "skipped_count": 1,
        "skipped_total_cents": 25,
    }


def test_aliases_normalize_base_radix_and_segment_on_both_sides():
    """Aliases in either input match canonically and emit canonical directive segment values."""
    write_rules(state="LIVE", reasons=("GO", "CHK", "WAIT"), negative="REVERSE")
    RULES.write_text(
        RULES.read_text()
        .replace("hex=>HEX", " f => FED ")
        .replace("B=>BETA", " a => ACH ")
        .replace("X=>XLINK", " s => SWIFT ")
    )
    write_inputs(
        [
            ["R-9", "991100", "99", "f", "f", "20260612120000", "LIVE", "tm", ""],
            ["R-8", "991100", "88", "ACH", "ACH", "20260612120100", "LIVE", "tm", ""],
        ],
        [
            ["C9", "R-9", "991100", "99", "FED", "20260612120500", "GO", "FED", "", ""],
            ["C8", "R-8", "991100", "88", "a", "20260612120500", "CHK", "a", "", ""],
        ],
    )

    rows, _, _ = run_program()

    assert [row["status"] for row in rows] == ["ROLLED", "ROLLED"]
    assert [row["segment_id"] for row in rows] == ["FED", "ACH"]


def test_consumed_directive_blocks_second_claim():
    """A rolled directive cannot satisfy a later accumulator for the same keys."""
    write_rules(state="LIVE", reasons=("GO", "CHK", "WAIT"))
    write_inputs(
        [["R-ONE", "991100", "75", "FED", "FED", "20260612120000", "LIVE", "tm", ""]],
        [
            ["FIRST", "R-ONE", "991100", "75", "FED", "20260612120500", "GO", "FED", "", ""],
            ["SECOND", "R-ONE", "991100", "75", "FED", "20260612120600", "CHK", "f", "", ""],
            ["UNKNOWN", "R-ONE", "991100", "75", "ZZZ", "20260612120700", "GO", "FED", "", ""],
        ],
    )

    rows, _, _ = run_program()

    assert [row["status"] for row in rows] == ["ROLLED", "SKIPPED", "SKIPPED"]
    assert [row["segment_id"] for row in rows] == ["FED", "", ""]
