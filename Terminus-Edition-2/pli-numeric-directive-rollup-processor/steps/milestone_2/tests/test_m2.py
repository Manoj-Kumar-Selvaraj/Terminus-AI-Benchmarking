# ruff: noqa: E501
"""Verifier tests for rollup windows, weighted controls, downstream, and group downgrade."""

import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
DIRECTIVES = APP / "data/directives.psv"
ACCUMULATORS = APP / "data/accumulators.psv"
WINDOWS = APP / "config/rollup_windows.psv"
RULES = APP / "src/rollup_rules.pli"
WEIGHTS = APP / "config/radix_weights.psv"
CONTROLS = APP / "config/control_totals.psv"
REPORT = APP / "out/rollup_report.csv"
CONTROL_REPORT = APP / "out/rollup_controls.psv"
DOWN = APP / "out/downstream"

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


def write_rules():
    RULES.write_text(
        "DCL ELIGIBLE_STATE CHAR(12) INIT('OPEN');\n"
        "DCL OPEN_ROLLUP_STATE CHAR(8) INIT('GREEN');\n"
        "DCL REASON_1 CHAR(12) INIT('OK');\n"
        "DCL REASON_2 CHAR(12) INIT('WATCH');\n"
        "DCL REASON_3 CHAR(12) INIT('DONE');\n"
        "DCL NEGATIVE_OPCODE_CODES CHAR(40) INIT('REVERSE,ADJUST');\n"
        "DCL ALIAS_1 CHAR(20) INIT('f=>FED');\n"
        "DCL ALIAS_2 CHAR(20) INIT('a=>ACH');\n"
        "DCL ALIAS_3 CHAR(20) INIT('s=>SWIFT');\n"
    )


def write_common_inputs():
    write_rules()
    write_psv(
        DIRECTIVES,
        DIR_HDR,
        [
            ["R1", "991100", "100", "f", "NYC", "20260612120000", "OPEN", "TM", ""],
            ["R2", "991100", "200", "FED", "NYC", "20260612120100", "OPEN", "TM", ""],
            ["R3", "991200", "90", "a", "BOS", "20260612120200", "OPEN", "TM", ""],
            ["R4", "991200", "60", "ACH", "BOS", "20260612120300", "OPEN", "TM", ""],
            ["R5", "991300", "70", "FED", "LAX", "20260612140000", "OPEN", "TM", ""],
        ],
    )
    write_psv(
        ACCUMULATORS,
        ACC_HDR,
        [
            ["C1", "R1", "991100", "100", "FED", "20260612120500", "OK", "NYC", "", ""],
            ["C2", "R2", "991100", "200", "FED", "20260612120600", "WATCH", "NYC", "", ""],
            ["C3", "R3", "991200", "90", "ACH", "20260612120700", "OK", "BOS", "", ""],
            ["C4", "R4", "991200", "60", "a", "20260612120800", "DONE", "BOS", "", ""],
            ["C5", "R5", "991300", "70", "FED", "20260612140500", "OK", "LAX", "", ""],
        ],
    )
    write_psv(
        WINDOWS,
        ["stream_id", "open_ts", "close_ts", "state"],
        [
            ["991100", "20260612115900", "20260612123000", "GREEN"],
            ["991200", "20260612115900", "20260612123000", "green"],
            ["991300", "20260612115900", "20260612123000", "GREEN"],
        ],
    )
    write_psv(
        WEIGHTS,
        ["base_radix", "weight_numerator", "weight_denominator", "state"],
        [["FED", "2", "1", "ACTIVE"], ["ACH", "3", "2", "ACTIVE"]],
    )
    write_psv(
        CONTROLS,
        ["stream_id", "base_radix", "segment_id", "expected_count", "expected_weighted_cents", "tolerance_cents"],
        [
            ["991100", "FED", "NYC", "2", "600", "0"],
            ["991200", "ACH", "BOS", "2", "225", "5"],
        ],
    )
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    for path in [REPORT, CONTROL_REPORT]:
        path.unlink(missing_ok=True)


def run_program():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="|"))
    with CONTROL_REPORT.open(newline="") as handle:
        controls = list(csv.DictReader(handle, delimiter="|"))
    return rows, controls


def test_windows_and_weighted_control_totals_are_enforced():
    """Open windows roll rows and emit exact weighted control arithmetic."""
    write_common_inputs()

    rows, controls = run_program()
    by_group = {(row["stream_id"], row["base_radix"], row["segment_id"]): row for row in controls}

    assert [row["status"] for row in rows] == ["ROLLED", "ROLLED", "ROLLED", "ROLLED", "SKIPPED"]
    assert by_group[("991100", "FED", "NYC")]["actual_count"] == "2"
    assert by_group[("991100", "FED", "NYC")]["actual_weighted_cents"] == "600"
    assert by_group[("991100", "FED", "NYC")]["status"] == "CONTROL_OK"
    assert by_group[("991200", "ACH", "BOS")]["actual_weighted_cents"] == "225"
    assert by_group[("991200", "ACH", "BOS")]["status"] == "CONTROL_OK"


def test_ingest_ts_outside_window_skips_even_when_rollup_ts_is_inside():
    """Both ingest_ts and rollup_ts must fall inside the stream window."""
    write_common_inputs()
    write_psv(
        DIRECTIVES,
        DIR_HDR,
        [
            ["R-IN", "991100", "50", "FED", "NYC", "20260612110000", "OPEN", "TM", ""],
            ["R-OK", "991100", "60", "FED", "NYC", "20260612120000", "OPEN", "TM", ""],
        ],
    )
    write_psv(
        ACCUMULATORS,
        ACC_HDR,
        [
            ["C-IN", "R-IN", "991100", "50", "FED", "20260612120500", "OK", "NYC", "", ""],
            ["C-OK", "R-OK", "991100", "60", "FED", "20260612120600", "OK", "NYC", "", ""],
        ],
    )
    write_psv(
        CONTROLS,
        ["stream_id", "base_radix", "segment_id", "expected_count", "expected_weighted_cents", "tolerance_cents"],
        [["991100", "FED", "NYC", "1", "120", "0"]],
    )

    rows, _ = run_program()

    assert [row["status"] for row in rows] == ["SKIPPED", "ROLLED"]


def test_control_held_groups_downgrade_report_rows():
    """Rows in CONTROL_HELD groups appear as SKIPPED with blank segment_id in the report."""
    write_common_inputs()
    write_psv(
        WEIGHTS,
        ["base_radix", "weight_numerator", "weight_denominator", "state"],
        [["FED", "2", "1", "ACTIVE"], ["ACH", "2", "3", "ACTIVE"]],
    )
    write_psv(
        CONTROLS,
        ["stream_id", "base_radix", "segment_id", "expected_count", "expected_weighted_cents", "tolerance_cents"],
        [["991100", "FED", "NYC", "2", "600", "0"]],
    )

    rows, controls = run_program()
    held = next(row for row in controls if row["stream_id"] == "991200")

    assert held["status"] == "CONTROL_HELD"
    assert rows[2]["status"] == "SKIPPED"
    assert rows[3]["status"] == "SKIPPED"
    assert rows[2]["segment_id"] == ""
    assert rows[3]["segment_id"] == ""


def test_downstream_files_split_accepted_and_rejected_rows():
    """Downstream delivery emits accepted groups, rejected rows, and a strict manifest."""
    write_rules()
    write_psv(
        DIRECTIVES,
        DIR_HDR,
        [
            ["A1", "991100", "100", "f", "NYC", "20260612120000", "OPEN", "TM", ""],
            ["A2", "991100", "200", "FED", "NYC", "20260612120100", "OPEN", "TM", ""],
            ["H1", "991200", "90", "a", "BOS", "20260612120200", "OPEN", "TM", ""],
            ["BAD", "991300", "70", "FED", "LAX", "20260612120200", "OPEN", "TM", ""],
        ],
    )
    write_psv(
        ACCUMULATORS,
        ACC_HDR,
        [
            ["CA1", "A1", "991100", "100", "FED", "20260612120500", "OK", "NYC", "", ""],
            ["CA2", "A2", "991100", "200", "FED", "20260612120600", "WATCH", "NYC", "", ""],
            ["CH1", "H1", "991200", "90", "ACH", "20260612120700", "OK", "BOS", "", ""],
            ["CSKIP", "BAD", "991300", "70", "FED", "20260612120700", "NOPE", "LAX", "", ""],
        ],
    )
    write_psv(
        WINDOWS,
        ["stream_id", "open_ts", "close_ts", "state"],
        [
            ["991100", "20260612115900", "20260612123000", "GREEN"],
            ["991200", "20260612115900", "20260612123000", "GREEN"],
            ["991300", "20260612115900", "20260612123000", "GREEN"],
        ],
    )
    write_psv(
        WEIGHTS,
        ["base_radix", "weight_numerator", "weight_denominator", "state"],
        [["FED", "2", "1", "ACTIVE"], ["ACH", "3", "2", "ACTIVE"]],
    )
    write_psv(
        CONTROLS,
        ["stream_id", "base_radix", "segment_id", "expected_count", "expected_weighted_cents", "tolerance_cents"],
        [["991100", "FED", "NYC", "2", "600", "0"]],
    )
    if DOWN.exists():
        for path in DOWN.glob("*"):
            path.unlink()

    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    accepted = list(csv.DictReader((DOWN / "accepted_rollups.psv").open(), delimiter="|"))
    rejected = list(csv.DictReader((DOWN / "rejected_rollups.psv").open(), delimiter="|"))
    manifest = json.loads((DOWN / "manifest.json").read_text())

    assert accepted == [
        {
            "stream_id": "991100",
            "base_radix": "FED",
            "segment_id": "NYC",
            "rolled_count": "2",
            "rolled_total_cents": "300",
            "weighted_total_cents": "600",
        }
    ]
    assert [row["reject_code"] for row in rejected] == ["CONTROL_HELD", "SKIPPED_INPUT"]
    assert manifest == {
        "schema_version": "rollup-downstream/v1",
        "accepted_groups": 1,
        "accepted_rows": 2,
        "rejected_rows": 2,
        "accepted_total_cents": 300,
        "weighted_total_cents": 600,
    }
