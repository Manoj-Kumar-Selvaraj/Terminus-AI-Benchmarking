import csv
import subprocess
from pathlib import Path

APP = Path("/app")
REPORT_HEADER = [
    "claim_id",
    "mandate_id",
    "service_id",
    "audit_class",
    "sandbox_class",
    "cap_token",
    "verdict_code",
    "status",
]


def write_psv(path, header, rows):
    path.write_text("|".join(header) + "\n" + "\n".join("|".join(row) for row in rows) + "\n")


def write_rules():
    (APP / "src" / "mandate_rules.pli").write_text(
        "\n".join(
            [
                "DCL ELIGIBLE_STATE CHAR(12) INIT('LIVE');",
                "DCL OPEN_SANDBOX_STATE CHAR(8) INIT('OPEN');",
                "DCL REASON_1 CHAR(12) INIT('APPROVE');",
                "DCL REASON_2 CHAR(12) INIT('WATCH');",
                "DCL REASON_3 CHAR(12) INIT('DONE');",
                "DCL ALIAS_1 CHAR(20) INIT('legacy=>CANON');",
            ]
        )
        + "\n"
    )


def run_batch():
    out = APP / "out"
    out.mkdir(exist_ok=True)
    for name in ("mandate_report.csv", "mandate_summary.txt"):
        (out / name).unlink(missing_ok=True)
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with (out / "mandate_report.csv").open(newline="") as handle:
        reader = csv.DictReader(handle, delimiter="|")
        rows = list(reader)
        header = reader.fieldnames
    summary = dict(
        line.split("=", 1) for line in (out / "mandate_summary.txt").read_text().splitlines()
    )
    return header, rows, {key: int(value) for key, value in summary.items()}


def test_full_matching_eligibility_consumption_and_outputs():
    """Verify strict keys, policy gates, consumption, schemas, and audit-side totals."""
    write_rules()
    write_psv(
        APP / "data" / "mandates.psv",
        ["mandate_id", "service_id", "cap_token", "payload_hash", "sandbox_class", "recv_ts", "state", "kind_code"],
        [
            ["MANDATE-100", "SERVICE-A", "10", "HASH-A", "CLASS-A", "20260612120000", "LIVE", "TM"],
            ["MANDATE-200", "SERVICE-B", "20", "HASH-B", "CLASS-B", "20260612120100", "BLOCKED", "TM"],
            ["MANDATE-300", "SERVICE-C", "30", "HASH-C", "CLASS-C", "BAD-TIMESTAMP", "LIVE", "TM"],
        ],
    )
    write_psv(
        APP / "data" / "sandbox_audits.psv",
        ["claim_id", "mandate_id", "service_id", "cap_token", "payload_hash", "audit_ts", "verdict_code", "sandbox_class"],
        [
            ["C1", "mandate-100", "service-a", "10", "hash-a", "20260612120500", "approve", "class-a"],
            ["C2", "MANDATE-100", "SERVICE-A", "10", "HASH-A", "20260612120600", "APPROVE", "CLASS-A"],
            ["C3", "MANDATE-200", "SERVICE-B", "20", "HASH-B", "20260612120700", "WATCH", "CLASS-B"],
            ["C4", "MANDATE-300", "SERVICE-C", "30", "HASH-C", "20260612120800", "DONE", "CLASS-C"],
            ["C5", "MANDATE-100", "SERVICE-A", "11", "HASH-A", "20260612120900", "APPROVE", "CLASS-A"],
            ["C6", "MANDATE-100", "SERVICE-A", "10", "HASH-X", "20260612121000", "NOPE", "CLASS-A"],
        ],
    )
    write_psv(
        APP / "config" / "sandbox_windows.psv",
        ["service_id", "open_ts", "close_ts", "state"],
        [["SERVICE-X", "20200101000000", "20200101000001", "CLOSED"]],
    )

    header, rows, summary = run_batch()

    assert header == REPORT_HEADER
    assert [row["claim_id"] for row in rows] == ["C1", "C2", "C3", "C4", "C5", "C6"]
    assert [row["status"] for row in rows] == [
        "AUTHORIZED",
        "DENIED",
        "DENIED",
        "DENIED",
        "DENIED",
        "DENIED",
    ]
    assert rows[0]["sandbox_class"] == "CLASS-A"
    assert rows[0]["audit_class"] == "class-a"
    assert all(row["sandbox_class"] == "" for row in rows[1:])
    assert summary == {
        "authorized_count": 1,
        "authorized_mandates": 10,
        "denied_count": 5,
        "denied_mandates": 81,
    }


def test_each_full_key_is_required_without_prefix_shortcuts():
    """Reject rows when exactly one of the five compare keys differs."""
    write_rules()
    source = ["MANDATE-ABCDE-1", "SERVICE-A", "17", "HASH-A", "CLASS-A", "20260612120000", "LIVE", "TM"]
    write_psv(
        APP / "data" / "mandates.psv",
        ["mandate_id", "service_id", "cap_token", "payload_hash", "sandbox_class", "recv_ts", "state", "kind_code"],
        [source] * 5,
    )
    audits = [
        ["C-ID", "MANDATE-ABCDE-2", "SERVICE-A", "17", "HASH-A", "20260612121000", "APPROVE", "CLASS-A"],
        ["C-SVC", "MANDATE-ABCDE-1", "SERVICE-X", "17", "HASH-A", "20260612121000", "APPROVE", "CLASS-A"],
        ["C-CAP", "MANDATE-ABCDE-1", "SERVICE-A", "18", "HASH-A", "20260612121000", "APPROVE", "CLASS-A"],
        ["C-HASH", "MANDATE-ABCDE-1", "SERVICE-A", "17", "HASH-X", "20260612121000", "APPROVE", "CLASS-A"],
        ["C-CLASS", "MANDATE-ABCDE-1", "SERVICE-A", "17", "HASH-A", "20260612121000", "APPROVE", "CLASS-X"],
    ]
    write_psv(
        APP / "data" / "sandbox_audits.psv",
        ["claim_id", "mandate_id", "service_id", "cap_token", "payload_hash", "audit_ts", "verdict_code", "sandbox_class"],
        audits,
    )

    _, rows, summary = run_batch()

    assert [row["status"] for row in rows] == ["DENIED"] * 5
    assert summary == {
        "authorized_count": 0,
        "authorized_mandates": 0,
        "denied_count": 5,
        "denied_mandates": 86,
    }


def test_tiebreak_latest_recv_ts_then_remaining_rows_are_consumed():
    """Multiple eligible mandates choose latest recv_ts and keep older rows available."""
    write_rules()
    write_psv(
        APP / "data" / "mandates.psv",
        ["mandate_id", "service_id", "cap_token", "payload_hash", "sandbox_class", "recv_ts", "state", "kind_code"],
        [
            ["M-TIE", "SERVICE-A", "25", "HASH-A", "CLASS-A", "20260612110000", "LIVE", "TM"],
            ["M-TIE", "SERVICE-A", "25", "HASH-A", "CLASS-B", "20260612120000", "LIVE", "TM"],
            ["M-TIE", "SERVICE-A", "25", "HASH-A", "CLASS-C", "20260612120000", "LIVE", "TM"],
        ],
    )
    write_psv(
        APP / "data" / "sandbox_audits.psv",
        ["claim_id", "mandate_id", "service_id", "cap_token", "payload_hash", "audit_ts", "verdict_code", "sandbox_class"],
        [
            ["C-LATEST", "M-TIE", "SERVICE-A", "25", "HASH-A", "20260612130000", "APPROVE", "CLASS-B"],
            ["C-EQUAL", "M-TIE", "SERVICE-A", "25", "HASH-A", "20260612130100", "APPROVE", "CLASS-C"],
            ["C-OLDER", "M-TIE", "SERVICE-A", "25", "HASH-A", "20260612130200", "APPROVE", "CLASS-A"],
            ["C-EMPTY", "M-TIE", "SERVICE-A", "25", "HASH-A", "20260612130300", "APPROVE", "CLASS-A"],
        ],
    )

    _, rows, summary = run_batch()

    assert [row["status"] for row in rows] == ["AUTHORIZED", "AUTHORIZED", "AUTHORIZED", "DENIED"]
    assert [row["sandbox_class"] for row in rows] == ["CLASS-B", "CLASS-C", "CLASS-A", ""]
    assert summary == {
        "authorized_count": 3,
        "authorized_mandates": 75,
        "denied_count": 1,
        "denied_mandates": 25,
    }
