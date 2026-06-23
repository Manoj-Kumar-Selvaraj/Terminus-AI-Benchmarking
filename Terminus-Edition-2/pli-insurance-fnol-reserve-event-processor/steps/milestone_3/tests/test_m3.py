# ruff: noqa: E501
"""Verifier tests for insurance FNOL reserve adjustment PL/I task — milestone 3."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
CLAIMS = [
    "claim_id",
    "policy_id",
    "loss_unit",
    "coverage_type",
    "reserve_cents",
    "fnol_ts",
    "status",
    "state_code",
]
ADJUSTMENTS = [
    "action_id",
    "claim_id",
    "policy_id",
    "loss_unit",
    "coverage_type",
    "reserve_cents",
    "adjust_ts",
    "reason",
    "state_code",
]
LEDGER = [
    "action_id",
    "claim_id",
    "policy_id",
    "loss_unit",
    "coverage_type",
    "reserve_cents",
    "status",
]
REPORT = APP / "out/reserve_adjustment_report.csv"
SUMMARY = APP / "out/reserve_adjustment_summary.txt"


def write_psv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("|".join(header) + "\n" + "\n".join("|".join(row) for row in rows) + "\n")


def write_common() -> None:
    (APP / "src/fnol_rules.pli").write_text(
        "DCL ELIGIBLE_STATUS CHAR(12) INIT('OPEN');\n"
        "DCL OPEN_WINDOW_STATUS CHAR(8) INIT('OPEN');\n"
        "DCL REASON_A CHAR(12) INIT('RAISE');\n"
        "DCL REASON_B CHAR(12) INIT('LOWER');\n"
        "DCL REASON_C CHAR(12) INIT('CLOSE');\n"
        "DCL NEGATIVE_REASON_CODES CHAR(40) INIT('LOWER,CLOSE');\n"
        "DCL ALIAS_1 CHAR(20) INIT('A=>AUTO');\n"
    )
    write_psv(
        APP / "config/windows.psv",
        ["loss_unit", "open_ts", "close_ts", "state"],
        [["S-L", "20260528110000", "20260528170000", "OPEN"]],
    )


def run_batch() -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, str]]:
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    report = list(csv.DictReader(REPORT.open(), delimiter="|"))
    ledger = list(csv.DictReader((APP / "out/reserve_ledger.psv").open(), delimiter="|"))
    restart = dict(
        line.split("=", 1) for line in (APP / "out/restart_audit.txt").read_text().splitlines()
    )
    return report, ledger, restart


def test_committed_ledger_rows_suppress_replay_and_new_rows_append_once() -> None:
    """M3 returns replay duplicates and appends only new committed rows."""
    write_common()
    write_psv(
        APP / "state/reserve_ledger.psv",
        LEDGER,
        [["OLD", "C-1", "P-1", "S-L", "AUTO", "30", "COMMITTED"]],
    )
    (APP / "state/restart_checkpoint.txt").write_text("1\n")
    write_psv(
        APP / "data/claims.psv",
        CLAIMS,
        [
            ["C-1", "P-1", "S-L", "AUTO", "30", "20260528120000", "OPEN", "L1"],
            ["C-2", "P-2", "S-L", "AUTO", "40", "20260528120100", "OPEN", "L2"],
        ],
    )
    write_psv(
        APP / "data/adjustments.psv",
        ADJUSTMENTS,
        [
            ["OLD", "C-1", "P-1", "S-L", "A", "30", "20260528121000", "RAISE", "L1"],
            ["NEW", "C-2", "P-2", "S-L", "A", "40", "20260528121100", "RAISE", "L2"],
        ],
    )

    report, ledger, restart = run_batch()

    assert [row["status"] for row in report] == ["UNMATCHED", "MATCHED"]
    assert [row["action_id"] for row in ledger] == ["OLD", "NEW"]
    assert restart == {"checkpoint_status": "OK", "committed_rows": "1"}


def test_missing_stale_and_ahead_checkpoints_do_not_skip_valid_processing() -> None:
    """Checkpoint anomalies are reported but do not suppress valid non-replay adjustments."""
    for marker, expected in [(None, "MISSING"), ("bad\n", "STALE"), ("9\n", "AHEAD")]:
        write_common()
        write_psv(APP / "state/reserve_ledger.psv", LEDGER, [])
        checkpoint = APP / "state/restart_checkpoint.txt"
        if marker is None:
            checkpoint.unlink(missing_ok=True)
        else:
            checkpoint.write_text(marker)
        write_psv(
            APP / "data/claims.psv",
            CLAIMS,
            [["C-X", "P-X", "S-L", "AUTO", "15", "20260528120000", "OPEN", "L1"]],
        )
        write_psv(
            APP / "data/adjustments.psv",
            ADJUSTMENTS,
            [["A-X", "C-X", "P-X", "S-L", "A", "15", "20260528121000", "RAISE", "L1"]],
        )

        report, ledger, restart = run_batch()

        assert report[0]["status"] == "MATCHED"
        assert ledger[-1]["action_id"] == "A-X"
        assert restart["checkpoint_status"] == expected
