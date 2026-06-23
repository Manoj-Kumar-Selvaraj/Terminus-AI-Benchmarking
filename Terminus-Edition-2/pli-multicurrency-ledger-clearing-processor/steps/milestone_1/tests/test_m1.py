import csv
import subprocess
from pathlib import Path

APP = Path("/app")

LEDGER_HEADER = [
    "txn_id", "account_id", "amount_cents", "currency_code",
    "desk_id", "book_ts", "state", "kind_code",
]
POSTING_HEADER = [
    "claim_id", "txn_id", "account_id", "amount_cents", "currency_code",
    "post_ts", "entry_type", "desk_id",
]
WINDOW_HEADER = ["account_id", "open_ts", "close_ts", "state"]
REPORT_HEADER = [
    "claim_id", "txn_id", "account_id", "desk_id", "currency_code",
    "amount_cents", "entry_type", "status",
]


def write_psv(path: Path, header, rows):
    path.write_text(
        "|".join(header) + "\n" + "\n".join("|".join(row) for row in rows) + "\n",
        encoding="utf-8",
    )


def write_rules(state="POSTED", reasons=("POST", "TRANSFER", "FEE")):
    """Replace rules so tests prove solutions read constants dynamically."""
    (APP / "src" / "ledger_rules.pli").write_text(
        "\n".join(
            [
                f"DCL ELIGIBLE_STATE CHAR(12) INIT('{state}');",
                "DCL OPEN_FX_STATE CHAR(8) INIT('OPEN');",
                f"DCL REASON_1 CHAR(12) INIT('{reasons[0]}');",
                f"DCL REASON_2 CHAR(12) INIT('{reasons[1]}');",
                f"DCL REASON_3 CHAR(12) INIT('{reasons[2]}');",
                "DCL ALIAS_1 CHAR(20) INIT('USD=>DOLLAR');",
                "DCL ALIAS_2 CHAR(20) INIT('B=>BETA');",
                "DCL ALIAS_3 CHAR(20) INIT('X=>XLINK');",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def run_batch():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    report_text = (APP / "out" / "ledger_report.csv").read_text(encoding="utf-8")
    rows = list(csv.DictReader(report_text.splitlines(), delimiter="|"))
    summary = {
        key: int(value)
        for key, value in (
            line.split("=", 1)
            for line in (APP / "out" / "ledger_summary.txt").read_text(encoding="utf-8").splitlines()
        )
    }
    return report_text, rows, summary


def prepare_windows():
    write_psv(
        APP / "config" / "fx_windows.psv",
        WINDOW_HEADER,
        [["991100", "20260612115900", "20260612123000", "OPEN"]],
    )
    (APP / "out").mkdir(exist_ok=True)


def test_m1_full_key_matching_consumes_once_and_summarizes_held_amounts():
    """Verify full-key matching, one-use ledger rows, blank HELD currency, and totals."""
    write_rules(state="LIVE", reasons=("OK", "WATCH", "DONE"))
    write_psv(
        APP / "data" / "ledger.psv",
        LEDGER_HEADER,
        [
            ["R-1", "991100", "10", "FED", "NYC", "20260612120000", "LIVE", "TM"],
            ["R-2", "991200", "20", "ACH", "NYC", "20260612120100", "BAD", "TM"],
            ["R-3", "991300", "30", "SWIFT", "BOS", "20260612120200", "LIVE", "TM"],
        ],
    )
    write_psv(
        APP / "data" / "postings.psv",
        POSTING_HEADER,
        [
            ["C1", "R-1", "991100", "10", "FED", "20260612120500", "OK", "NYC"],
            ["C2", "R-1", "991100", "10", "FED", "20260612120600", "OK", "NYC"],
            ["C3", "R-2", "991200", "20", "ACH", "20260612120700", "OK", "NYC"],
            ["C4", "R-3", "991300", "30", "SWIFT", "20260612120700", "WATCH", "BOS"],
            ["C5", "R-3", "991300", "31", "SWIFT", "20260612120700", "WATCH", "BOS"],
            ["C6", "R-3", "991300", "30", "SWIFT", "20260612120700", "NOPE", "BOS"],
        ],
    )
    prepare_windows()

    _, rows, summary = run_batch()

    assert [r["status"] for r in rows] == ["CLEARED", "HELD", "HELD", "CLEARED", "HELD", "HELD"]
    assert rows[0]["currency_code"] == "FED"
    assert rows[1]["currency_code"] == ""
    assert rows[3]["currency_code"] == "SWIFT"
    assert summary == {
        "cleared_count": 2,
        "cleared_amount_cents": 40,
        "held_count": 4,
        "held_amount_cents": 91,
    }


def test_m1_rejects_prefix_only_matches_and_preserves_pipe_delimited_schema():
    """A shared transaction prefix is insufficient; the pipe-delimited schema is fixed."""
    write_rules(state="SETTLED", reasons=("APPROVE", "MANUAL", "DONE"))
    write_psv(
        APP / "data" / "ledger.psv",
        LEDGER_HEADER,
        [["ABCDE-LEDGER", "ACCT9", "77", "JPY", "TKO", "20260612120000", "SETTLED", "TM"]],
    )
    write_psv(
        APP / "data" / "postings.psv",
        POSTING_HEADER,
        [
            ["P1", "ABCDE-POST", "ACCT9", "77", "JPY", "20260612120500", "manual", "TKO"],
            ["P2", "ABCDE-LEDGER", "ACCT9", "77", "JPY", "20260612120600", "MaNuAl", "TKO"],
        ],
    )
    prepare_windows()

    report_text, rows, summary = run_batch()

    assert report_text.splitlines()[0].split("|") == REPORT_HEADER
    assert "," not in report_text.splitlines()[0]
    assert [r["status"] for r in rows] == ["HELD", "CLEARED"]
    assert rows[0]["currency_code"] == ""
    assert rows[1]["currency_code"] == "JPY"
    assert summary == {
        "cleared_count": 1,
        "cleared_amount_cents": 77,
        "held_count": 1,
        "held_amount_cents": 77,
    }


def test_m1_tiebreaks_by_latest_book_ts_then_earliest_ledger_row():
    """Multiple eligible ledger rows use latest book_ts, then earliest physical row."""
    write_rules(state="LIVE", reasons=("OK", "WATCH", "DONE"))
    write_psv(
        APP / "data" / "ledger.psv",
        LEDGER_HEADER,
        [
            ["R-T", "ACCT1", "100", "USD", "NYC", "20260612110000", "LIVE", "TM"],
            ["R-T", "ACCT1", "100", "usd", "NYC", "20260612120000", "LIVE", "TM"],
            ["R-T", "ACCT1", "100", "Usd", "NYC", "20260612120000", "LIVE", "TM"],
        ],
    )
    write_psv(
        APP / "data" / "postings.psv",
        POSTING_HEADER,
        [
            ["P-T1", "R-T", "ACCT1", "100", "USD", "20260612130000", "OK", "NYC"],
            ["P-T2", "R-T", "ACCT1", "100", "USD", "20260612130001", "OK", "NYC"],
            ["P-T3", "R-T", "ACCT1", "100", "USD", "20260612130002", "OK", "NYC"],
        ],
    )
    prepare_windows()

    _, rows, summary = run_batch()

    assert [r["status"] for r in rows] == ["CLEARED", "CLEARED", "CLEARED"]
    assert [r["currency_code"] for r in rows] == ["usd", "Usd", "USD"]
    assert summary == {
        "cleared_count": 3,
        "cleared_amount_cents": 300,
        "held_count": 0,
        "held_amount_cents": 0,
    }
