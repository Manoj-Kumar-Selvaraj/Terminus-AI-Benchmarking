"""Milestone 2 tests for the card chargeback clearing task."""
import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SALES = APP / "data" / "sales.dat"
CHARGEBACKS = APP / "data" / "chargebacks.dat"
REPORT = APP / "out" / "chargeback_report.csv"
SUMMARY = APP / "out" / "chargeback_summary.txt"
SUMMARY_FIELDS = (
    "applied_count",
    "applied_amount_cents",
    "exception_count",
    "exception_amount_cents",
)


def assert_cobol_binary():
    """Verify the batch still comes from the COBOL compile path."""
    compile_script = (APP / "scripts" / "compile.sh").read_text().lower()
    assert "cobc" in compile_script
    assert ".cbl" in compile_script
    assert any((APP / "src").glob("*.cbl"))
    assert (APP / "build" / "batch").read_bytes().startswith(b"\x7fELF")


def compile_program():
    """Compile the COBOL chargeback clearing program."""
    subprocess.run(["/app/scripts/compile.sh"], check=True, cwd=APP)
    assert_cobol_binary()


def write_inputs(sales, chargebacks):
    """Rewrite the fixed-width input files for a focused scenario."""
    SALES.write_text("\n".join(sales) + "\n")
    CHARGEBACKS.write_text("\n".join(chargebacks) + "\n")


def run_program():
    """Run the compiled program and return parsed report and summary outputs."""
    subprocess.run(["/app/build/batch"], check=True, cwd=APP)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {}
    lines = SUMMARY.read_text().splitlines()
    assert len(lines) == len(SUMMARY_FIELDS)
    for line in lines:
        assert line == line.strip()
        key, value = line.split("=", 1)
        assert value == value.strip()
        summary[key] = int(value)
    assert tuple(summary.keys()) == SUMMARY_FIELDS
    return rows, summary


class TestMilestone2:
    def test_mrc_chargeback_applies_and_counts_positive_amount(self):
        """MRC chargeback reasons should apply settled sales and add positive cents."""
        compile_program()
        write_inputs(
            ["SSAL202604101F100000012500MRCH1001S", "SSAL202604102MRC0000008800MRCH1002S"],
            ["CSAL2026041010000012500MRCH1001", "CSAL2026041020000008800MRCH1002"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["APPLIED", "APPLIED"]
        assert rows[1]["reason"] == "MRC"
        assert summary["applied_count"] == 2
        assert summary["applied_amount_cents"] == 21300
        assert summary["exception_count"] == 0

    def test_sale_id_match_uses_all_12_characters(self):
        """A chargeback must not apply a sale sharing only the leading id prefix."""
        compile_program()
        write_inputs(
            ["SSAL777770001F100000003300MRCH2001S", "SSAL777770002F100000003300MRCH2001S"],
            ["CSAL7777700030000003300MRCH2001", "CSAL7777700020000003300MRCH2001"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["EXCEPTION", "APPLIED"]
        assert summary["applied_count"] == 1
        assert summary["exception_count"] == 1

    def test_merchant_amount_status_and_reason_all_gate_applying(self):
        """Merchant id, amount, settled status, and allowed reason must all be satisfied."""
        compile_program()
        write_inputs(
            [
                "SSAL300000001F100000001000MRCH3001S",
                "SSAL300000002F200000002000MRCH3002S",
                "SSAL300000003R990000003000MRCH3003P",
                "SSAL300000004INT0000004000MRCH3004S",
                "SSAL300000005MRC0000005000MRCH3005S",
            ],
            [
                "CSAL3000000010000001000MRCH9999",
                "CSAL3000000020000002100MRCH3002",
                "CSAL3000000030000003000MRCH3003",
                "CSAL3000000040000004000MRCH3004",
                "CSAL3000000050000005000MRCH3005",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["EXCEPTION", "EXCEPTION", "EXCEPTION", "EXCEPTION", "APPLIED"]
        assert summary["applied_amount_cents"] == 5000
        assert summary["exception_count"] == 4

    def test_report_schema_order_and_zero_padded_amounts_are_stable(self):
        """The report schema, chargeback input order, and zero-padded amount text should stay stable."""
        compile_program()
        write_inputs(
            [
                "SSAL900000001F100000000100MRCH9001S",
                "SSAL900000002MRC0000000200MRCH9002S",
                "SSAL900000003R990000000300MRCH9003S",
            ],
            [
                "CSAL9000000030000000300MRCH9003",
                "CSAL9000000010000000100MRCH9001",
                "CSAL9000000020000000200MRCH9002",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "sale_id,merchant_id,reason,amount_cents,status"
        assert [row["sale_id"] for row in rows] == ["SAL900000003", "SAL900000001", "SAL900000002"]
        assert [row["merchant_id"] for row in rows] == ["MRCH9003", "MRCH9001", "MRCH9002"]
        assert [row["amount_cents"] for row in rows] == ["0000000300", "0000000100", "0000000200"]
        assert summary["applied_count"] == 3

    def test_duplicate_chargebacks_do_not_reuse_consumed_sale(self):
        """Only the earliest eligible chargeback may consume a matching settled sale."""
        compile_program()
        write_inputs(
            ["SSAL555500001MRC0000007200MRCH5551S", "SSAL555500002F200000004100MRCH5552S"],
            [
                "CSAL5555000010000007200MRCH5551",
                "CSAL5555000010000007200MRCH5551",
                "CSAL5555000020000004100MRCH5552",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["APPLIED", "EXCEPTION", "APPLIED"]
        assert summary["applied_count"] == 2
        assert summary["applied_amount_cents"] == 11300
        assert summary["exception_count"] == 1
        assert summary["exception_amount_cents"] == 7200

    def test_duplicate_sale_rows_are_consumed_by_row_position(self):
        """Two identical settled sale rows should be independently consumable before exceptions begin."""
        compile_program()
        write_inputs(
            [
                "SSAL565600001F100000006600MRCH5656S",
                "SSAL565600001F100000006600MRCH5656S",
            ],
            [
                "CSAL5656000010000006600MRCH5656",
                "CSAL5656000010000006600MRCH5656",
                "CSAL5656000010000006600MRCH5656",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["APPLIED", "APPLIED", "EXCEPTION"]
        assert [row["reason"] for row in rows] == ["F10", "F10", ""]
        assert summary["applied_count"] == 2
        assert summary["applied_amount_cents"] == 13200
        assert summary["exception_count"] == 1
        assert summary["exception_amount_cents"] == 6600
