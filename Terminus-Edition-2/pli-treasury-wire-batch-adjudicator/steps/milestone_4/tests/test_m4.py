# ruff: noqa: E501
import csv
import subprocess
from pathlib import Path

APP = Path("/app")
CLEARING = ["wire_id", "account", "amount_cents", "rail_code", "posted_ts", "state", "branch_id"]
CLAIMS = [
    "claim_id",
    "wire_id",
    "account",
    "amount_cents",
    "rail_code",
    "claim_ts",
    "reason_code",
    "branch_id",
    "counterparty_id",
]
LEDGER = ["claim_id", "wire_id", "account", "branch_id", "rail_code", "amount_cents", "status"]


def write_psv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("|".join(header) + "\n" + "\n".join("|".join(row) for row in rows) + "\n")


def setup_common() -> None:
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
    write_psv(APP / "state/wire_ledger.psv", LEDGER, [])
    (APP / "state/restart_checkpoint.txt").write_text("0\n")
    write_psv(APP / "config/clearing_windows.psv", ["account", "open_ts", "close_ts", "state"], [["991100", "20260612110000", "20260612170000", "OPEN"]])
    write_psv(APP / "config/settlement_calendar.psv", ["business_date", "cutoff_ts", "state"], [["20260612", "20260612170000", "OPEN"]])


def run_batch():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    report = list(csv.DictReader((APP / "out/wire_report.csv").open(), delimiter="|"))
    exceptions = list(csv.DictReader((APP / "out/wire_exceptions.csv").open(), delimiter="|"))
    positions = list(csv.DictReader((APP / "out/liquidity_position.txt").open(), delimiter="|"))
    return report, exceptions, positions


def test_liquidity_limits_hold_over_cap_but_other_buckets_continue() -> None:
    """Liquidity is consumed per canonical account/rail bucket in claim order."""
    setup_common()
    write_psv(APP / "config/nostro_limits.psv", ["account", "rail_code", "limit_cents"], [["991100", "FED", "100"], ["991100", "ACH", "50"]])
    write_psv(APP / "config/sanctions_watchlist.psv", ["counterparty_id", "reason"], [["OFAC-LOCK", "blocked"]])
    write_psv(
        APP / "data/clearing.psv",
        CLEARING,
        [
            ["W1", "991100", "60", "F", "20260612120000", "OPEN", "NYC"],
            ["W2", "991100", "50", "FED", "20260612120100", "OPEN", "NYC"],
            ["W3", "991100", "20", "ACH", "20260612120200", "OPEN", "NYC"],
        ],
    )
    write_psv(
        APP / "data/claims.psv",
        CLAIMS,
        [
            ["C1", "W1", "991100", "60", "FED", "20260612121000", "OK", "NYC", "SAFE"],
            ["C2", "W2", "991100", "50", "FED", "20260612121100", "OK", "NYC", "SAFE"],
            ["C3", "W3", "991100", "20", "A", "20260612121200", "OK", "NYC", "SAFE"],
        ],
    )

    report, exceptions, positions = run_batch()

    assert [row["status"] for row in report] == ["CLEARED", "RETURNED", "CLEARED"]
    assert [row["reason"] for row in exceptions] == ["LIQUIDITY_HOLD"]
    assert exceptions[0]["claim_id"] == "C2"
    fed = next(row for row in positions if row["account"] == "991100" and row["rail_code"] == "FED")
    assert fed == {"account": "991100", "rail_code": "FED", "limit_cents": "100", "used_cents": "60", "remaining_cents": "40"}


def test_sanctions_hit_does_not_consume_clearing_row_for_later_safe_claim() -> None:
    """Sanctions quarantine returns the hit but leaves its clearing row available."""
    setup_common()
    write_psv(APP / "config/nostro_limits.psv", ["account", "rail_code", "limit_cents"], [["991100", "FED", "200"]])
    write_psv(APP / "config/sanctions_watchlist.psv", ["counterparty_id", "reason"], [["OFAC-LOCK", "blocked"]])
    write_psv(APP / "data/clearing.psv", CLEARING, [["W-S", "991100", "45", "F", "20260612120000", "OPEN", "NYC"]])
    write_psv(
        APP / "data/claims.psv",
        CLAIMS,
        [
            ["HIT", "W-S", "991100", "45", "FED", "20260612121000", "OK", "NYC", "OFAC-LOCK"],
            ["SAFE", "W-S", "991100", "45", "FED", "20260612121100", "OK", "NYC", "SAFE"],
        ],
    )

    report, exceptions, _ = run_batch()

    assert [row["status"] for row in report] == ["RETURNED", "CLEARED"]
    assert exceptions[0] == {
        "claim_id": "HIT",
        "wire_id": "W-S",
        "account": "991100",
        "reason": "SANCTIONS_HIT",
        "detail": "OFAC-LOCK",
    }
