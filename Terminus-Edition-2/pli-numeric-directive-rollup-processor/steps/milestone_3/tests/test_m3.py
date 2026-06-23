# ruff: noqa: E501
"""Verifier tests for rollup ledger replay and settlement cutoff."""

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
LEDGER_HDR = [
    "claim_id",
    "line_id",
    "stream_id",
    "segment_id",
    "base_radix",
    "value_cents",
    "status",
]


def write_psv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("|".join(header) + "\n" + "\n".join("|".join(row) for row in rows) + "\n")


def write_common() -> None:
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
    write_psv(WEIGHTS, ["base_radix", "weight_numerator", "weight_denominator", "state"], [["FED", "1", "1", "ACTIVE"]])
    write_psv(
        CALENDAR,
        ["business_date", "cutoff_ts", "state"],
        [["20260612", "20260612180000", "OPEN"]],
    )


def run_batch():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    report = list(csv.DictReader(REPORT.open(), delimiter="|"))
    ledger = list(csv.DictReader((APP / "out/rollup_ledger.psv").open(), delimiter="|"))
    restart = dict(
        line.split("=", 1) for line in (APP / "out/restart_audit.txt").read_text().splitlines()
    )
    exceptions = list(csv.DictReader((APP / "out/rollup_exceptions.csv").open(), delimiter="|"))
    return report, ledger, restart, exceptions


def test_committed_ledger_rows_suppress_replay_and_new_rows_append_once() -> None:
    """M3 returns replay duplicates and appends only new committed rows."""
    write_common()
    write_psv(
        LEDGER,
        LEDGER_HDR,
        [["OLD", "C-1", "991100", "NYC", "FED", "30", "COMMITTED"]],
    )
    CHECKPOINT.write_text("1\n")
    write_psv(
        DIRECTIVES,
        DIR_HDR,
        [
            ["C-1", "991100", "30", "FED", "NYC", "20260612120000", "OPEN", "TM", ""],
            ["C-2", "991100", "40", "FED", "NYC", "20260612120100", "OPEN", "TM", ""],
        ],
    )
    write_psv(
        ACCUMULATORS,
        ACC_HDR,
        [
            ["OLD", "C-1", "991100", "30", "FED", "20260612121000", "OK", "NYC", "", ""],
            ["NEW", "C-2", "991100", "40", "FED", "20260612121100", "OK", "NYC", "", ""],
        ],
    )
    write_psv(CONTROLS, ["stream_id", "base_radix", "segment_id", "expected_count", "expected_weighted_cents", "tolerance_cents"], [["991100", "FED", "NYC", "1", "40", "0"]])

    report, ledger, restart, exceptions = run_batch()

    assert [row["status"] for row in report] == ["SKIPPED", "ROLLED"]
    assert [row["claim_id"] for row in ledger] == ["OLD", "NEW"]
    assert restart == {"checkpoint_status": "OK", "committed_rows": "1"}
    assert exceptions[0]["reason"] == "REPLAY_DUPLICATE"


def test_missing_stale_and_ahead_checkpoints_do_not_skip_valid_processing() -> None:
    """Checkpoint anomalies are reported but do not suppress valid non-replay rollups."""
    for marker, expected in [(None, "MISSING"), ("bad\n", "STALE"), ("9\n", "AHEAD")]:
        write_common()
        write_psv(LEDGER, LEDGER_HDR, [])
        if marker is None:
            CHECKPOINT.unlink(missing_ok=True)
        else:
            CHECKPOINT.write_text(marker)
        write_psv(
            DIRECTIVES,
            DIR_HDR,
            [["C-X", "991100", "15", "FED", "NYC", "20260612120000", "OPEN", "TM", ""]],
        )
        write_psv(
            ACCUMULATORS,
            ACC_HDR,
            [["A-X", "C-X", "991100", "15", "FED", "20260612121000", "OK", "NYC", "", ""]],
        )
        write_psv(CONTROLS, ["stream_id", "base_radix", "segment_id", "expected_count", "expected_weighted_cents", "tolerance_cents"], [["991100", "FED", "NYC", "1", "15", "0"]])

        report, ledger, restart, _ = run_batch()

        assert report[0]["status"] == "ROLLED"
        assert ledger[-1]["claim_id"] == "A-X"
        assert restart["checkpoint_status"] == expected


def test_cutoff_rejects_boundary_timestamp_after_calendar_cutoff() -> None:
    """Both ingest_ts and rollup_ts must be on or before the OPEN day cutoff."""
    write_common()
    write_psv(LEDGER, LEDGER_HDR, [])
    CHECKPOINT.write_text("0\n")
    write_psv(
        DIRECTIVES,
        DIR_HDR,
        [
            ["LATE", "991100", "20", "FED", "NYC", "20260612180000", "OPEN", "TM", ""],
            ["OK", "991100", "25", "FED", "NYC", "20260612170000", "OPEN", "TM", ""],
        ],
    )
    write_psv(
        ACCUMULATORS,
        ACC_HDR,
        [
            ["L1", "LATE", "991100", "20", "FED", "20260612180500", "OK", "NYC", "", ""],
            ["L2", "OK", "991100", "25", "FED", "20260612171000", "OK", "NYC", "", ""],
        ],
    )
    write_psv(CONTROLS, ["stream_id", "base_radix", "segment_id", "expected_count", "expected_weighted_cents", "tolerance_cents"], [["991100", "FED", "NYC", "1", "25", "0"]])

    report, _, _, _ = run_batch()

    assert [row["status"] for row in report] == ["SKIPPED", "ROLLED"]
