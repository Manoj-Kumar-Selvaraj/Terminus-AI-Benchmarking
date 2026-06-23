"""Milestone 3 tests for legacy card chargeback aliases and cycle controls."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SALES = APP / "data" / "sales.dat"
CHARGEBACKS = APP / "data" / "chargebacks.dat"
CALENDAR = APP / "config" / "cycle_calendar.txt"
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


def write_inputs(sales, chargebacks, calendar):
    """Rewrite fixed-width inputs and the cycle calendar for a focused scenario."""
    SALES.write_text("\n".join(sales) + "\n")
    CHARGEBACKS.write_text("\n".join(chargebacks) + "\n")
    CALENDAR.write_text("\n".join(calendar) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


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


def test_mrc_chargeback_applies_and_counts_positive_amount():
    """MRC chargebacks should still apply on legacy undated records with positive totals."""
    compile_program()
    write_inputs(
        ["SSAL202604101F100000012500MRCH1001S", "SSAL202604102MRC0000008800MRCH1002S"],
        ["CSAL2026041010000012500MRCH1001", "CSAL2026041020000008800MRCH1002"],
        ["20991231 CLOSED"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["APPLIED", "APPLIED"]
    assert rows[1]["reason"] == "MRC"
    assert summary["applied_count"] == 2
    assert summary["applied_amount_cents"] == 21300
    assert summary["exception_count"] == 0


def test_sale_id_match_uses_all_12_characters():
    """A chargeback must not apply a sale sharing only the leading id prefix."""
    compile_program()
    write_inputs(
        ["SSAL777770001F100000003300MRCH2001S", "SSAL777770002F100000003300MRCH2001S"],
        ["CSAL7777700030000003300MRCH2001", "CSAL7777700020000003300MRCH2001"],
        ["20991231 CLOSED"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["EXCEPTION", "APPLIED"]
    assert summary["applied_count"] == 1
    assert summary["exception_count"] == 1


def test_merchant_amount_status_and_reason_all_gate_applying():
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
        ["20991231 CLOSED"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["EXCEPTION", "EXCEPTION", "EXCEPTION", "EXCEPTION", "APPLIED"]
    assert summary["applied_amount_cents"] == 5000
    assert summary["exception_count"] == 4


def test_duplicate_chargebacks_do_not_reuse_consumed_sale():
    """Only the first eligible chargeback may consume a matching settled sale row."""
    compile_program()
    write_inputs(
        ["SSAL555500001MRC0000007200MRCH5551S", "SSAL555500002F200000004100MRCH5552S"],
        [
            "CSAL5555000010000007200MRCH5551",
            "CSAL5555000010000007200MRCH5551",
            "CSAL5555000020000004100MRCH5552",
        ],
        ["20991231 CLOSED"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["APPLIED", "EXCEPTION", "APPLIED"]
    assert summary["applied_count"] == 2
    assert summary["applied_amount_cents"] == 11300
    assert summary["exception_count"] == 1


def test_duplicate_sale_rows_are_consumed_by_row_position():
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
        ["20991231 CLOSED"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["APPLIED", "APPLIED", "EXCEPTION"]
    assert [row["reason"] for row in rows] == ["F10", "F10", ""]
    assert summary["applied_count"] == 2
    assert summary["applied_amount_cents"] == 13200
    assert summary["exception_count"] == 1


def test_report_schema_order_and_zero_padded_amounts_are_stable():
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
        ["20991231 CLOSED"],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "sale_id,merchant_id,reason,amount_cents,status"
    assert [row["sale_id"] for row in rows] == ["SAL900000003", "SAL900000001", "SAL900000002"]
    assert [row["merchant_id"] for row in rows] == ["MRCH9003", "MRCH9001", "MRCH9002"]
    assert [row["amount_cents"] for row in rows] == ["0000000300", "0000000100", "0000000200"]
    assert [row["reason"] for row in rows] == ["R99", "F10", "MRC"]
    assert summary["applied_count"] == 3


class TestMilestone3:
    """Legacy aliases, cycle-date eligibility, and latest-row selection."""

    def test_alias_reasons_emit_canonical_and_latest_settlement_date_wins(self):
        """Aliases should normalize, and repeated chargebacks should consume newest eligible sales first."""
        compile_program()
        write_inputs(
            [
                "SSAL950000001F100000001000MRCH9501S20260429",
                "SSAL950000001FRD0000001000MRCH9501S20260430",
                "SSAL950000001MER0000001000MRCH9501S20260501",
                "SSAL950000002M200000002000MRCH9502S20260501",
                "SSAL950000003UNK0000003000MRCH9503S20260501",
            ],
            [
                "CSAL9500000010000001000MRCH950120260501",
                "CSAL9500000010000001000MRCH950120260501",
                "CSAL9500000010000001000MRCH950120260501",
                "CSAL9500000020000002000MRCH950220260501",
                "CSAL9500000030000003000MRCH950320260501",
            ],
            [
                "20260429 OPEN",
                "20260430 OPEN",
                "20260501 OPEN",
                "20260502 OPEN",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["APPLIED", "APPLIED", "APPLIED", "APPLIED", "EXCEPTION"]
        assert [row["reason"] for row in rows] == ["MRC", "F10", "F10", "F20", ""]
        assert [row["merchant_id"] for row in rows] == ["MRCH9501", "MRCH9501", "MRCH9501", "MRCH9502", "MRCH9503"]
        assert [row["amount_cents"] for row in rows] == [
            "0000001000",
            "0000001000",
            "0000001000",
            "0000002000",
            "0000003000",
        ]
        assert summary["applied_count"] == 4
        assert summary["applied_amount_cents"] == 5000
        assert summary["exception_count"] == 1
        assert summary["exception_amount_cents"] == 3000

    def test_closed_absent_blank_and_too_late_dates_are_ineligible(self):
        """Closed, absent, blank, reversed, and over-window dates should reject otherwise valid rows."""
        compile_program()
        write_inputs(
            [
                "SSAL960000001F100000001000MRCH9601S20260502",
                "SSAL960000002F100000002000MRCH9602S20260501",
                "SSAL960000003F100000003000MRCH9603S20260501",
                "SSAL960000004MRC0000004000MRCH9604S20260504",
                "SSAL960000005F200000005000MRCH9605S20260506",
                "SSAL960000006MRC0000006000MRCH9606S20260503",
            ],
            [
                "CSAL9600000010000001000MRCH960120260503",
                "CSAL9600000020000002000MRCH960220260502",
                "CSAL9600000030000003000MRCH960320260506",
                "CSAL9600000040000004000MRCH960420260503",
                "CSAL9600000050000005000MRCH960520260507",
                "CSAL9600000060000006000MRCH960620260504",
            ],
            [
                "20260501 OPEN",
                "20260502 CLOSED",
                "20260503 OPEN",
                "20260504 OPEN",
                "20260505 CLOSED",
                "20260506 OPEN",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == [
            "EXCEPTION",
            "EXCEPTION",
            "EXCEPTION",
            "EXCEPTION",
            "EXCEPTION",
            "APPLIED",
        ]
        assert [row["reason"] for row in rows] == ["", "", "", "", "", "MRC"]
        assert summary["applied_count"] == 1
        assert summary["applied_amount_cents"] == 6000
        assert summary["exception_count"] == 5
        assert summary["exception_amount_cents"] == 15000

    def test_open_day_count_ignores_closed_calendar_days_in_window(self):
        """Cycle gating must count OPEN days only, not raw calendar span."""
        compile_program()
        write_inputs(
            ["SSAL100000001F100000001000MRCH0001S20260501"],
            ["CSAL1000000010000001000MRCH000120260504"],
            [
                "20260501 OPEN",
                "20260502 CLOSED",
                "20260503 CLOSED",
                "20260504 OPEN",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "APPLIED"
        assert rows[0]["reason"] == "F10"
        assert summary["applied_count"] == 1
        assert summary["exception_count"] == 0

    def test_same_settlement_date_tie_uses_latest_sale_input_row_and_consumption(self):
        """When settlement dates tie, latest sale input row wins and consumed rows are skipped."""
        compile_program()
        write_inputs(
            [
                "SSAL970000001F100000001100MRCH9701S20260601",
                "SSAL970000001MER0000001100MRCH9701S20260601",
                "SSAL970000001M200000001100MRCH9701S20260601",
            ],
            [
                "CSAL9700000010000001100MRCH970120260602",
                "CSAL9700000010000001100MRCH970120260602",
                "CSAL9700000010000001100MRCH970120260602",
            ],
            [
                "20260601 OPEN",
                "20260602 OPEN",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["APPLIED", "APPLIED", "APPLIED"]
        assert [row["reason"] for row in rows] == ["F20", "MRC", "F10"]
        assert summary["applied_count"] == 3
        assert summary["applied_amount_cents"] == 3300
        assert summary["exception_count"] == 0

    def test_prior_matching_gates_still_apply_with_cycle_dates(self):
        """Merchant, amount, status, reason, and blank-date gates should still block matches."""
        compile_program()
        write_inputs(
            [
                "SSAL980000001F100000001000MRCH9801S20260701",
                "SSAL980000002F100000002000MRCH9802P20260701",
                "SSAL980000003F100000003100MRCH9803S20260701",
                "SSAL980000004MRC0000004000MRCH9804S        ",
                "SSAL980000005F200000005000MRCH9805S20260701",
            ],
            [
                "CSAL9800000010000001000MRCH999920260702",
                "CSAL9800000020000002000MRCH980220260702",
                "CSAL9800000030000003000MRCH980320260702",
                "CSAL9800000040000004000MRCH980420260702",
                "CSAL9800000050000005000MRCH9805        ",
            ],
            [
                "20260701 OPEN",
                "20260702 OPEN",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["EXCEPTION", "EXCEPTION", "EXCEPTION", "EXCEPTION", "EXCEPTION"]
        assert [row["reason"] for row in rows] == ["", "", "", "", ""]
        assert summary["applied_count"] == 0
        assert summary["exception_count"] == 5
        assert summary["exception_amount_cents"] == 15000

    def test_latest_settlement_date_wins_before_older_sale_row_is_used(self):
        """Older settlement rows listed first must lose to later dates, not first-in-file order."""
        compile_program()
        write_inputs(
            [
                "SSAL990000001MRC0000001000MRCH9901S20260429",
                "SSAL990000001F100000001000MRCH9901S20260501",
                "SSAL990000001M200000001000MRCH9901S20260502",
            ],
            [
                "CSAL9900000010000001000MRCH990120260501",
                "CSAL9900000010000001000MRCH990120260501",
                "CSAL9900000010000001000MRCH990120260503",
            ],
            [
                "20260429 OPEN",
                "20260430 OPEN",
                "20260501 OPEN",
                "20260502 OPEN",
                "20260503 OPEN",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["APPLIED", "APPLIED", "APPLIED"]
        assert [row["reason"] for row in rows] == ["F10", "MRC", "F20"]
        assert summary["applied_count"] == 3
        assert summary["exception_count"] == 0

    def test_undated_records_skip_cycle_gating(self):
        """Legacy records without chargeback dates must ignore a closed calendar."""
        compile_program()
        write_inputs(
            [
                "SSAL202604101F100000012500MRCH1001S",
                "SSAL202604102FRD0000008800MRCH1002S",
            ],
            ["CSAL2026041010000012500MRCH1001", "CSAL2026041020000008800MRCH1002"],
            ["20991231 CLOSED"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["APPLIED", "APPLIED"]
        assert [row["reason"] for row in rows] == ["F10", "F10"]
        assert summary["applied_count"] == 2
        assert summary["applied_amount_cents"] == 21300

    def test_chargeback_date_equal_to_settlement_date_is_eligible(self):
        """Settlement and chargeback on the same open day should still apply."""
        compile_program()
        write_inputs(
            ["SSAL991000001F100000001000MRCH9910S20260510"],
            ["CSAL9910000010000001000MRCH991020260510"],
            ["20260510 OPEN"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "APPLIED"
        assert rows[0]["reason"] == "F10"
        assert summary["applied_count"] == 1
