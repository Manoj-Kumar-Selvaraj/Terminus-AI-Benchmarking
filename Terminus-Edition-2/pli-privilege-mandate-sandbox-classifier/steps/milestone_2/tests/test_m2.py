import csv
import subprocess
from pathlib import Path

APP = Path("/app")


def write_psv(path, header, rows):
    path.write_text("|".join(header) + "\n" + "\n".join("|".join(row) for row in rows) + "\n")


def configure_rules():
    (APP / "src" / "mandate_rules.pli").write_text(
        "\n".join(
            [
                "DCL ELIGIBLE_STATE CHAR(12) INIT('LIVE');",
                "DCL OPEN_SANDBOX_STATE CHAR(8) INIT('OPEN');",
                "DCL REASON_1 CHAR(12) INIT('GO');",
                "DCL REASON_2 CHAR(12) INIT('CHECK');",
                "DCL REASON_3 CHAR(12) INIT('WAIT');",
                "DCL ALIAS_1 CHAR(30) INIT('svc-old=>SERVICE-CANON');",
                "DCL ALIAS_2 CHAR(30) INIT('hash-old=>HASH-CANON');",
                "DCL ALIAS_3 CHAR(30) INIT('box-old=>SANDBOX-CANON');",
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
    rows = list(csv.DictReader((out / "mandate_report.csv").open(), delimiter="|"))
    summary = dict(line.split("=", 1) for line in (out / "mandate_summary.txt").read_text().splitlines())
    return rows, {key: int(value) for key, value in summary.items()}


def test_aliases_apply_to_both_sides_of_all_text_compare_keys():
    """Normalize trimmed mixed-case aliases and emit the selected canonical class."""
    configure_rules()
    write_psv(
        APP / "data" / "mandates.psv",
        ["mandate_id", "service_id", "cap_token", "payload_hash", "sandbox_class", "recv_ts", "state", "kind_code"],
        [
            ["Mandate-1", " svc-old ", "25", "HASH-CANON", " box-old ", "20260612120000", "LIVE", "TM"],
            ["Mandate-2", "SERVICE-CANON", "30", " hash-old ", "SANDBOX-CANON", "20260612120100", "LIVE", "TM"],
        ],
    )
    write_psv(
        APP / "data" / "sandbox_audits.psv",
        ["claim_id", "mandate_id", "service_id", "cap_token", "payload_hash", "audit_ts", "verdict_code", "sandbox_class"],
        [
            ["C1", "mandate-1", "Service-Canon", "25", " hash-old ", "20260612121000", "go", "sandbox-canon"],
            ["C2", "MANDATE-2", "svc-old", "30", "HASH-CANON", "20260612121100", "CHECK", "box-old"],
        ],
    )

    rows, summary = run_batch()

    assert [row["status"] for row in rows] == ["AUTHORIZED", "AUTHORIZED"]
    assert [row["sandbox_class"] for row in rows] == ["SANDBOX-CANON", "SANDBOX-CANON"]
    assert summary == {
        "authorized_count": 2,
        "authorized_mandates": 55,
        "denied_count": 0,
        "denied_mandates": 0,
    }


def test_unknown_or_cross_mapped_values_remain_denied():
    """Keep unknown aliases distinct and blank the class on denied rows."""
    configure_rules()
    write_psv(
        APP / "data" / "mandates.psv",
        ["mandate_id", "service_id", "cap_token", "payload_hash", "sandbox_class", "recv_ts", "state", "kind_code"],
        [["M-9", "SERVICE-CANON", "40", "HASH-CANON", "SANDBOX-CANON", "20260612120000", "LIVE", "TM"]],
    )
    write_psv(
        APP / "data" / "sandbox_audits.psv",
        ["claim_id", "mandate_id", "service_id", "cap_token", "payload_hash", "audit_ts", "verdict_code", "sandbox_class"],
        [
            ["C-UNKNOWN", "M-9", "SERVICE-CANON", "40", "HASH-CANON", "20260612121000", "GO", "unknown-box"],
            ["C-CROSS", "M-9", "SERVICE-CANON", "40", "SANDBOX-CANON", "20260612121100", "GO", "hash-old"],
        ],
    )

    rows, summary = run_batch()

    assert [row["status"] for row in rows] == ["DENIED", "DENIED"]
    assert [row["sandbox_class"] for row in rows] == ["", ""]
    assert summary == {
        "authorized_count": 0,
        "authorized_mandates": 0,
        "denied_count": 2,
        "denied_mandates": 80,
    }
