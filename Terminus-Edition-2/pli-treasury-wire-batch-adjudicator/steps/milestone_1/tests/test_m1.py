# ruff: noqa: E501
import csv
import subprocess
from pathlib import Path

APP = Path("/app")
CLEARING = ["wire_id", "account", "amount_cents", "rail_code", "posted_ts", "state", "branch_id"]
CLAIMS = ["claim_id", "wire_id", "account", "amount_cents", "rail_code", "claim_ts", "reason_code", "branch_id"]


def write_psv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.write_text("|".join(header) + "\n" + "\n".join("|".join(row) for row in rows) + "\n")


def write_rules(state: str = "LIVE") -> None:
    (APP / "src/wire_rules.pli").write_text(
        "\n".join(
            [
                f"DCL ELIGIBLE_STATE CHAR(12) INIT('{state}');",
                "DCL OPEN_CLEAR_STATE CHAR(8) INIT('OPEN');",
                "DCL REASON_1 CHAR(12) INIT('APPROVE');",
                "DCL REASON_2 CHAR(12) INIT('RECALL');",
                "DCL REASON_3 CHAR(12) INIT('MANUAL');",
                "DCL ALIAS_1 CHAR(20) INIT(' f => FED ');",
                "DCL ALIAS_2 CHAR(20) INIT('a=>ACH');",
                "DCL ALIAS_3 CHAR(20) INIT('s=>SWIFT');",
                "DCL NEGATIVE_REASON_CODES CHAR(40) INIT('RECALL');",
            ]
        )
        + "\n"
    )


def run_batch() -> tuple[list[dict[str, str]], dict[str, int], list[str]]:
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with (APP / "out/wire_report.csv").open() as handle:
        reader = csv.DictReader(handle, delimiter="|")
        rows = list(reader)
        columns = reader.fieldnames or []
    summary = dict(
        line.split("=", 1) for line in (APP / "out/wire_summary.txt").read_text().splitlines()
    )
    return rows, {key: int(value) for key, value in summary.items()}, columns


def test_aliases_direction_consumption_and_absolute_totals() -> None:
    """M1 combines strict matching, alias normalization, signed reasons, and consume-once."""
    write_rules()
    write_psv(
        APP / "data/clearing.psv",
        CLEARING,
        [
            ["W-1", "991100", "100", "f", "20260612120000", "LIVE", "NYC"],
            ["W-2", "991100", "-25", "ACH", "20260612120100", "LIVE", "NYC"],
            ["W-3", "991100", "40", "SWIFT", "20260612120200", "LIVE", "NYC"],
        ],
    )
    write_psv(
        APP / "data/claims.psv",
        CLAIMS,
        [
            ["C1", "W-1", "991100", "100", "FED", "20260612120500", " approve ", "NYC"],
            ["C2", "W-1", "991100", "100", "FED", "20260612120600", "APPROVE", "NYC"],
            ["C3", "W-2", "991100", "-25", "a", "20260612120700", "recall", "NYC"],
            ["C4", "W-3", "991100", "40", "s", "20260612120800", "RECALL", "NYC"],
        ],
    )

    rows, summary, columns = run_batch()

    assert columns == [
        "claim_id",
        "wire_id",
        "account",
        "branch_id",
        "rail_code",
        "amount_cents",
        "reason_code",
        "status",
    ]
    assert [row["status"] for row in rows] == ["CLEARED", "RETURNED", "CLEARED", "RETURNED"]
    assert [row["rail_code"] for row in rows] == ["FED", "", "ACH", ""]
    assert summary == {
        "cleared_count": 2,
        "cleared_amount_cents": 125,
        "returned_count": 2,
        "returned_amount_cents": 140,
    }


def test_no_prefix_shortcuts_runtime_state_and_report_regeneration() -> None:
    """Runtime state/reasons are honored and old output rows are replaced."""
    write_rules(state="READY")
    write_psv(
        APP / "data/clearing.psv",
        CLEARING,
        [
            ["WIRE-100-EXTRA", "991100", "55", "FED", "20260612120000", "READY", "NYC"],
            ["WIRE-200", "991200", "60", "ACH", "20260612120100", "LIVE", "NYC"],
        ],
    )
    write_psv(
        APP / "data/claims.psv",
        CLAIMS,
        [
            ["PFX", "WIRE-100", "991100", "55", "FED", "20260612120500", "APPROVE", "NYC"],
            ["STATE", "WIRE-200", "991200", "60", "ACH", "20260612120500", "APPROVE", "NYC"],
        ],
    )
    rows, summary, _ = run_batch()
    assert [row["status"] for row in rows] == ["RETURNED", "RETURNED"]
    assert summary["returned_amount_cents"] == 115

    write_psv(
        APP / "data/clearing.psv",
        CLEARING,
        [["WIRE-300", "991300", "70", "FED", "20260612120100", "READY", "BOS"]],
    )
    write_psv(
        APP / "data/claims.psv",
        CLAIMS,
        [["ONLY", "WIRE-300", "991300", "70", "f", "20260612120500", "manual", "BOS"]],
    )
    rows, summary, _ = run_batch()
    assert [row["claim_id"] for row in rows] == ["ONLY"]
    assert rows[0]["status"] == "CLEARED"
    assert rows[0]["rail_code"] == "FED"
    assert summary["cleared_amount_cents"] == 70
