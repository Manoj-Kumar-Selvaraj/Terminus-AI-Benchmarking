"""Milestone 3 tests for healthcare remittance return settlement-cycle controls."""

import csv
import os
import subprocess
from pathlib import Path

APP = Path("/app")
WIRES = APP / "data" / "wires.dat"
RETURNS = APP / "data" / "returns.dat"
CALENDAR = APP / "config" / "cycle_calendar.txt"
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


def write_inputs(wires, returns, calendar):
    """Rewrite fixed-width input files and the cycle calendar for one scenario."""
    WIRES.write_text("\n".join(wires) + "\n")
    RETURNS.write_text("\n".join(returns) + "\n")
    CALENDAR.write_text("\n".join(calendar) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


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


class TestMilestone3:
    """Verify cycle calendar windows and latest eligible wire selection."""

    def test_cycle_window_open_dates_and_latest_eligible_wire(self):
        """Cycle windows should skip closed dates and choose the latest eligible wire."""
        compile_program()
        write_inputs(
            [
                "WHCL910000001MED0000000100ACCT9101S20260429",
                "WHCL910000001COP0000000100ACCT9101S20260430",
                "WHCL910000002PHR0000000200ACCT9102S20260429",
                "WHCL910000003ADJ0000000300ACCT9103S20260430",
                "WHCL910000004MED0000000400ACCT9104S20260501",
                "WHCL910000005COP0000000500ACCT9105S20260430",
                "WHCL910000006PHR0000000600ACCT9106S20260428",
                "WHCL910000007ADJ0000000700ACCT9107S20260430",
            ],
            [
                "RHCL9100000010000000100ACCT910120260501",
                "RHCL9100000020000000200ACCT910220260504",
                "RHCL9100000030000000300ACCT910320260502",
                "RHCL9100000040000000400ACCT910420260430",
                "RHCL9100000050000000500ACCT910520260504",
                "RHCL9100000060000000600ACCT910620260501",
                "RHCL9100000070000000700ACCT910720260501",
            ],
            [
                "20260428 OPEN",
                "20260429 OPEN",
                "20260430 OPEN",
                "20260501 OPEN",
                "20260502 CLOSED",
                "20260503 OPEN",
                "20260504 OPEN",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == [
            "CLEARED",
            "EXCEPTION",
            "EXCEPTION",
            "EXCEPTION",
            "EXCEPTION",
            "EXCEPTION",
            "CLEARED",
        ]
        assert rows[0]["reason"] == "COP"
        assert [row["account_id"] for row in rows] == [
            "ACCT9101",
            "ACCT9102",
            "ACCT9103",
            "ACCT9104",
            "ACCT9105",
            "ACCT9106",
            "ACCT9107",
        ]
        assert rows[0]["amount_cents"] == "0000000100"
        assert rows[6]["reason"] == "ADJ"
        assert [row["reason"] for row in rows[1:6]] == ["", "", "", "", ""]
        assert summary["cleared_count"] == 2
        assert summary["cleared_amount_cents"] == 800
        assert summary["exception_count"] == 5
        assert summary["exception_amount_cents"] == 2000

    def test_same_day_and_tie_breaker_use_earliest_wire_input_row(self):
        """Same-day returns should clear, and same-date candidate ties use wire input order."""
        compile_program()
        write_inputs(
            [
                "WHCL920000001MED0000000900ACCT9201S20260430",
                "WHCL920000001COP0000000900ACCT9201S20260430",
                "WHCL920000002PHR0000000800ACCT9202S20260501",
            ],
            [
                "RHCL9200000010000000900ACCT920120260430",
                "RHCL9200000010000000900ACCT920120260430",
                "RHCL9200000020000000800ACCT920220260501",
            ],
            [
                "20260430 OPEN",
                "20260501 OPEN",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["CLEARED", "CLEARED", "CLEARED"]
        assert [row["reason"] for row in rows] == ["MED", "COP", "PHR"]
        assert summary["cleared_count"] == 3
        assert summary["cleared_amount_cents"] == 2600
        assert summary["exception_count"] == 0

    def test_exactly_two_open_cycle_days_is_eligible(self):
        """A return on the second open day after settlement should still clear."""
        compile_program()
        write_inputs(
            [
                "WHCL930000001MED0000001100ACCT9301S20260430",
                "WHCL930000002PHR0000001200ACCT9302S20260430",
            ],
            [
                "RHCL9300000010000001100ACCT930120260504",
                "RHCL9300000020000001200ACCT930220260505",
            ],
            [
                "20260430 OPEN",
                "20260501 OPEN",
                "20260502 CLOSED",
                "20260503 CLOSED",
                "20260504 OPEN",
                "20260505 OPEN",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["CLEARED", "EXCEPTION"]
        assert [row["reason"] for row in rows] == ["MED", ""]
        assert summary["cleared_count"] == 1
        assert summary["cleared_amount_cents"] == 1100
        assert summary["exception_count"] == 1
        assert summary["exception_amount_cents"] == 1200

    def test_closed_settlement_date_is_not_eligible(self):
        """A CLOSED settlement date should not clear even when the return date is OPEN."""
        compile_program()
        write_inputs(
            ["WHCL950000001MED0000000100ACCT9501S20260502"],
            ["RHCL9500000010000000100ACCT950120260503"],
            [
                "20260501 OPEN",
                "20260502 CLOSED",
                "20260503 OPEN",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "EXCEPTION"
        assert rows[0]["reason"] == ""
        assert summary["cleared_count"] == 0
        assert summary["cleared_amount_cents"] == 0
        assert summary["exception_count"] == 1
        assert summary["exception_amount_cents"] == 100

    def test_calendar_status_is_case_insensitive_and_order_independent(self):
        """Mixed-case calendar statuses and unsorted calendar rows should still drive eligibility."""
        compile_program()
        write_inputs(
            [
                "WHCL970000001MED0000001500ACCT9701S20260501",
                "WHCL970000002PHR0000001600ACCT9702S20260502",
                "WHCL970000003ADJ0000001700ACCT9703S20260503",
            ],
            [
                "RHCL9700000010000001500ACCT970120260503",
                "RHCL9700000020000001600ACCT970220260504",
                "RHCL9700000030000001700ACCT970320260505",
            ],
            [
                "20260505 open",
                "20260503 OPEN",
                "20260501 Open",
                "20260504 CLOSED",
                "20260502 closed",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["CLEARED", "EXCEPTION", "CLEARED"]
        assert [row["reason"] for row in rows] == ["MED", "", "ADJ"]
        assert summary["cleared_count"] == 2
        assert summary["cleared_amount_cents"] == 3200
        assert summary["exception_count"] == 1
        assert summary["exception_amount_cents"] == 1600

    def test_duplicate_returns_still_deduplicated_with_dates(self):
        """Prior duplicate-return protection should remain active with cycle dates."""
        compile_program()
        write_inputs(
            ["WHCL960000001COP0000000400ACCT9601S20260501"],
            [
                "RHCL9600000010000000400ACCT960120260502",
                "RHCL9600000010000000400ACCT960120260502",
            ],
            [
                "20260501 OPEN",
                "20260502 OPEN",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["CLEARED", "EXCEPTION"]
        assert [row["reason"] for row in rows] == ["COP", ""]
        assert summary["cleared_count"] == 1
        assert summary["cleared_amount_cents"] == 400
        assert summary["exception_count"] == 1
        assert summary["exception_amount_cents"] == 400

    def test_blank_dates_and_absent_calendar_rows_are_ineligible(self):
        """Blank dates and dates missing from the calendar should not clear."""
        compile_program()
        write_inputs(
            [
                "WHCL940000001MED0000000100ACCT9401S",
                "WHCL940000002COP0000000200ACCT9402S20260506",
                "WHCL940000003ADJ0000000300ACCT9403S20260507",
            ],
            [
                "RHCL9400000010000000100ACCT940120260506",
                "RHCL9400000020000000200ACCT940220260507",
                "RHCL9400000030000000300ACCT9403",
            ],
            [
                "20260506 OPEN",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["EXCEPTION", "EXCEPTION", "EXCEPTION"]
        assert [row["reason"] for row in rows] == ["", "", ""]
        assert summary["cleared_count"] == 0
        assert summary["cleared_amount_cents"] == 0
        assert summary["exception_count"] == 3
        assert summary["exception_amount_cents"] == 600
