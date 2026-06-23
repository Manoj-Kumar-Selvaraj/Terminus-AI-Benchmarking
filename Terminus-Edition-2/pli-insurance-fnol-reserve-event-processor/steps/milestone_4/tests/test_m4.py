# ruff: noqa: E501
"""Verifier tests for insurance FNOL reserve adjustment PL/I task — milestone 4."""

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


def write_psv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("|".join(header) + "\n" + "\n".join("|".join(row) for row in rows) + "\n")


def setup_common() -> None:
    (APP / "src/fnol_rules.pli").write_text(
        "DCL ELIGIBLE_STATUS CHAR(12) INIT('OPEN');\n"
        "DCL OPEN_WINDOW_STATUS CHAR(8) INIT('OPEN');\n"
        "DCL REASON_A CHAR(12) INIT('RAISE');\n"
        "DCL REASON_B CHAR(12) INIT('LOWER');\n"
        "DCL REASON_C CHAR(12) INIT('CLOSE');\n"
        "DCL NEGATIVE_REASON_CODES CHAR(40) INIT('LOWER,CLOSE');\n"
        "DCL ALIAS_1 CHAR(20) INIT('A=>AUTO');\n"
    )
    write_psv(APP / "state/reserve_ledger.psv", LEDGER, [])
    (APP / "state/restart_checkpoint.txt").write_text("0\n")
    write_psv(
        APP / "config/windows.psv",
        ["loss_unit", "open_ts", "close_ts", "state"],
        [["S-F", "20260528110000", "20260528170000", "OPEN"]],
    )


def run_batch():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    report = list(
        csv.DictReader((APP / "out/reserve_adjustment_report.csv").open(), delimiter="|")
    )
    exceptions = list(
        csv.DictReader((APP / "out/reserve_exceptions.csv").open(), delimiter="|")
    )
    positions = list(
        csv.DictReader((APP / "out/reserve_position.txt").open(), delimiter="|")
    )
    return report, exceptions, positions


def test_policy_limits_hold_over_cap_but_other_policies_continue() -> None:
    """Policy reserve limits are consumed in adjustment order per policy_id."""
    setup_common()
    write_psv(
        APP / "config/policy_limits.psv",
        ["policy_id", "max_reserve_cents"],
        [["POL-A", "100"], ["POL-B", "50"]],
    )
    write_psv(APP / "config/subrogation_holds.psv", ["action_id", "hold_reason"], [])
    write_psv(
        APP / "data/claims.psv",
        CLAIMS,
        [
            ["C1", "POL-A", "S-F", "AUTO", "60", "20260528120000", "OPEN", "L1"],
            ["C2", "POL-A", "S-F", "AUTO", "50", "20260528120100", "OPEN", "L1"],
            ["C3", "POL-B", "S-F", "AUTO", "20", "20260528120200", "OPEN", "L2"],
        ],
    )
    write_psv(
        APP / "data/adjustments.psv",
        ADJUSTMENTS,
        [
            ["A1", "C1", "POL-A", "S-F", "A", "60", "20260528121000", "RAISE", "L1"],
            ["A2", "C2", "POL-A", "S-F", "A", "50", "20260528121100", "RAISE", "L1"],
            ["A3", "C3", "POL-B", "S-F", "A", "20", "20260528121200", "RAISE", "L2"],
        ],
    )

    report, exceptions, positions = run_batch()

    assert [row["status"] for row in report] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert [row["reason"] for row in exceptions] == ["POLICY_LIMIT"]
    assert exceptions[0]["action_id"] == "A2"
    pol_a = next(row for row in positions if row["policy_id"] == "POL-A")
    assert pol_a == {
        "policy_id": "POL-A",
        "limit_cents": "100",
        "used_cents": "60",
        "remaining_cents": "40",
    }


def test_subrogation_hold_does_not_consume_claim_for_later_safe_adjustment() -> None:
    """Subrogation quarantine returns the hold but leaves the claim row available."""
    setup_common()
    write_psv(
        APP / "config/policy_limits.psv",
        ["policy_id", "max_reserve_cents"],
        [["POL-S", "200"]],
    )
    write_psv(
        APP / "config/subrogation_holds.psv",
        ["action_id", "hold_reason"],
        [["HIT", "pending_review"]],
    )
    write_psv(
        APP / "data/claims.psv",
        CLAIMS,
        [["C-HOLD", "POL-S", "S-F", "AUTO", "45", "20260528120000", "OPEN", "L1"]],
    )
    write_psv(
        APP / "data/adjustments.psv",
        ADJUSTMENTS,
        [
            ["HIT", "C-HOLD", "POL-S", "S-F", "A", "45", "20260528121000", "RAISE", "L1"],
            ["SAFE", "C-HOLD", "POL-S", "S-F", "A", "45", "20260528121100", "RAISE", "L1"],
        ],
    )

    report, exceptions, _ = run_batch()

    assert [row["status"] for row in report] == ["UNMATCHED", "MATCHED"]
    assert exceptions[0] == {
        "action_id": "HIT",
        "claim_id": "C-HOLD",
        "policy_id": "POL-S",
        "reason": "SUBROGATION_HOLD",
        "detail": "pending_review",
    }
