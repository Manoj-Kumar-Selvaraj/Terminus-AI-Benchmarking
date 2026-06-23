"""Milestone 4 tests for the healthcare remittance return audit extract."""

import csv
import os
import subprocess
from pathlib import Path

APP = Path("/app")
WIRES = APP / "data" / "wires.dat"
RETURNS = APP / "data" / "returns.dat"
CALENDAR = APP / "config" / "cycle_calendar.txt"
AUDIT = APP / "out" / "wire_return_audit.csv"
REPORT = APP / "out" / "wire_return_report.csv"
SUMMARY = APP / "out" / "wire_return_summary.txt"
COBOL_SOURCE = APP / "src" / "wire_returns.cbl"
BINARY = APP / "build" / "batch"


def assert_compile_requires_cobol_source():
    """compile.sh must fail when the COBOL source file is unavailable."""
    backup = COBOL_SOURCE.with_suffix(".cbl.hidden")
    BINARY.unlink(missing_ok=True)
    COBOL_SOURCE.rename(backup)
    try:
        result = subprocess.run(["/app/scripts/compile.sh"], cwd=APP, timeout=60)
        assert result.returncode != 0
        assert not BINARY.exists()
    finally:
        backup.rename(COBOL_SOURCE)


def compile_with_cobc_probe():
    """Compile while proving compile.sh invokes cobc on the task .cbl file."""
    real_cobc = subprocess.check_output(["bash", "-lc", "command -v cobc"], text=True).strip()
    probe_dir = APP / "build" / "cobc-probe"
    log_path = APP / "build" / "cobc-args.log"
    probe_dir.mkdir(parents=True, exist_ok=True)
    log_path.unlink(missing_ok=True)
    wrapper = probe_dir / "cobc"
    wrapper.write_text(
        "#!/usr/bin/env bash\n"
        'printf "%s\\n" "$@" >> /app/build/cobc-args.log\n'
        f'exec "{real_cobc}" "$@"\n'
    )
    wrapper.chmod(0o755)
    env = os.environ.copy()
    env["PATH"] = f"{probe_dir}:{env['PATH']}"
    subprocess.run(["/app/scripts/compile.sh"], check=True, cwd=APP, env=env, timeout=60)
    args = log_path.read_text()
    assert str(COBOL_SOURCE) in args
    assert str(BINARY) in args


def compile_program():
    """Compile the COBOL batch and verify the produced ELF binary."""
    assert_compile_requires_cobol_source()
    compile_with_cobc_probe()
    assert COBOL_SOURCE.exists()
    assert BINARY.read_bytes().startswith(b"\x7fELF")


def write_inputs(wires, returns, calendar=None):
    """Rewrite fixed-width inputs and the cycle calendar for a focused audit scenario."""
    WIRES.write_text("\n".join(wires) + "\n")
    RETURNS.write_text("\n".join(returns) + "\n")
    calendar_rows = calendar or [
        "20260501 OPEN",
        "20260502 OPEN",
        "20260503 CLOSED",
    ]
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")


def run_program():
    """Run the batch and parse the report, audit extract, and summary outputs."""
    subprocess.run(["/app/build/batch"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        report_rows = list(csv.DictReader(handle))
    with AUDIT.open(newline="") as handle:
        audit_rows = list(csv.DictReader(handle))
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        summary[key] = int(value)
    return report_rows, audit_rows, summary


class TestMilestone4:
    def test_audit_extract_tracks_report_outcomes(self):
        """The audit extract should mirror the main report outcomes and schema."""
        compile_program()
        write_inputs(
            ["WHCL990000001MED0000000150ACCT9901S20260501", "WHCL990000002PHR0000000250ACCT9902S20260501"],
            ["RHCL9900000010000000150ACCT990120260501", "RHCL9900000020000000250ACCT990220260503"],
        )
        report_rows, audit_rows, summary = run_program()
        assert [row["status"] for row in report_rows] == ["CLEARED", "EXCEPTION"]
        assert [row["status"] for row in audit_rows] == ["CLEARED", "EXCEPTION"]
        assert [row["id"] for row in audit_rows] == ["HCL990000001", "HCL990000002"]
        assert [row["amount_cents"] for row in audit_rows] == ["0000000150", "0000000250"]
        assert AUDIT.read_text().splitlines()[0] == "id,amount_cents,status"
        assert summary["cleared_count"] == 1
        assert summary["exception_count"] == 1

    def test_audit_extract_all_cleared_rows_tracks_report_alignment(self):
        """The audit extract should stay aligned when both returns clear."""
        compile_program()
        write_inputs(
            [
                "WHCL991000001MED0000000100ACCT9910S20260501",
                "WHCL991000001MED0000000100ACCT9910S20260502",
            ],
            [
                "RHCL9910000010000000100ACCT991020260501",
                "RHCL9910000010000000100ACCT991020260502",
            ],
        )
        report_rows, audit_rows, summary = run_program()

        assert [row["status"] for row in report_rows] == ["CLEARED", "CLEARED"]
        assert [row["status"] for row in audit_rows] == ["CLEARED", "CLEARED"]
        assert [row["wire_id"] for row in report_rows] == ["HCL991000001", "HCL991000001"]
        assert [row["id"] for row in audit_rows] == ["HCL991000001", "HCL991000001"]
        assert AUDIT.read_text().splitlines()[0] == "id,amount_cents,status"
        assert summary == {
            "cleared_count": 2,
            "cleared_amount_cents": 200,
            "exception_count": 0,
            "exception_amount_cents": 0,
        }

    def test_audit_extract_keeps_exception_order_when_no_wire_matches(self):
        """The audit extract should preserve return order when every return becomes an exception."""
        compile_program()
        write_inputs(
            ["WHCL992000001MED0000000400ACCT9920S20260501"],
            [
                "RHCL9920000990000000500ACCT992020260501",
                "RHCL9920000980000000600ACCT992020260502",
            ],
        )
        report_rows, audit_rows, summary = run_program()

        assert [row["status"] for row in report_rows] == ["EXCEPTION", "EXCEPTION"]
        assert [row["status"] for row in audit_rows] == ["EXCEPTION", "EXCEPTION"]
        assert [row["wire_id"] for row in report_rows] == ["HCL992000099", "HCL992000098"]
        assert [row["id"] for row in audit_rows] == ["HCL992000099", "HCL992000098"]
        assert AUDIT.read_text().splitlines()[0] == "id,amount_cents,status"
        assert summary == {
            "cleared_count": 0,
            "cleared_amount_cents": 0,
            "exception_count": 2,
            "exception_amount_cents": 1100,
        }
