# ruff: noqa: E501
"""Verifier tests for stream capacity, directive holds, and restart commits."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
DIRECTIVES = APP / "data/directives.psv"
ACCUMULATORS = APP / "data/accumulators.psv"
WINDOWS = APP / "config/rollup_windows.psv"
CALENDAR = APP / "config/rollup_calendar.psv"
CAPACITY = APP / "config/stream_capacity.psv"
HOLDS = APP / "config/directive_holds.psv"
COMMITS = APP / "state/rollup_commits.psv"
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
        [
            ["991100", "20260612110000", "20260612190000", "OPEN"],
            ["991200", "20260612110000", "20260612190000", "OPEN"],
        ],
    )
    write_psv(CALENDAR, ["business_date", "cutoff_ts", "state"], [["20260612", "20260612190000", "OPEN"]])
    write_psv(LEDGER, ["claim_id", "line_id", "stream_id", "segment_id", "base_radix", "value_cents", "status"], [])
    CHECKPOINT.write_text("0\n")
    write_psv(
        WEIGHTS,
        ["base_radix", "weight_numerator", "weight_denominator", "state"],
        [["FED", "1", "1", "ACTIVE"]],
    )


def run_batch():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    report = list(csv.DictReader(REPORT.open(), delimiter="|"))
    exceptions = list(csv.DictReader((APP / "out/rollup_exceptions.csv").open(), delimiter="|"))
    positions = list(csv.DictReader((APP / "out/capacity_position.txt").open(), delimiter="|"))
    commits = list(csv.DictReader((APP / "out/rollup_commits.psv").open(), delimiter="|"))
    return report, exceptions, positions, commits


def test_capacity_overflow_holds_row_but_later_stream_continues() -> None:
    """Capacity limits apply per stream and canonical radix in claim order."""
    setup_common()
    write_psv(CAPACITY, ["stream_id", "base_radix", "limit_cents"], [["991100", "FED", "100"]])
    write_psv(HOLDS, ["claim_id", "hold_reason"], [])
    write_psv(COMMITS, ["stream_id", "base_radix", "segment_id", "rolled_count", "rolled_total_cents", "committed_ts"], [])
    write_psv(
        CONTROLS,
        ["stream_id", "base_radix", "segment_id", "expected_count", "expected_weighted_cents", "tolerance_cents"],
        [["991100", "FED", "NYC", "1", "60", "0"], ["991200", "FED", "LAX", "1", "50", "0"]],
    )
    write_psv(
        DIRECTIVES,
        DIR_HDR,
        [
            ["D1", "991100", "60", "FED", "NYC", "20260612120000", "OPEN", "TM", ""],
            ["D2", "991100", "50", "FED", "NYC", "20260612120100", "OPEN", "TM", ""],
            ["D3", "991200", "50", "FED", "LAX", "20260612120200", "OPEN", "TM", ""],
        ],
    )
    write_psv(
        ACCUMULATORS,
        ACC_HDR,
        [
            ["A1", "D1", "991100", "60", "FED", "20260612121000", "OK", "NYC", "", ""],
            ["A2", "D2", "991100", "50", "FED", "20260612121100", "OK", "NYC", "", ""],
            ["A3", "D3", "991200", "50", "FED", "20260612121200", "OK", "LAX", "", ""],
        ],
    )

    report, exceptions, positions, _ = run_batch()

    assert [row["status"] for row in report] == ["ROLLED", "SKIPPED", "ROLLED"]
    assert exceptions[0]["reason"] == "CAPACITY_HOLD"
    cap = next(row for row in positions if row["stream_id"] == "991100")
    assert cap["used_cents"] == "60"
    assert cap["remaining_cents"] == "40"


def test_directive_hold_leaves_directive_available_for_later_claims() -> None:
    """Held claim rows skip before matching; other claims may still roll."""
    setup_common()
    write_psv(CAPACITY, ["stream_id", "base_radix", "limit_cents"], [])
    write_psv(HOLDS, ["claim_id", "hold_reason"], [["HOLDME", "LEGAL"]])
    write_psv(COMMITS, ["stream_id", "base_radix", "segment_id", "rolled_count", "rolled_total_cents", "committed_ts"], [])
    write_psv(CONTROLS, ["stream_id", "base_radix", "segment_id", "expected_count", "expected_weighted_cents", "tolerance_cents"], [["991100", "FED", "NYC", "1", "40", "0"]])
    write_psv(
        DIRECTIVES,
        DIR_HDR,
        [["D1", "991100", "40", "FED", "NYC", "20260612120000", "OPEN", "TM", ""]],
    )
    write_psv(
        ACCUMULATORS,
        ACC_HDR,
        [
            ["HOLDME", "D1", "991100", "40", "FED", "20260612121000", "OK", "NYC", "", ""],
            ["FREE", "D1", "991100", "40", "FED", "20260612121100", "OK", "NYC", "", ""],
        ],
    )

    report, exceptions, _, _ = run_batch()

    assert [row["status"] for row in report] == ["SKIPPED", "ROLLED"]
    assert exceptions[0]["reason"] == "DIRECTIVE_HOLD"


def test_restart_commits_are_idempotent_on_rerun() -> None:
    """Already committed groups are not appended again on rerun."""
    setup_common()
    write_psv(CAPACITY, ["stream_id", "base_radix", "limit_cents"], [])
    write_psv(HOLDS, ["claim_id", "hold_reason"], [])
    write_psv(
        COMMITS,
        ["stream_id", "base_radix", "segment_id", "rolled_count", "rolled_total_cents", "committed_ts"],
        [["991100", "FED", "NYC", "1", "40", "20260612180000"]],
    )
    write_psv(
        CONTROLS,
        ["stream_id", "base_radix", "segment_id", "expected_count", "expected_weighted_cents", "tolerance_cents"],
        [["991100", "FED", "NYC", "1", "40", "0"]],
    )
    write_psv(
        DIRECTIVES,
        DIR_HDR,
        [["D1", "991100", "40", "FED", "NYC", "20260612120000", "OPEN", "TM", ""]],
    )
    write_psv(
        ACCUMULATORS,
        ACC_HDR,
        [["A1", "D1", "991100", "40", "FED", "20260612121000", "OK", "NYC", "", ""]],
    )

    _, _, _, commits = run_batch()

    assert len(commits) == 1
    assert commits[0]["stream_id"] == "991100"
