import csv
import hashlib
import subprocess
from pathlib import Path

APP = Path("/app")
LEDGER_HEADER = ["txn_id", "account_id", "amount_cents", "currency_code", "desk_id", "book_ts", "state", "kind_code"]
POSTING_HEADER = ["claim_id", "txn_id", "account_id", "amount_cents", "currency_code", "post_ts", "entry_type", "desk_id"]
WINDOW_HEADER = ["account_id", "open_ts", "close_ts", "state"]
REPORT_HEADER = ["claim_id", "txn_id", "account_id", "desk_id", "currency_code", "amount_cents", "entry_type", "status"]
SCRIPT_HASHES = {
    APP / "scripts" / "run_batch.sh": "78627b421ff9280d32c6b7acc5e3ebb0c522d74948cbf7a67bd5cead539ccb04",
    APP / "scripts" / "pli_ledger.awk": "487f0581b992c1e6ddd40ba16637057a08812f60964a9f7f9272086dc6433ce5",
}


def write_psv(path: Path, header, rows):
    path.write_text("|".join(header) + "\n" + "\n".join("|".join(row) for row in rows) + "\n", encoding="utf-8")


def write_rules():
    (APP / "src" / "ledger_rules.pli").write_text(
        "\n".join(
            [
                "DCL ELIGIBLE_STATE CHAR(12) INIT('LIVE');",
                "DCL OPEN_FX_STATE CHAR(8) INIT('OPEN');",
                "DCL REASON_1 CHAR(12) INIT('GO');",
                "DCL REASON_2 CHAR(12) INIT('CHK');",
                "DCL REASON_3 CHAR(12) INIT('WAIT');",
                "DCL ALIAS_1 CHAR(20) INIT('f=>FED');",
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


def prepare_windows():
    write_psv(APP / "config" / "fx_windows.psv", WINDOW_HEADER, [["991100", "20260612115900", "20260612123000", "OPEN"]])
    (APP / "out").mkdir(exist_ok=True)


def test_m2_keeps_fixed_batch_harness_unmodified():
    """Alias behavior is enabled through PL/I control files, not script edits."""
    for path, expected in SCRIPT_HASHES.items():
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == expected, f"{path} changed: expected {expected}, got {actual}"


def test_m2_multiple_aliases_are_case_insensitive_and_emit_canonical_only_on_cleared_rows():
    """Exercise all configured aliases so a single hardcoded alias cannot pass."""
    write_rules()
    write_psv(
        APP / "data" / "ledger.psv",
        LEDGER_HEADER,
        [
            ["R-F", "991100", "11", "f", "NYC", "20260612120000", "LIVE", "TM"],
            ["R-A", "991100", "22", "ACH", "NYC", "20260612120100", "LIVE", "TM"],
            ["R-S", "991100", "33", "s", "BOS", "20260612120200", "LIVE", "TM"],
        ],
    )
    write_psv(
        APP / "data" / "postings.psv",
        POSTING_HEADER,
        [
            ["C-F", "R-F", "991100", "11", "FED", "20260612120500", "go", "NYC"],
            ["C-A", "R-A", "991100", "22", "a", "20260612120600", "CHK", "NYC"],
            ["C-S", "R-S", "991100", "33", "SWIFT", "20260612120700", "wait", "BOS"],
            ["C-X", "R-X", "991100", "44", "FED", "20260612120800", "go", "NYC"],
        ],
    )
    prepare_windows()

    rows, summary = run_batch()

    assert [r["status"] for r in rows] == ["CLEARED", "CLEARED", "CLEARED", "HELD"]
    assert [r["currency_code"] for r in rows] == ["FED", "ACH", "SWIFT", ""]
    assert summary == {
        "cleared_count": 3,
        "cleared_amount_cents": 66,
        "held_count": 1,
        "held_amount_cents": 44,
    }


def test_m2_keeps_full_key_consumption_and_blank_currency_for_held_alias_rows():
    """Alias normalization must not weaken the milestone-1 full-key and consume rules."""
    write_rules()
    write_psv(
        APP / "data" / "ledger.psv",
        LEDGER_HEADER,
        [["DUP-1", "991100", "90", "f", "NYC", "20260612120000", "LIVE", "TM"]],
    )
    write_psv(
        APP / "data" / "postings.psv",
        POSTING_HEADER,
        [
            ["C1", "DUP-1", "991100", "90", "FED", "20260612120500", "GO", "NYC"],
            ["C2", "DUP-1", "991100", "90", "FED", "20260612120600", "GO", "NYC"],
            ["C3", "DUP-1", "991999", "90", "FED", "20260612120700", "GO", "NYC"],
        ],
    )
    prepare_windows()

    rows, summary = run_batch()

    assert [r["status"] for r in rows] == ["CLEARED", "HELD", "HELD"]
    assert [r["currency_code"] for r in rows] == ["FED", "", ""]
    assert summary["cleared_count"] == 1
    assert summary["held_count"] == 2


def test_m2_alias_matching_still_rejects_an_unconsumed_full_key_mismatch():
    """An alias match cannot consume a row when one non-currency key differs."""
    write_rules()
    write_psv(
        APP / "data" / "ledger.psv",
        LEDGER_HEADER,
        [["ABCDE-ROW", "991100", "90", "f", "NYC", "20260612120000", "LIVE", "TM"]],
    )
    write_psv(
        APP / "data" / "postings.psv",
        POSTING_HEADER,
        [
            ["C-WRONG", "ABCDE-ROW", "991999", "90", "FED", "20260612120500", "GO", "NYC"],
            ["C-RIGHT", "ABCDE-ROW", "991100", "90", "FED", "20260612120600", "GO", "NYC"],
        ],
    )
    prepare_windows()

    rows, summary = run_batch()

    assert [r["status"] for r in rows] == ["HELD", "CLEARED"]
    assert [r["currency_code"] for r in rows] == ["", "FED"]
    assert summary == {
        "cleared_count": 1,
        "cleared_amount_cents": 90,
        "held_count": 1,
        "held_amount_cents": 90,
    }
