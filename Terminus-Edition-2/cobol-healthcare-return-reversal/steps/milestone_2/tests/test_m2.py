"""Milestone 2 tests for the healthcare remittance return settlement task."""
import csv
import os
import subprocess
from pathlib import Path

APP = Path("/app")
WIRES = APP / "data" / "wires.dat"
RETURNS = APP / "data" / "returns.dat"
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


def assert_cobol_binary():
    """Verify the batch still comes from the COBOL compile path."""
    assert COBOL_SOURCE.exists()
    assert BINARY.read_bytes().startswith(b"\x7fELF")
    assert BINARY.stat().st_mtime_ns >= COBOL_SOURCE.stat().st_mtime_ns


def compile_program():
    """Compile the COBOL healthcare remittance return program."""
    assert_compile_requires_cobol_source()
    compile_with_cobc_probe()
    assert_cobol_binary()


def write_inputs(wires, returns):
    """Rewrite the fixed-width input files for a focused scenario."""
    WIRES.write_text("\n".join(wires) + "\n")
    RETURNS.write_text("\n".join(returns) + "\n")


def run_program():
    """Run the compiled program and return parsed report and summary outputs."""
    subprocess.run(["/app/build/batch"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        summary[key] = int(value)
    return rows, summary


class TestMilestone2:
    def test_cop_return_clears_and_counts_positive_amount(self):
        """COP return reasons should clear settled wires and add positive cents."""
        compile_program()
        write_inputs(
            ["WHCL202604101MED0000012500ACCT1001S", "WHCL202604102COP0000008800ACCT1002S"],
            ["RHCL2026041010000012500ACCT1001", "RHCL2026041020000008800ACCT1002"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["CLEARED", "CLEARED"]
        assert rows[1]["reason"] == "COP"
        assert summary["cleared_count"] == 2
        assert summary["cleared_amount_cents"] == 21300
        assert summary["exception_count"] == 0
        assert summary["exception_amount_cents"] == 0

    def test_wire_id_match_uses_all_12_characters(self):
        """A return must not clear a wire sharing only the leading id prefix."""
        compile_program()
        write_inputs(
            ["WHCL777770001MED0000003300ACCT2001S", "WHCL777770002MED0000003300ACCT2001S"],
            ["RHCL7777700030000003300ACCT2001", "RHCL7777700020000003300ACCT2001"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["EXCEPTION", "CLEARED"]
        assert summary["cleared_count"] == 1
        assert summary["cleared_amount_cents"] == 3300
        assert summary["exception_count"] == 1
        assert summary["exception_amount_cents"] == 3300

    def test_account_amount_status_and_reason_all_gate_clearing(self):
        """Account id, amount, settled status, and allowed reason must all be satisfied."""
        compile_program()
        write_inputs(
            [
                "WHCL300000001MED0000001000ACCT3001S",
                "WHCL300000002PHR0000002000ACCT3002S",
                "WHCL300000003ADJ0000003000ACCT3003P",
                "WHCL300000004INT0000004000ACCT3004S",
                "WHCL300000005COP0000005000ACCT3005S",
            ],
            [
                "RHCL3000000010000001000ACCT9999",
                "RHCL3000000020000002100ACCT3002",
                "RHCL3000000030000003000ACCT3003",
                "RHCL3000000040000004000ACCT3004",
                "RHCL3000000050000005000ACCT3005",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["EXCEPTION", "EXCEPTION", "EXCEPTION", "EXCEPTION", "CLEARED"]
        assert summary["cleared_amount_cents"] == 5000
        assert summary["exception_count"] == 4
        assert summary["exception_amount_cents"] == 10100

    def test_report_schema_order_and_zero_padded_amounts_are_stable(self):
        """The report schema, return input order, and zero-padded amount text should stay stable."""
        compile_program()
        write_inputs(
            [
                "WHCL900000001MED0000000100ACCT9001S",
                "WHCL900000002COP0000000200ACCT9002S",
                "WHCL900000003ADJ0000000300ACCT9003S",
            ],
            [
                "RHCL9000000030000000300ACCT9003",
                "RHCL9000000010000000100ACCT9001",
                "RHCL9000000020000000200ACCT9002",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "wire_id,account_id,reason,amount_cents,status"
        assert [row["wire_id"] for row in rows] == ["HCL900000003", "HCL900000001", "HCL900000002"]
        assert [row["account_id"] for row in rows] == ["ACCT9003", "ACCT9001", "ACCT9002"]
        assert [row["amount_cents"] for row in rows] == ["0000000300", "0000000100", "0000000200"]
        assert summary["cleared_count"] == 3
        assert summary["cleared_amount_cents"] == 600
        assert summary["exception_count"] == 0
        assert summary["exception_amount_cents"] == 0

    def test_duplicate_returns_do_not_reuse_consumed_wire(self):
        """Only the earliest eligible return may consume a matching settled wire."""
        compile_program()
        write_inputs(
            ["WHCL555500001COP0000007200ACCT5551S", "WHCL555500002PHR0000004100ACCT5552S"],
            [
                "RHCL5555000010000007200ACCT5551",
                "RHCL5555000010000007200ACCT5551",
                "RHCL5555000020000004100ACCT5552",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["CLEARED", "EXCEPTION", "CLEARED"]
        assert summary["cleared_count"] == 2
        assert summary["cleared_amount_cents"] == 11300
        assert summary["exception_count"] == 1
        assert summary["exception_amount_cents"] == 7200
