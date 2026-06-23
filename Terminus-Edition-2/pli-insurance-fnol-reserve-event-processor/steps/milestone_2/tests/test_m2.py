# ruff: noqa: E501
"""Verifier tests for insurance FNOL reserve adjustment PL/I task — milestone 2."""

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


def write_inputs(
    claims: list[list[str]],
    adjustments: list[list[str]],
    windows: list[list[str]],
) -> None:
    write_psv(APP / "data/claims.psv", CLAIMS, claims)
    write_psv(APP / "data/adjustments.psv", ADJUSTMENTS, adjustments)
    write_psv(APP / "config/windows.psv", ["loss_unit", "open_ts", "close_ts", "state"], windows)


def run_batch() -> tuple[list[dict[str, str]], dict[str, int]]:
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="|"))
    summary = {
        key: int(value)
        for key, value in (
            line.split("=", 1) for line in SUMMARY.read_text().splitlines()
        )
    }
    return rows, summary


def test_milestone1_aliases_direction_consumption_and_absolute_totals() -> None:
    """Regression: milestone 1 strict keys, aliases, direction, and consumption."""
    write_rules()
    write_inputs(
        [
            ["SRC-1", "PARTY-1", "S-A", "AUTO", "10", "20260528120000", "OPEN", "L1"],
            ["SRC-2", "PARTY-2", "S-A", "HOME", "-20", "20260528120100", "OPEN", "L2"],
            ["SRC-3", "PARTY-3", "S-A", "LIAB", "30", "20260528120200", "OPEN", "L3"],
        ],
        [
            ["ACT-1", "SRC-1", "PARTY-1", "S-A", "a", "10", "20260528120500", "RAISE", "L1"],
            ["ACT-2", "SRC-1", "PARTY-1", "S-A", "A", "10", "20260528120600", "RAISE", "L1"],
            ["ACT-3", "SRC-2", "PARTY-2", "S-A", "H", "-20", "20260528120700", "LOWER", "L2"],
            ["ACT-4", "SRC-3", "PARTY-3", "S-A", "L", "40", "20260528120700", "RAISE", "L3"],
        ],
        [["S-A", "20260528115900", "20260528123000", "OPEN"]],
    )
    rows, summary = run_batch()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED", "UNMATCHED"]
    assert summary["matched_amount_cents"] == 30


def test_windows_closed_malformed_latest_timestamp_and_row_tiebreak() -> None:
    """M2 rejects closed/malformed windows and picks latest fnol_ts then earliest claim row."""
    write_rules(open_state="LIVE")
    write_inputs(
        [
            ["W-1", "P-1", "S-O", "AUTO", "1", "20260528140000", "OPEN", "L1"],
            ["W-2", "P-2", "S-C", "AUTO", "2", "20260528140000", "OPEN", "L2"],
            ["W-3", "P-3", "S-O", "HOME", "-3", "bad-time", "OPEN", "L3"],
            ["DUP", "P-4", "S-O", "LIAB", "-4", "20260528140100", "OPEN", "L4"],
            ["DUP", "P-4", "S-O", "LIAB", "-4", "20260528140100", "OPEN", "L4"],
        ],
        [
            ["Y-1", "W-1", "P-1", "S-O", "A", "1", "20260528140500", "RAISE", "L1"],
            ["Y-2", "W-2", "P-2", "S-C", "A", "2", "20260528140500", "RAISE", "L2"],
            ["Y-3", "W-3", "P-3", "S-O", "H", "-3", "20260528140500", "LOWER", "L3"],
            ["Y-4", "DUP", "P-4", "S-O", "L", "-4", "20260528140600", "CLOSE", "L4"],
            ["Y-5", "W-1", "P-1", "S-O", "A", "1", "20260528150000", "RAISE", "L1"],
        ],
        [
            ["S-O", "20260528135900", "20260528143000", "LIVE"],
            ["S-C", "20260528135900", "20260528143000", "CLOSED"],
        ],
    )
    rows, summary = run_batch()
    assert [row["status"] for row in rows] == [
        "MATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "MATCHED",
        "UNMATCHED",
    ]
    assert [row["coverage_type"] for row in rows] == ["AUTO", "", "", "LIAB", ""]
    assert summary == {
        "matched_count": 2,
        "matched_amount_cents": 5,
        "unmatched_count": 3,
        "unmatched_amount_cents": 6,
    }


def test_action_timestamp_before_source_is_unmatched() -> None:
    """M2 requires adjust_ts on or after fnol_ts inside the open window."""
    write_rules()
    write_inputs(
        [["TS-1", "P-1", "S-T", "AUTO", "5", "20260528150000", "OPEN", "L1"]],
        [["Z-1", "TS-1", "P-1", "S-T", "A", "5", "20260528140000", "RAISE", "L1"]],
        [["S-T", "20260528135900", "20260528153000", "OPEN"]],
    )
    rows, _ = run_batch()
    assert rows[0]["status"] == "UNMATCHED"
