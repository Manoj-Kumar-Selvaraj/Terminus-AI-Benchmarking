# ruff: noqa: E501
"""Verifier tests for insurance FNOL reserve adjustment PL/I task — milestone 1."""

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
REPORT = APP / "out/reserve_adjustment_report.csv"
SUMMARY = APP / "out/reserve_adjustment_summary.txt"


def write_psv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("|".join(header) + "\n" + "\n".join("|".join(row) for row in rows) + "\n")


def write_rules(
    status: str = "OPEN",
    open_state: str = "OPEN",
    reasons: tuple[str, str, str] = ("RAISE", "LOWER", "CLOSE"),
    aliases: tuple[str, ...] = ("A=>AUTO", "H=>HOME", "L=>LIAB"),
    negative: str = "LOWER,CLOSE",
) -> None:
    lines = [
        f"DCL ELIGIBLE_STATUS CHAR(12) INIT('{status}');",
        f"DCL OPEN_WINDOW_STATUS CHAR(8) INIT('{open_state}');",
        f"DCL REASON_A CHAR(12) INIT('{reasons[0]}');",
        f"DCL REASON_B CHAR(12) INIT('{reasons[1]}');",
        f"DCL REASON_C CHAR(12) INIT('{reasons[2]}');",
        f"DCL NEGATIVE_REASON_CODES CHAR(40) INIT('{negative}');",
    ]
    lines += [f"DCL ALIAS_{i + 1} CHAR(20) INIT('{a}');" for i, a in enumerate(aliases)]
    (APP / "src/fnol_rules.pli").write_text("\n".join(lines) + "\n")


def run_batch() -> tuple[list[dict[str, str]], dict[str, int], list[str]]:
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter="|")
        rows = list(reader)
        columns = reader.fieldnames or []
    summary = {
        key: int(value)
        for key, value in (
            line.split("=", 1) for line in SUMMARY.read_text().splitlines()
        )
    }
    return rows, summary, columns


def test_aliases_direction_consumption_and_absolute_totals() -> None:
    """M1 combines strict matching, alias normalization, signed reasons, and consume-once."""
    write_rules()
    write_psv(
        APP / "data/claims.psv",
        CLAIMS,
        [
            ["SRC-1", "PARTY-1", "S-A", "AUTO", "10", "20260528120000", "OPEN", "L1"],
            ["SRC-2", "PARTY-2", "S-A", "HOME", "-20", "20260528120100", "OPEN", "L2"],
            ["SRC-3", "PARTY-3", "S-A", "LIAB", "30", "20260528120200", "OPEN", "L3"],
        ],
    )
    write_psv(
        APP / "data/adjustments.psv",
        ADJUSTMENTS,
        [
            ["ACT-1", "SRC-1", "PARTY-1", "S-A", "a", "10", "20260528120500", "RAISE", "L1"],
            ["ACT-2", "SRC-1", "PARTY-1", "S-A", "A", "10", "20260528120600", "RAISE", "L1"],
            ["ACT-3", "SRC-2", "PARTY-2", "S-A", "H", "-20", "20260528120700", "LOWER", "L2"],
            ["ACT-4", "SRC-3", "PARTY-3", "S-A", "L", "40", "20260528120700", "RAISE", "L3"],
        ],
    )

    rows, summary, columns = run_batch()

    assert columns == [
        "action_id",
        "claim_id",
        "policy_id",
        "loss_unit",
        "coverage_type",
        "reserve_cents",
        "reason",
        "status",
    ]
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED", "UNMATCHED"]
    assert [row["coverage_type"] for row in rows] == ["AUTO", "", "HOME", ""]
    assert summary == {
        "matched_count": 2,
        "matched_amount_cents": 30,
        "unmatched_count": 2,
        "unmatched_amount_cents": 50,
    }


def test_no_prefix_shortcuts_runtime_state_and_report_regeneration() -> None:
    """Runtime state/reasons are honored and old output rows are replaced."""
    write_rules(status="READY", reasons=("OK", "WATCH", "DONE"))
    write_psv(
        APP / "data/claims.psv",
        CLAIMS,
        [
            ["SRC-1", "PARTY-1", "S-A", "AUTO", "10", "20260528120000", "READY", "L1"],
            ["SRC-2", "PARTY-2", "S-A", "HOME", "20", "20260528120100", "BAD", "L2"],
        ],
    )
    write_psv(
        APP / "data/adjustments.psv",
        ADJUSTMENTS,
        [
            ["ACT-1", "SRC-1", "PARTY-1", "S-A", "AUTO", "10", "20260528120500", "OK", "L1"],
            ["ACT-2", "SRC-2", "PARTY-2", "S-A", "HOME", "20", "20260528120700", "WATCH", "L2"],
            ["ACT-3", "SRC-3", "PARTY-3", "S-A", "HOME", "30", "20260528120700", "WATCH", "L3"],
        ],
    )

    rows, summary, _ = run_batch()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 10,
        "unmatched_count": 2,
        "unmatched_amount_cents": 50,
    }

    write_psv(
        APP / "data/claims.psv",
        CLAIMS,
        [["ONLY", "PARTY-9", "S-Z", "AUTO", "5", "20260528120000", "READY", "L9"]],
    )
    write_psv(
        APP / "data/adjustments.psv",
        ADJUSTMENTS,
        [["ACT-9", "ONLY-EXTRA", "PARTY-9", "S-Z", "AUTO", "5", "20260528120500", "OK", "L9"]],
    )
    rows, summary, _ = run_batch()
    assert rows[0]["status"] == "UNMATCHED"
    assert summary["unmatched_amount_cents"] == 5
