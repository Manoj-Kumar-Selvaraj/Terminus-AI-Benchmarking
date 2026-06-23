import csv
import subprocess
from pathlib import Path

APP = Path("/app")
LEDGER_HEADER = ["txn_id", "account_id", "amount_cents", "currency_code", "desk_id", "book_ts", "state", "kind_code"]
POSTING_HEADER = ["claim_id", "txn_id", "account_id", "amount_cents", "currency_code", "post_ts", "entry_type", "desk_id"]
WINDOW_HEADER = ["account_id", "open_ts", "close_ts", "state"]
REPORT_HEADER = ["claim_id", "txn_id", "account_id", "desk_id", "currency_code", "amount_cents", "entry_type", "status"]


def write_psv(path: Path, header, rows):
    path.write_text("|".join(header) + "\n" + "\n".join("|".join(row) for row in rows) + "\n", encoding="utf-8")


def write_rules(open_state="ACTIVE"):
    (APP / "src" / "ledger_rules.pli").write_text(
        "\n".join(
            [
                "DCL ELIGIBLE_STATE CHAR(12) INIT('LIVE');",
                f"DCL OPEN_FX_STATE CHAR(8) INIT('{open_state}');",
                "DCL REASON_1 CHAR(12) INIT('OK');",
                "DCL REASON_2 CHAR(12) INIT('WATCH');",
                "DCL REASON_3 CHAR(12) INIT('DONE');",
                "DCL ALIAS_1 CHAR(20) INIT('u=>USD');",
                "DCL ALIAS_2 CHAR(20) INIT('a=>ACH');",
                "DCL ALIAS_3 CHAR(20) INIT('s=>SWIFT');",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def run_batch():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    report_text = (APP / "out" / "ledger_report.csv").read_text(encoding="utf-8")
    reader = csv.DictReader(report_text.splitlines(), delimiter="|")
    assert reader.fieldnames == REPORT_HEADER
    rows = list(reader)
    summary = {
        key: int(value)
        for key, value in (
            line.split("=", 1)
            for line in (APP / "out" / "ledger_summary.txt").read_text(encoding="utf-8").splitlines()
        )
    }
    return rows, summary


def test_m3_dynamic_open_state_and_both_book_and_post_timestamps_must_be_inside_window():
    """Book and posting timestamps are both gated, and OPEN_FX_STATE is dynamic."""
    write_rules(open_state="ACTIVE")
    write_psv(
        APP / "data" / "ledger.psv",
        LEDGER_HEADER,
        [
            ["R-IN", "AC1", "10", "USD", "NYC", "20260612120000", "LIVE", "TM"],
            ["R-BOOK-BEFORE", "AC1", "20", "USD", "NYC", "20260612115959", "LIVE", "TM"],
            ["R-POST-AFTER", "AC1", "30", "USD", "NYC", "20260612121000", "LIVE", "TM"],
            ["R-WRONG-STATE", "AC2", "40", "USD", "NYC", "20260612120000", "LIVE", "TM"],
        ],
    )
    write_psv(
        APP / "data" / "postings.psv",
        POSTING_HEADER,
        [
            ["C-IN", "R-IN", "AC1", "10", "u", "20260612123000", "ok", "NYC"],
            ["C-BOOK-BEFORE", "R-BOOK-BEFORE", "AC1", "20", "USD", "20260612120500", "OK", "NYC"],
            ["C-POST-AFTER", "R-POST-AFTER", "AC1", "30", "USD", "20260612123001", "OK", "NYC"],
            ["C-WRONG-STATE", "R-WRONG-STATE", "AC2", "40", "USD", "20260612120500", "OK", "NYC"],
        ],
    )
    write_psv(
        APP / "config" / "fx_windows.psv",
        WINDOW_HEADER,
        [
            ["AC1", "20260612120000", "20260612123000", "active"],
            ["AC2", "20260612115900", "20260612123000", "CLOSED"],
        ],
    )
    (APP / "out").mkdir(exist_ok=True)

    rows, summary = run_batch()

    assert [r["status"] for r in rows] == ["CLEARED", "HELD", "HELD", "HELD"]
    assert [r["currency_code"] for r in rows] == ["USD", "", "", ""]
    assert summary == {
        "cleared_count": 1,
        "cleared_amount_cents": 10,
        "held_count": 3,
        "held_amount_cents": 90,
    }


def test_m3_keeps_alias_normalization_and_single_consumption_inside_fx_window():
    """Milestone 3 must carry forward alias normalization and one-use ledger rows."""
    write_rules(open_state="GREEN")
    write_psv(
        APP / "data" / "ledger.psv",
        LEDGER_HEADER,
        [["R-DUP", "AC9", "55", "u", "BOS", "20260612120500", "LIVE", "TM"]],
    )
    write_psv(
        APP / "data" / "postings.psv",
        POSTING_HEADER,
        [
            ["C1", "R-DUP", "AC9", "55", "USD", "20260612120600", "DONE", "BOS"],
            ["C2", "R-DUP", "AC9", "55", "USD", "20260612120700", "done", "BOS"],
        ],
    )
    write_psv(APP / "config" / "fx_windows.psv", WINDOW_HEADER, [["AC9", "20260612120000", "20260612123000", "GREEN"]])
    (APP / "out").mkdir(exist_ok=True)

    rows, summary = run_batch()

    assert [r["status"] for r in rows] == ["CLEARED", "HELD"]
    assert [r["currency_code"] for r in rows] == ["USD", ""]
    assert summary == {
        "cleared_count": 1,
        "cleared_amount_cents": 55,
        "held_count": 1,
        "held_amount_cents": 55,
    }
