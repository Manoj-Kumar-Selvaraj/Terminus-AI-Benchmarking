# ruff: noqa: E501
import csv
import subprocess
from pathlib import Path

APP = Path("/app")
CLEARING = ["wire_id", "account", "amount_cents", "rail_code", "posted_ts", "state", "branch_id"]
CLAIMS = ["claim_id", "wire_id", "account", "amount_cents", "rail_code", "claim_ts", "reason_code", "branch_id"]
LEDGER = ["claim_id", "wire_id", "account", "branch_id", "rail_code", "amount_cents", "status"]


def write_psv(path: Path, header: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("|".join(header) + "\n" + "\n".join("|".join(row) for row in rows) + "\n")


def write_common() -> None:
    (APP / "src/wire_rules.pli").write_text(
        "DCL ELIGIBLE_STATE CHAR(12) INIT('OPEN');\n"
        "DCL OPEN_CLEAR_STATE CHAR(8) INIT('OPEN');\n"
        "DCL REASON_1 CHAR(12) INIT('OK');\n"
        "DCL REASON_2 CHAR(12) INIT('RECALL');\n"
        "DCL REASON_3 CHAR(12) INIT('DONE');\n"
        "DCL ALIAS_1 CHAR(20) INIT('F=>FED');\n"
        "DCL NEGATIVE_REASON_CODES CHAR(40) INIT('RECALL');\n"
    )
    write_psv(APP / "config/clearing_windows.psv", ["account", "open_ts", "close_ts", "state"], [["991100", "20260612110000", "20260612170000", "OPEN"]])
    write_psv(APP / "config/settlement_calendar.psv", ["business_date", "cutoff_ts", "state"], [["20260612", "20260612170000", "OPEN"]])


def run_batch() -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, str]]:
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    report = list(csv.DictReader((APP / "out/wire_report.csv").open(), delimiter="|"))
    ledger = list(csv.DictReader((APP / "out/wire_ledger.psv").open(), delimiter="|"))
    restart = dict(line.split("=", 1) for line in (APP / "out/restart_audit.txt").read_text().splitlines())
    return report, ledger, restart


def test_committed_ledger_rows_suppress_replay_and_new_rows_append_once() -> None:
    """M3 returns committed replay duplicates and appends only new committed rows."""
    write_common()
    write_psv(APP / "state/wire_ledger.psv", LEDGER, [["OLD", "W-1", "991100", "NYC", "FED", "30", "COMMITTED"]])
    (APP / "state/restart_checkpoint.txt").write_text("1\n")
    write_psv(
        APP / "data/clearing.psv",
        CLEARING,
        [
            ["W-1", "991100", "30", "FED", "20260612120000", "OPEN", "NYC"],
            ["W-2", "991100", "40", "F", "20260612120100", "OPEN", "NYC"],
        ],
    )
    write_psv(
        APP / "data/claims.psv",
        CLAIMS,
        [
            ["OLD", "W-1", "991100", "30", "FED", "20260612121000", "OK", "NYC"],
            ["NEW", "W-2", "991100", "40", "FED", "20260612121100", "OK", "NYC"],
        ],
    )

    report, ledger, restart = run_batch()

    assert [row["status"] for row in report] == ["RETURNED", "CLEARED"]
    assert [row["claim_id"] for row in ledger] == ["OLD", "NEW"]
    assert restart == {"checkpoint_status": "OK", "committed_rows": "1"}


def test_missing_stale_and_ahead_checkpoints_do_not_skip_valid_processing() -> None:
    """Checkpoint anomalies are reported but do not suppress valid non-replay claims."""
    for marker, expected in [(None, "MISSING"), ("bad\n", "STALE"), ("9\n", "AHEAD")]:
        write_common()
        write_psv(APP / "state/wire_ledger.psv", LEDGER, [])
        checkpoint = APP / "state/restart_checkpoint.txt"
        if marker is None:
            checkpoint.unlink(missing_ok=True)
        else:
            checkpoint.write_text(marker)
        write_psv(APP / "data/clearing.psv", CLEARING, [["W-X", "991100", "15", "F", "20260612120000", "OPEN", "NYC"]])
        write_psv(APP / "data/claims.psv", CLAIMS, [["C-X", "W-X", "991100", "15", "FED", "20260612121000", "OK", "NYC"]])

        report, ledger, restart = run_batch()

        assert report[0]["status"] == "CLEARED"
        assert ledger[-1]["claim_id"] == "C-X"
        assert restart["checkpoint_status"] == expected
