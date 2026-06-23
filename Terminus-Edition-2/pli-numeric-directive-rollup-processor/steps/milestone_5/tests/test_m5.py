# ruff: noqa: E501
"""Verifier tests for directive sequence locks and cross-claim netting."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
DIRECTIVES = APP / "data/directives.psv"
ACCUMULATORS = APP / "data/accumulators.psv"
WINDOWS = APP / "config/rollup_windows.psv"
CALENDAR = APP / "config/rollup_calendar.psv"
WEIGHTS = APP / "config/radix_weights.psv"
CONTROLS = APP / "config/control_totals.psv"
LEDGER = APP / "state/rollup_ledger.psv"
CHECKPOINT = APP / "state/restart_checkpoint.txt"
RULES = APP / "src/rollup_rules.pli"
REPORT = APP / "out/rollup_report.csv"

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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("|".join(header) + "\n" + "\n".join("|".join(row) for row in rows) + "\n")


def setup_common() -> None:
    RULES.write_text(
        "DCL ELIGIBLE_STATE CHAR(12) INIT('OPEN');\n"
        "DCL OPEN_ROLLUP_STATE CHAR(8) INIT('OPEN');\n"
        "DCL REASON_1 CHAR(12) INIT('OK');\n"
        "DCL REASON_2 CHAR(12) INIT('WATCH');\n"
        "DCL REASON_3 CHAR(12) INIT('DONE');\n"
        "DCL NEGATIVE_OPCODE_CODES CHAR(40) INIT('REVERSE,ADJUST');\n"
        "DCL ALIAS_1 CHAR(20) INIT('f=>FED');\n"
    )
    write_psv(
        WINDOWS,
        ["stream_id", "open_ts", "close_ts", "state"],
        [["991100", "20260612110000", "20260612190000", "OPEN"]],
    )
    write_psv(CALENDAR, ["business_date", "cutoff_ts", "state"], [["20260612", "20260612190000", "OPEN"]])
    write_psv(LEDGER, ["claim_id", "line_id", "stream_id", "segment_id", "base_radix", "value_cents", "status"], [])
    CHECKPOINT.write_text("0\n")
    write_psv(
        WEIGHTS,
        ["base_radix", "weight_numerator", "weight_denominator", "state"],
        [["FED", "1", "1", "ACTIVE"]],
    )
    write_psv(
        CONTROLS,
        ["stream_id", "base_radix", "segment_id", "expected_count", "expected_weighted_cents", "tolerance_cents"],
        [["991100", "FED", "NYC", "2", "0", "0"]],
    )


def run_batch():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    report = list(csv.DictReader(REPORT.open(), delimiter="|"))
    exceptions = list(csv.DictReader((APP / "out/rollup_exceptions.csv").open(), delimiter="|"))
    return report, exceptions


def test_sequence_gap_blocks_out_of_order_match() -> None:
    """Lower unused seq_no must be consumed before higher sequences roll."""
    setup_common()
    write_psv(
        DIRECTIVES,
        DIR_HDR,
        [
            ["D2", "991100", "20", "FED", "NYC", "20260612120000", "OPEN", "TM", "2"],
            ["D1", "991100", "10", "FED", "NYC", "20260612120100", "OPEN", "TM", "1"],
        ],
    )
    write_psv(
        ACCUMULATORS,
        ACC_HDR,
        [
            ["A2", "D2", "991100", "20", "FED", "20260612121000", "OK", "NYC", "2", ""],
            ["A1", "D1", "991100", "10", "FED", "20260612121100", "OK", "NYC", "1", ""],
        ],
    )
    write_psv(CONTROLS, ["stream_id", "base_radix", "segment_id", "expected_count", "expected_weighted_cents", "tolerance_cents"], [["991100", "FED", "NYC", "1", "10", "0"]])

    report, _ = run_batch()

    assert [row["status"] for row in report] == ["SKIPPED", "ROLLED"]


def test_non_zero_netting_group_downgrades_to_skipped() -> None:
    """Netting keys must net to weighted zero before rows stay rolled."""
    setup_common()
    write_psv(
        DIRECTIVES,
        DIR_HDR,
        [
            ["D1", "991100", "30", "FED", "NYC", "20260612120000", "OPEN", "TM", "1"],
            ["D2", "991100", "10", "FED", "NYC", "20260612120100", "OPEN", "TM", "2"],
        ],
    )
    write_psv(
        ACCUMULATORS,
        ACC_HDR,
        [
            ["A1", "D1", "991100", "30", "FED", "20260612121000", "OK", "NYC", "1", "NET-A"],
            ["A2", "D2", "991100", "10", "FED", "20260612121100", "OK", "NYC", "2", "NET-A"],
        ],
    )

    report, exceptions = run_batch()

    assert all(row["status"] == "SKIPPED" for row in report)
    assert all(row["segment_id"] == "" for row in report)
    assert exceptions[0]["reason"] == "NETTING_HOLD"


def test_zero_netting_group_remains_rolled() -> None:
    """Balanced netting keys with weighted total zero stay rolled."""
    setup_common()
    write_psv(
        CONTROLS,
        ["stream_id", "base_radix", "segment_id", "expected_count", "expected_weighted_cents", "tolerance_cents"],
        [["991100", "FED", "NYC", "2", "60", "0"]],
    )
    write_psv(
        DIRECTIVES,
        DIR_HDR,
        [
            ["D1", "991100", "30", "FED", "NYC", "20260612120000", "OPEN", "TM", "1"],
            ["D2", "991100", "-30", "FED", "NYC", "20260612120100", "OPEN", "TM", "2"],
        ],
    )
    write_psv(
        ACCUMULATORS,
        ACC_HDR,
        [
            ["A1", "D1", "991100", "30", "FED", "20260612121000", "OK", "NYC", "1", "NET-Z"],
            ["A2", "D2", "991100", "-30", "FED", "20260612121100", "REVERSE", "NYC", "2", "NET-Z"],
        ],
    )

    report, exceptions = run_batch()

    assert [row["status"] for row in report] == ["ROLLED", "ROLLED"]
    assert exceptions == []
