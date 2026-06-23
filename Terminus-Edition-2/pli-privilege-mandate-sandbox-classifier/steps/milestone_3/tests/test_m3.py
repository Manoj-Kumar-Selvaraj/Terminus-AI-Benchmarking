import csv
import subprocess
from pathlib import Path

APP = Path("/app")
MANDATE_HEADER = ["mandate_id", "service_id", "cap_token", "payload_hash", "sandbox_class", "recv_ts", "state", "kind_code"]
AUDIT_HEADER = ["claim_id", "mandate_id", "service_id", "cap_token", "payload_hash", "audit_ts", "verdict_code", "sandbox_class"]
WINDOW_HEADER = ["service_id", "open_ts", "close_ts", "state"]


def write_psv(path, header, rows):
    path.write_text("|".join(header) + "\n" + "\n".join("|".join(row) for row in rows) + "\n")


def configure_rules():
    (APP / "src" / "mandate_rules.pli").write_text(
        "\n".join(
            [
                "DCL ELIGIBLE_STATE CHAR(12) INIT('ACTIVE');",
                "DCL OPEN_SANDBOX_STATE CHAR(12) INIT('AVAILABLE');",
                "DCL REASON_1 CHAR(12) INIT('ALLOW');",
                "DCL REASON_2 CHAR(12) INIT('CHECK');",
                "DCL REASON_3 CHAR(12) INIT('DONE');",
                "DCL ALIAS_1 CHAR(24) INIT('old-box=>BOX-CANON');",
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


def write_single_case(recv_ts, audit_ts, windows, service_id="SERVICE-A"):
    write_psv(
        APP / "data" / "mandates.psv",
        MANDATE_HEADER,
        [["M-1", service_id, "10", "HASH-A", "old-box", recv_ts, "ACTIVE", "TM"]],
    )
    write_psv(
        APP / "data" / "sandbox_audits.psv",
        AUDIT_HEADER,
        [["C-1", "M-1", service_id, "10", "HASH-A", audit_ts, "allow", "BOX-CANON"]],
    )
    write_psv(APP / "config" / "sandbox_windows.psv", WINDOW_HEADER, windows)


def test_inclusive_window_boundaries_authorize():
    """Allow valid rows exactly at the configured open and close timestamps."""
    configure_rules()
    write_single_case(
        "20260612120000",
        "20260612123000",
        [[" service-a ", "20260612120000", "20260612123000", "available"]],
    )

    rows, summary = run_batch()

    assert rows[0]["status"] == "AUTHORIZED"
    assert rows[0]["sandbox_class"] == "BOX-CANON"
    assert summary == {
        "authorized_count": 1,
        "authorized_mandates": 10,
        "denied_count": 0,
        "denied_mandates": 0,
    }


def test_recv_and_audit_timestamps_are_independently_window_gated():
    """Deny when either endpoint falls outside the otherwise valid window."""
    configure_rules()
    window = [["SERVICE-A", "20260612120000", "20260612123000", "AVAILABLE"]]
    write_single_case("20260612115959", "20260612121000", window)
    assert run_batch()[0][0]["status"] == "DENIED"

    write_single_case("20260612120500", "20260612123001", window)
    assert run_batch()[0][0]["status"] == "DENIED"

    write_single_case("20260612122000", "20260612121000", window)
    assert run_batch()[0][0]["status"] == "DENIED"


def test_wrong_service_state_and_malformed_windows_are_denied():
    """Reject wrong-service, closed, malformed, missing, and reversed windows."""
    configure_rules()
    scenarios = [
        [["SERVICE-X", "20260612120000", "20260612123000", "AVAILABLE"]],
        [["SERVICE-A", "20260612120000", "20260612123000", "CLOSED"]],
        [["SERVICE-A", "BAD", "20260612123000", "AVAILABLE"]],
        [["SERVICE-A", "20260612124000", "20260612123000", "AVAILABLE"]],
        [],
    ]
    for windows in scenarios:
        write_single_case("20260612120500", "20260612121000", windows)
        rows, _ = run_batch()
        assert rows[0]["status"] == "DENIED"
        assert rows[0]["sandbox_class"] == ""


def test_latest_candidate_is_consumed_before_an_earlier_row():
    """Use later window eligibility to prove latest-recv selection and consumption."""
    configure_rules()
    write_psv(
        APP / "data" / "mandates.psv",
        MANDATE_HEADER,
        [
            ["M-1", "SERVICE-A", "15", "HASH-A", "BOX-CANON", "20260612120000", "ACTIVE", "TM"],
            ["M-1", "SERVICE-A", "15", "HASH-A", "old-box", "20260612120500", "ACTIVE", "TM"],
        ],
    )
    write_psv(
        APP / "data" / "sandbox_audits.psv",
        AUDIT_HEADER,
        [
            ["C-FIRST", "M-1", "SERVICE-A", "15", "HASH-A", "20260612121000", "ALLOW", "BOX-CANON"],
            ["C-SECOND", "M-1", "SERVICE-A", "15", "HASH-A", "20260612122000", "ALLOW", "BOX-CANON"],
        ],
    )
    write_psv(
        APP / "config" / "sandbox_windows.psv",
        WINDOW_HEADER,
        [
            ["SERVICE-A", "20260612115900", "20260612121000", "AVAILABLE"],
            ["SERVICE-A", "20260612120400", "20260612122000", "AVAILABLE"],
        ],
    )

    rows, summary = run_batch()

    assert [row["status"] for row in rows] == ["AUTHORIZED", "DENIED"]
    assert [row["sandbox_class"] for row in rows] == ["BOX-CANON", ""]
    assert summary == {
        "authorized_count": 1,
        "authorized_mandates": 15,
        "denied_count": 1,
        "denied_mandates": 15,
    }


def test_equal_recv_ts_uses_earliest_mandate_input_row():
    """Equal recv_ts candidates authorize in mandate file order and keep consumption exact."""
    configure_rules()
    write_psv(
        APP / "data" / "mandates.psv",
        MANDATE_HEADER,
        [
            ["M-EQ", "SERVICE-A", "15", "HASH-A", "BOX-CANON", "20260612120500", "ACTIVE", "TM"],
            ["M-EQ", "SERVICE-A", "15", "HASH-A", "old-box", "20260612120500", "ACTIVE", "TM"],
        ],
    )
    write_psv(
        APP / "data" / "sandbox_audits.psv",
        AUDIT_HEADER,
        [
            ["C-FIRST", "M-EQ", "SERVICE-A", "15", "HASH-A", "20260612121000", "ALLOW", "BOX-CANON"],
            ["C-SECOND", "M-EQ", "SERVICE-A", "15", "HASH-A", "20260612121100", "ALLOW", "BOX-CANON"],
            ["C-THIRD", "M-EQ", "SERVICE-A", "15", "HASH-A", "20260612121200", "ALLOW", "BOX-CANON"],
        ],
    )
    write_psv(
        APP / "config" / "sandbox_windows.psv",
        WINDOW_HEADER,
        [[" service-a ", "20260612120000", "20260612122000", "available"]],
    )

    rows, summary = run_batch()

    assert [row["status"] for row in rows] == ["AUTHORIZED", "AUTHORIZED", "DENIED"]
    assert [row["audit_class"] for row in rows] == ["BOX-CANON", "BOX-CANON", "BOX-CANON"]
    assert [row["sandbox_class"] for row in rows] == ["BOX-CANON", "BOX-CANON", ""]
    assert summary == {
        "authorized_count": 2,
        "authorized_mandates": 30,
        "denied_count": 1,
        "denied_mandates": 15,
    }
