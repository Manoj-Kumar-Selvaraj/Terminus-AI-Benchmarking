# ruff: noqa: E501
import csv
import subprocess
from pathlib import Path

APP = Path("/app")
CLEARING = ["wire_id", "account", "amount_cents", "rail_code", "posted_ts", "state", "branch_id"]
CLAIMS = ["claim_id", "wire_id", "account", "amount_cents", "rail_code", "claim_ts", "reason_code", "branch_id"]


def write_psv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.write_text("|".join(header) + "\n" + "\n".join("|".join(row) for row in rows) + "\n")


def write_rules() -> None:
    (APP / "src/wire_rules.pli").write_text(
        "DCL ELIGIBLE_STATE CHAR(12) INIT('OPEN');\n"
        "DCL OPEN_CLEAR_STATE CHAR(8) INIT('OPEN');\n"
        "DCL REASON_1 CHAR(12) INIT('OK');\n"
        "DCL REASON_2 CHAR(12) INIT('RECALL');\n"
        "DCL REASON_3 CHAR(12) INIT('DONE');\n"
        "DCL ALIAS_1 CHAR(20) INIT('F=>FED');\n"
        "DCL ALIAS_2 CHAR(20) INIT('A=>ACH');\n"
        "DCL NEGATIVE_REASON_CODES CHAR(40) INIT('RECALL');\n"
    )


def run_batch() -> tuple[list[dict[str, str]], dict[str, int]]:
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    rows = list(csv.DictReader((APP / "out/wire_report.csv").open(), delimiter="|"))
    summary = dict(
        line.split("=", 1) for line in (APP / "out/wire_summary.txt").read_text().splitlines()
    )
    return rows, {key: int(value) for key, value in summary.items()}


def test_window_cutoff_latest_candidate_and_consumption() -> None:
    """M2 requires pass windows, settlement cutoff, latest candidate, and consumption."""
    write_rules()
    write_psv(
        APP / "data/clearing.psv",
        CLEARING,
        [
            ["W-A", "991100", "10", "F", "20260612120000", "OPEN", "NYC"],
            ["W-A", "991100", "10", "FED", "20260612121000", "OPEN", "NYC"],
        ],
    )
    write_psv(
        APP / "data/claims.psv",
        CLAIMS,
        [
            ["LATEST", "W-A", "991100", "10", "FED", "20260612121500", "OK", "NYC"],
            ["OLDER", "W-A", "991100", "10", "f", "20260612120500", "OK", "NYC"],
        ],
    )
    write_psv(
        APP / "config/clearing_windows.psv",
        ["account", "open_ts", "close_ts", "state"],
        [["991100", "20260612115900", "20260612123000", "OPEN"]],
    )
    write_psv(
        APP / "config/settlement_calendar.psv",
        ["business_date", "cutoff_ts", "state"],
        [["20260612", "20260612170000", "OPEN"]],
    )

    rows, summary = run_batch()

    assert [row["status"] for row in rows] == ["CLEARED", "CLEARED"]
    assert [row["rail_code"] for row in rows] == ["FED", "FED"]
    assert summary["cleared_amount_cents"] == 20


def test_closed_missing_malformed_and_after_cutoff_rows_return() -> None:
    """Closed windows, missing calendars, malformed timestamps, and cutoff breaches return claims."""
    write_rules()
    write_psv(
        APP / "data/clearing.psv",
        CLEARING,
        [
            ["CLOSED", "991100", "11", "FED", "20260612120000", "OPEN", "NYC"],
            ["NOCAL", "991200", "12", "ACH", "20260613120000", "OPEN", "NYC"],
            ["BADTS", "991300", "13", "FED", "BAD", "OPEN", "NYC"],
            ["LATE", "991400", "14", "FED", "20260612180000", "OPEN", "NYC"],
        ],
    )
    write_psv(
        APP / "data/claims.psv",
        CLAIMS,
        [
            ["C1", "CLOSED", "991100", "11", "FED", "20260612120500", "OK", "NYC"],
            ["C2", "NOCAL", "991200", "12", "ACH", "20260613120500", "OK", "NYC"],
            ["C3", "BADTS", "991300", "13", "FED", "20260612120500", "OK", "NYC"],
            ["C4", "LATE", "991400", "14", "FED", "20260612180500", "OK", "NYC"],
        ],
    )
    write_psv(
        APP / "config/clearing_windows.psv",
        ["account", "open_ts", "close_ts", "state"],
        [
            ["991100", "20260612115900", "20260612123000", "CLOSED"],
            ["991200", "20260613115900", "20260613123000", "OPEN"],
            ["991300", "20260612115900", "20260612123000", "OPEN"],
            ["991400", "20260612170000", "20260612190000", "OPEN"],
        ],
    )
    write_psv(
        APP / "config/settlement_calendar.psv",
        ["business_date", "cutoff_ts", "state"],
        [["20260612", "20260612170000", "OPEN"]],
    )

    rows, summary = run_batch()

    assert [row["status"] for row in rows] == ["RETURNED"] * 4
    assert all(row["rail_code"] == "" for row in rows)
    assert summary["returned_amount_cents"] == 50


def test_posted_timestamp_after_claim_is_ineligible() -> None:
    """posted_ts > claim_ts is rejected even inside an otherwise valid open window."""
    write_rules()
    write_psv(
        APP / "data/clearing.psv",
        CLEARING,
        [
            ["W-LATE", "991100", "10", "FED", "20260612121500", "OPEN", "NYC"],
            ["W-OK", "991100", "10", "FED", "20260612120000", "OPEN", "NYC"],
        ],
    )
    write_psv(
        APP / "data/claims.psv",
        CLAIMS,
        [
            ["LATE-POST", "W-LATE", "991100", "10", "FED", "20260612121000", "OK", "NYC"],
            ["VALID", "W-OK", "991100", "10", "FED", "20260612120500", "OK", "NYC"],
        ],
    )
    write_psv(
        APP / "config/clearing_windows.psv",
        ["account", "open_ts", "close_ts", "state"],
        [["991100", "20260612115900", "20260612123000", "OPEN"]],
    )
    write_psv(
        APP / "config/settlement_calendar.psv",
        ["business_date", "cutoff_ts", "state"],
        [["20260612", "20260612170000", "OPEN"]],
    )

    rows, summary = run_batch()

    assert [row["status"] for row in rows] == ["RETURNED", "CLEARED"]
    assert rows[0]["rail_code"] == ""
    assert rows[1]["rail_code"] == "FED"
    assert summary["cleared_amount_cents"] == 10
