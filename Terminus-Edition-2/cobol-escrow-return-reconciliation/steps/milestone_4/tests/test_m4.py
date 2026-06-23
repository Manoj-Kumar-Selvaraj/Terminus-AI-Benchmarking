"""Milestone 4 tests for configurable settlement-cycle windows."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
WIRES = APP / "data" / "wires.dat"
RETURNS = APP / "data" / "returns.dat"
CALENDAR = APP / "config" / "cycle_calendar.txt"
JOB_PROPS = APP / "config" / "job.properties"
REASON_CODES = APP / "config" / "reason_codes.csv"
REPORT = APP / "out" / "wire_return_report.csv"
SUMMARY = APP / "out" / "wire_return_summary.txt"


def assert_cobol_binary():
    """Verify the batch still comes from the COBOL compile path."""
    compile_script = (APP / "scripts" / "compile.sh").read_text().lower()
    assert "cobc" in compile_script
    assert ".cbl" in compile_script
    assert any((APP / "src").glob("*.cbl"))
    assert (APP / "build" / "batch").read_bytes().startswith(b"\x7fELF")


def compile_program():
    """Compile the COBOL wire return program."""
    subprocess.run(["/app/scripts/compile.sh"], check=True, cwd=APP, timeout=60)
    assert_cobol_binary()


def write_inputs(wires, returns, calendar, job_props_lines, reason_codes=None):
    """Rewrite fixed-width input files, calendar, and job properties for one scenario."""
    WIRES.write_text("\n".join(wires) + "\n")
    RETURNS.write_text("\n".join(returns) + "\n")
    CALENDAR.write_text("\n".join(calendar) + "\n")
    JOB_PROPS.write_text("\n".join(job_props_lines) + "\n")
    if reason_codes is not None:
        REASON_CODES.write_text(reason_codes)
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


class TestMilestone4:
    """Verify configurable cycle windows using job.properties."""

    def test_cycle_window_can_be_zero_open_days(self):
        """When the window is 0, only same-day returns can clear."""
        compile_program()
        write_inputs(
            [
                "WWIR810000001CON0000000100ACCT8101S20260430",
                "WWIR810000002REF0000000200ACCT8102S20260430",
            ],
            [
                "RWIR8100000010000000100ACCT810120260430",
                "RWIR8100000020000000200ACCT810220260501",
            ],
            [
                "20260430 OPEN",
                "20260501 OPEN",
            ],
            [
                "report=/app/out/wire_return_report.csv",
                "summary=/app/out/wire_return_summary.txt",
                "cycle_window_open_days=0",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["CLEARED", "EXCEPTION"]
        assert [row["reason"] for row in rows] == ["CON", ""]
        assert summary["cleared_count"] == 1
        assert summary["cleared_amount_cents"] == 100
        assert summary["exception_count"] == 1
        assert summary["exception_amount_cents"] == 200

    def test_cycle_window_can_be_three_open_days(self):
        """When the window is 3, a third open day after settlement is still eligible."""
        compile_program()
        write_inputs(
            ["WWIR820000001B2B0000000700ACCT8201S20260430"],
            ["RWIR8200000010000000700ACCT820120260504"],
            [
                "20260430 OPEN",
                "20260501 CLOSED",
                "20260502 OPEN",
                "20260503 OPEN",
                "20260504 OPEN",
            ],
            [
                "report=/app/out/wire_return_report.csv",
                "summary=/app/out/wire_return_summary.txt",
                "cycle_window_open_days=3",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "CLEARED"
        assert rows[0]["reason"] == "B2B"
        assert summary["cleared_count"] == 1
        assert summary["cleared_amount_cents"] == 700
        assert summary["exception_count"] == 0

    def test_both_wire_and_return_dates_blank_are_ineligible(self):
        """The configurable window must not make both blank dates eligible."""
        compile_program()
        write_inputs(
            ["WWIR990000001CON0000000100ACCT9901S"],
            ["RWIR9900000010000000100ACCT9901"],
            ["20260501 OPEN"],
            [
                "report=/app/out/wire_return_report.csv",
                "summary=/app/out/wire_return_summary.txt",
                "cycle_window_open_days=2",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "EXCEPTION"
        assert rows[0]["reason"] == ""
        assert summary["cleared_count"] == 0
        assert summary["cleared_amount_cents"] == 0
        assert summary["exception_count"] == 1
        assert summary["exception_amount_cents"] == 100

    def test_missing_cycle_window_defaults_to_two(self):
        """When cycle_window_open_days is absent, default to window=2."""
        compile_program()
        write_inputs(
            ["WWIR830000001CON0000000100ACCT8301S20260430"],
            ["RWIR8300000010000000100ACCT830120260504"],
            [
                "20260430 OPEN",
                "20260501 OPEN",
                "20260502 CLOSED",
                "20260503 CLOSED",
                "20260504 OPEN",
            ],
            [
                "report=/app/out/wire_return_report.csv",
                "summary=/app/out/wire_return_summary.txt",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "CLEARED"
        assert rows[0]["reason"] == "CON"
        assert summary["cleared_count"] == 1
        assert summary["cleared_amount_cents"] == 100
        assert summary["exception_count"] == 0

    def test_blank_cycle_window_defaults_to_two(self):
        """When cycle_window_open_days is present but blank, default to window=2."""
        compile_program()
        write_inputs(
            ["WWIR830000001CON0000000100ACCT8301S20260430"],
            ["RWIR8300000010000000100ACCT830120260504"],
            [
                "20260430 OPEN",
                "20260501 OPEN",
                "20260502 CLOSED",
                "20260503 CLOSED",
                "20260504 OPEN",
            ],
            [
                "report=/app/out/wire_return_report.csv",
                "summary=/app/out/wire_return_summary.txt",
                "cycle_window_open_days=",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "CLEARED"
        assert rows[0]["reason"] == "CON"
        assert summary["cleared_count"] == 1
        assert summary["cleared_amount_cents"] == 100
        assert summary["exception_count"] == 0

    def test_non_default_window_preserves_latest_wire_and_consumption(self):
        """Window=3 still picks the latest eligible wire and consumes it for duplicate returns."""
        compile_program()
        write_inputs(
            [
                "WWIR840000001CON0000000500ACCT8401S20260430",
                "WWIR840000001REF0000000500ACCT8401S20260502",
            ],
            [
                "RWIR8400000010000000500ACCT840120260504",
                "RWIR8400000010000000500ACCT840120260504",
            ],
            [
                "20260430 OPEN",
                "20260501 OPEN",
                "20260502 OPEN",
                "20260503 OPEN",
                "20260504 OPEN",
            ],
            [
                "report=/app/out/wire_return_report.csv",
                "summary=/app/out/wire_return_summary.txt",
                "cycle_window_open_days=3",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["CLEARED", "EXCEPTION"]
        assert rows[0]["reason"] == "REF"
        assert rows[1]["reason"] == ""
        assert summary["cleared_count"] == 1
        assert summary["cleared_amount_cents"] == 500
        assert summary["exception_count"] == 1
        assert summary["exception_amount_cents"] == 500

    def test_removed_reason_code_from_csv_blocks_matching(self):
        """Runtime reason_codes.csv loading must survive milestone 4 configurable windows."""
        compile_program()
        write_inputs(
            ["WWIR600000001B2B0000008800ACCT6001S20260430"],
            ["RWIR6000000010000008800ACCT600120260501"],
            [
                "20260430 OPEN",
                "20260501 OPEN",
            ],
            [
                "report=/app/out/wire_return_report.csv",
                "summary=/app/out/wire_return_summary.txt",
                "cycle_window_open_days=2",
            ],
            reason_codes="code,meaning\nCON,consumer return\nREF,refund return\nADM,administrative return\n",
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "EXCEPTION"
        assert rows[0]["reason"] == ""
        assert summary["cleared_count"] == 0
        assert summary["exception_count"] == 1
        assert summary["exception_amount_cents"] == 8800

