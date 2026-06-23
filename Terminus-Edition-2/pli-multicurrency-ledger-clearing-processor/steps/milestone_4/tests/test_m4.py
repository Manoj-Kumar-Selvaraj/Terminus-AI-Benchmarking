import csv
import hashlib
import os
import subprocess
from pathlib import Path

APP = Path("/app")
LEDGER_HEADER = ["txn_id", "account_id", "amount_cents", "currency_code", "desk_id", "book_ts", "state", "kind_code"]
POSTING_HEADER = ["claim_id", "txn_id", "account_id", "amount_cents", "currency_code", "post_ts", "entry_type", "desk_id"]
WINDOW_HEADER = ["account_id", "open_ts", "close_ts", "state"]
CONTROL_HEADER = ["account_id", "desk_id", "currency_code", "expected_count", "expected_amount_cents", "tolerance_cents"]
REPORT_HEADER = ["claim_id", "txn_id", "account_id", "desk_id", "currency_code", "amount_cents", "entry_type", "status"]
GROUP_HEADER = ["account_id", "desk_id", "currency_code", "actual_count", "actual_amount_cents", "expected_count", "expected_amount_cents", "tolerance_cents", "status"]
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
                "DCL OPEN_FX_STATE CHAR(8) INIT('GREEN');",
                "DCL REASON_1 CHAR(12) INIT('CLEAR');",
                "DCL REASON_2 CHAR(12) INIT('NET');",
                "DCL REASON_3 CHAR(12) INIT('FEE');",
                "DCL ALIAS_1 CHAR(20) INIT('u=>USD');",
                "DCL ALIAS_2 CHAR(20) INIT('d=>USD');",
                "DCL ALIAS_3 CHAR(20) INIT('e=>EUR');",
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def reset_out():
    out = APP / "out"
    out.mkdir(exist_ok=True)
    for child in out.iterdir():
        if child.is_file():
            child.unlink()


def read_rows(path: Path, header):
    text = path.read_text(encoding="utf-8")
    reader = csv.DictReader(text.splitlines(), delimiter="|")
    assert reader.fieldnames == header
    return list(reader)


def run_batch(expect_success=True, extra_env=None):
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    result = subprocess.run(["/app/scripts/run_batch.sh"], cwd=APP, env=env, text=True, capture_output=True, timeout=60)
    if expect_success:
        assert result.returncode == 0, result.stderr + result.stdout
    else:
        assert result.returncode != 0, result.stderr + result.stdout
    report = read_rows(APP / "out" / "ledger_report.csv", REPORT_HEADER)
    summary = {
        key: int(value)
        for key, value in (
            line.split("=", 1)
            for line in (APP / "out" / "ledger_summary.txt").read_text(encoding="utf-8").splitlines()
        )
    }
    groups = read_rows(APP / "out" / "clearing_groups.psv", GROUP_HEADER)
    return report, summary, groups, result


def seed_group_dataset():
    write_rules()
    write_psv(
        APP / "data" / "ledger.psv",
        LEDGER_HEADER,
        [
            ["G1-A", "AC100", "100", "u", "NYC", "20260612120000", "LIVE", "TM"],
            ["G1-B", "AC100", "200", "USD", "NYC", "20260612120100", "LIVE", "TM"],
            ["G2-A", "AC200", "70", "e", "LON", "20260612120200", "LIVE", "TM"],
            ["G2-B", "AC200", "80", "EUR", "LON", "20260612120300", "LIVE", "TM"],
            ["G3-A", "AC300", "90", "USD", "NYC", "20260612120400", "LIVE", "TM"],
        ],
    )
    write_psv(
        APP / "data" / "postings.psv",
        POSTING_HEADER,
        [
            ["P1", "G1-A", "AC100", "100", "d", "20260612120500", "CLEAR", "NYC"],
            ["P2", "G1-B", "AC100", "200", "USD", "20260612120600", "NET", "NYC"],
            ["P3", "G2-A", "AC200", "70", "EUR", "20260612120700", "CLEAR", "LON"],
            ["P4", "G2-B", "AC200", "80", "e", "20260612120800", "FEE", "LON"],
            ["P5", "G3-A", "AC300", "90", "USD", "20260612120900", "CLEAR", "NYC"],
        ],
    )
    write_psv(
        APP / "config" / "fx_windows.psv",
        WINDOW_HEADER,
        [
            ["AC100", "20260612115900", "20260612123000", "GREEN"],
            ["AC200", "20260612115900", "20260612123000", "GREEN"],
            ["AC300", "20260612115900", "20260612123000", "GREEN"],
        ],
    )
    write_psv(
        APP / "config" / "control_totals.psv",
        CONTROL_HEADER,
        [
            ["AC100", "NYC", "USD", "2", "300", "0"],
            ["AC200", "LON", "EUR", "2", "151", "1"],
            ["AC300", "NYC", "USD", "2", "90", "0"],  # count mismatch: row must be held
        ],
    )
    reset_out()


def test_m4_keeps_fixed_batch_harness_unmodified():
    """Control totals are enabled through PL/I control files, not script edits."""
    for path, expected in SCRIPT_HASHES.items():
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == expected, f"{path} changed: expected {expected}, got {actual}"


def test_m4_group_control_totals_change_row_status_and_emit_group_report():
    """Rows are not independently clearable when their group control total fails."""
    seed_group_dataset()

    report, summary, groups, _ = run_batch()
    assert [r["status"] for r in report] == ["CLEARED", "CLEARED", "CLEARED", "CLEARED", "HELD"]
    assert [r["currency_code"] for r in report] == ["USD", "USD", "EUR", "EUR", ""]
    assert summary == {
        "cleared_count": 4,
        "cleared_amount_cents": 450,
        "held_count": 1,
        "held_amount_cents": 90,
    }
    by_group = {(g["account_id"], g["desk_id"], g["currency_code"]): g for g in groups}
    assert by_group[("AC100", "NYC", "USD")]["status"] == "COMMITTED"
    assert by_group[("AC100", "NYC", "USD")]["actual_count"] == "2"
    assert by_group[("AC100", "NYC", "USD")]["actual_amount_cents"] == "300"
    assert by_group[("AC200", "LON", "EUR")]["status"] == "COMMITTED"
    assert by_group[("AC200", "LON", "EUR")]["actual_count"] == "2"
    assert by_group[("AC200", "LON", "EUR")]["actual_amount_cents"] == "150"
    assert by_group[("AC300", "NYC", "USD")]["status"] == "HELD_CONTROL"
    assert by_group[("AC300", "NYC", "USD")]["actual_count"] == "1"
    assert by_group[("AC300", "NYC", "USD")]["actual_amount_cents"] == "90"
    assert by_group[("AC200", "LON", "EUR")]["expected_amount_cents"] == "151"
    assert by_group[("AC200", "LON", "EUR")]["tolerance_cents"] == "1"


def test_m4_group_missing_control_total_is_held_control():
    """A cleared group absent from control_totals.psv is reported but not committed."""
    seed_group_dataset()
    write_psv(
        APP / "data" / "ledger.psv",
        LEDGER_HEADER,
        [["G4-A", "AC400", "120", "USD", "TKY", "20260612121000", "LIVE", "TM"]],
    )
    write_psv(
        APP / "data" / "postings.psv",
        POSTING_HEADER,
        [["P6", "G4-A", "AC400", "120", "USD", "20260612121100", "CLEAR", "TKY"]],
    )
    write_psv(
        APP / "config" / "fx_windows.psv",
        WINDOW_HEADER,
        [["AC400", "20260612115900", "20260612123000", "GREEN"]],
    )
    write_psv(APP / "config" / "control_totals.psv", CONTROL_HEADER, [])
    reset_out()

    report, summary, groups, _ = run_batch()

    assert report[0]["status"] == "HELD"
    assert report[0]["currency_code"] == ""
    assert summary["held_amount_cents"] == 120
    assert groups == [
        {
            "account_id": "AC400",
            "desk_id": "TKY",
            "currency_code": "USD",
            "actual_count": "1",
            "actual_amount_cents": "120",
            "expected_count": "",
            "expected_amount_cents": "",
            "tolerance_cents": "",
            "status": "HELD_CONTROL",
        }
    ]


def test_m4_matching_count_with_amount_outside_tolerance_holds_the_group():
    """A matching row count cannot commit when the amount difference exceeds tolerance."""
    write_rules()
    write_psv(
        APP / "data" / "ledger.psv",
        LEDGER_HEADER,
        [["G-AMT", "AC500", "100", "u", "NYC", "20260612120000", "LIVE", "TM"]],
    )
    write_psv(
        APP / "data" / "postings.psv",
        POSTING_HEADER,
        [["P-AMT", "G-AMT", "AC500", "100", "USD", "20260612120500", "CLEAR", "NYC"]],
    )
    write_psv(
        APP / "config" / "fx_windows.psv",
        WINDOW_HEADER,
        [["AC500", "20260612115900", "20260612123000", "GREEN"]],
    )
    write_psv(
        APP / "config" / "control_totals.psv",
        CONTROL_HEADER,
        [["AC500", "NYC", "USD", "1", "102", "1"]],
    )
    reset_out()

    report, summary, groups, _ = run_batch()

    assert report[0]["status"] == "HELD"
    assert report[0]["currency_code"] == ""
    assert summary == {
        "cleared_count": 0,
        "cleared_amount_cents": 0,
        "held_count": 1,
        "held_amount_cents": 100,
    }
    assert groups == [
        {
            "account_id": "AC500",
            "desk_id": "NYC",
            "currency_code": "USD",
            "actual_count": "1",
            "actual_amount_cents": "100",
            "expected_count": "1",
            "expected_amount_cents": "102",
            "tolerance_cents": "1",
            "status": "HELD_CONTROL",
        }
    ]


def test_m4_restart_after_abend_commits_groups_once_and_continues_pending_groups():
    """A rerun after a group-boundary ABEND must not duplicate committed groups."""
    seed_group_dataset()

    _, _, _, first = run_batch(expect_success=False, extra_env={"ABEND_AFTER_GROUPS": "1"})
    assert "ABEND_AFTER_GROUPS" in first.stderr
    first_commits = read_rows(APP / "out" / "clearing_commits.psv", ["account_id", "desk_id", "currency_code", "cleared_count", "cleared_amount_cents"])
    assert first_commits == [
        {"account_id": "AC100", "desk_id": "NYC", "currency_code": "USD", "cleared_count": "2", "cleared_amount_cents": "300"}
    ]

    report, summary, groups, _ = run_batch()

    final_commits = read_rows(APP / "out" / "clearing_commits.psv", ["account_id", "desk_id", "currency_code", "cleared_count", "cleared_amount_cents"])
    assert final_commits == [
        {"account_id": "AC100", "desk_id": "NYC", "currency_code": "USD", "cleared_count": "2", "cleared_amount_cents": "300"},
        {"account_id": "AC200", "desk_id": "LON", "currency_code": "EUR", "cleared_count": "2", "cleared_amount_cents": "150"},
    ]
    checkpoint = (APP / "out" / "restart_checkpoint.txt").read_text(encoding="utf-8")
    assert checkpoint.strip() == "last_committed_group=AC200|LON|EUR"
    assert checkpoint.count("\n") <= 1
    assert [r["status"] for r in report] == ["CLEARED", "CLEARED", "CLEARED", "CLEARED", "HELD"]
    assert summary["cleared_count"] == 4
    assert [g["status"] for g in groups] == ["COMMITTED", "COMMITTED", "HELD_CONTROL"]
