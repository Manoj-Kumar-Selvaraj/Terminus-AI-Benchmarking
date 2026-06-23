"""Milestone 1 tests for the wire return settlement task."""
import csv
import subprocess
from pathlib import Path

APP = Path("/app")
WIRES = APP / "data" / "wires.dat"
RETURNS = APP / "data" / "returns.dat"
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


class TestMilestone1:
    def test_b2b_return_clears_and_counts_positive_amount(self):
        """B2B return reasons should clear settled wires and add positive cents."""
        compile_program()
        write_inputs(
            ["WWIR202604101CON0000012500ACCT1001S", "WWIR202604102B2B0000008800ACCT1002S"],
            ["RWIR2026041010000012500ACCT1001", "RWIR2026041020000008800ACCT1002"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["CLEARED", "CLEARED"]
        assert rows[1]["reason"] == "B2B"
        assert summary["cleared_count"] == 2
        assert summary["cleared_amount_cents"] == 21300
        assert summary["exception_count"] == 0
        assert summary["exception_amount_cents"] == 0

    def test_ref_return_clears_as_allowed_reason(self):
        """REF is an allowed reason and should clear when every other gate passes."""
        compile_program()
        write_inputs(
            ["WWIR500000001REF0000007700ACCT5001S"],
            ["RWIR5000000010000007700ACCT5001"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "CLEARED"
        assert rows[0]["account_id"] == "ACCT5001"
        assert rows[0]["reason"] == "REF"
        assert summary["cleared_count"] == 1
        assert summary["cleared_amount_cents"] == 7700
        assert summary["exception_count"] == 0
        assert summary["exception_amount_cents"] == 0

    def test_wire_id_match_uses_all_12_characters(self):
        """A return must not clear a wire sharing only the leading id prefix."""
        compile_program()
        write_inputs(
            ["WWIR777770001CON0000003300ACCT2001S", "WWIR777770002CON0000003300ACCT2001S"],
            ["RWIR7777700030000003300ACCT2001", "RWIR7777700020000003300ACCT2001"],
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
                "WWIR300000001CON0000001000ACCT3001S",
                "WWIR300000002REF0000002000ACCT3002S",
                "WWIR300000003ADM0000003000ACCT3003P",
                "WWIR300000004INT0000004000ACCT3004S",
                "WWIR300000005B2B0000005000ACCT3005S",
            ],
            [
                "RWIR3000000010000001000ACCT9999",
                "RWIR3000000020000002100ACCT3002",
                "RWIR3000000030000003000ACCT3003",
                "RWIR3000000040000004000ACCT3004",
                "RWIR3000000050000005000ACCT3005",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["EXCEPTION", "EXCEPTION", "EXCEPTION", "EXCEPTION", "CLEARED"]
        assert all(row["reason"] == "" for row in rows if row["status"] == "EXCEPTION")
        assert summary["cleared_amount_cents"] == 5000
        assert summary["exception_count"] == 4
        assert summary["exception_amount_cents"] == 10100

    def test_report_schema_order_and_zero_padded_amounts_are_stable(self):
        """The report schema, return input order, and zero-padded amount text should stay stable."""
        compile_program()
        write_inputs(
            [
                "WWIR900000001CON0000000100ACCT9001S",
                "WWIR900000002B2B0000000200ACCT9002S",
                "WWIR900000003ADM0000000300ACCT9003S",
            ],
            [
                "RWIR9000000030000000300ACCT9003",
                "RWIR9000000010000000100ACCT9001",
                "RWIR9000000020000000200ACCT9002",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "wire_id,account_id,reason,amount_cents,status"
        assert [row["wire_id"] for row in rows] == ["WIR900000003", "WIR900000001", "WIR900000002"]
        assert [row["account_id"] for row in rows] == ["ACCT9003", "ACCT9001", "ACCT9002"]
        assert [row["amount_cents"] for row in rows] == ["0000000300", "0000000100", "0000000200"]
        assert summary["cleared_count"] == 3
        assert summary["cleared_amount_cents"] == 600
        assert summary["exception_count"] == 0
        assert summary["exception_amount_cents"] == 0

    def test_runtime_reason_codes_loaded_from_config_without_recompile(self):
        """Allowed reasons must come from reason_codes.csv at runtime, not hardcoded OR clauses."""
        compile_program()
        original_codes = REASON_CODES.read_text()
        try:
            REASON_CODES.write_text(
                original_codes.rstrip() + "\nTST,test return\n",
            )
            write_inputs(
                ["WWIR600000001TST0000006600ACCT6001S"],
                ["RWIR6000000010000006600ACCT6001"],
            )
            rows, summary = run_program()
            assert rows[0]["status"] == "CLEARED"
            assert rows[0]["reason"] == "TST"
            assert summary["cleared_count"] == 1
            assert summary["cleared_amount_cents"] == 6600
        finally:
            REASON_CODES.write_text(original_codes)
