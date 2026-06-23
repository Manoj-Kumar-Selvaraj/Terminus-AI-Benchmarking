"""Milestone 4 tests for merchant eligibility gating on card chargeback clearing."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SALES = APP / "data" / "sales.dat"
CHARGEBACKS = APP / "data" / "chargebacks.dat"
CALENDAR = APP / "config" / "cycle_calendar.txt"
MERCHANTS = APP / "config" / "merchants.csv"
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


def write_inputs(sales, chargebacks, calendar, merchants):
    """Rewrite inputs, calendar, and merchant config for a focused scenario."""
    SALES.write_text("\n".join(sales) + "\n")
    CHARGEBACKS.write_text("\n".join(chargebacks) + "\n")
    CALENDAR.write_text("\n".join(calendar) + "\n")
    MERCHANTS.write_text("merchant_id,chargeback_enabled\n" + "\n".join(merchants) + "\n")
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


def test_chargeback_enabled_true_required_after_prior_gates():
    """Only merchants listed with chargeback_enabled=true may apply chargebacks."""
    compile_program()
    write_inputs(
        [
            "SSAL410000001F100000001000MRCH4101S20260508",
            "SSAL410000002F100000002000MRCH4102S20260508",
            "SSAL410000003MRC0000003000MRCH4103S20260508",
        ],
        [
            "CSAL4100000010000001000MRCH410120260508",
            "CSAL4100000020000002000MRCH410220260508",
            "CSAL4100000030000003000MRCH410320260508",
        ],
        ["20260508 OPEN", "20260509 OPEN"],
        ["MRCH4101,true", "MRCH4102,false", "MRCH4103,true"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["APPLIED", "EXCEPTION", "APPLIED"]
    assert [row["reason"] for row in rows] == ["F10", "", "MRC"]
    assert summary["applied_count"] == 2
    assert summary["applied_amount_cents"] == 4000
    assert summary["exception_count"] == 1
    assert summary["exception_amount_cents"] == 2000


def test_missing_merchant_row_makes_sale_ineligible():
    """Sales for merchants absent from merchants.csv must not apply when cycle dates are eligible."""
    compile_program()
    write_inputs(
        ["SSAL420000001F100000000900MRCH4201S20260510"],
        ["CSAL4200000010000000900MRCH420120260510"],
        ["20260510 OPEN", "20260511 OPEN"],
        ["MRCH9999,true"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "EXCEPTION"
    assert rows[0]["reason"] == ""
    assert summary["applied_count"] == 0
    assert summary["exception_amount_cents"] == 900


def test_malformed_and_non_boolean_merchant_rows_do_not_enable():
    """Malformed merchant rows and non-true flags must not permit applying when cycle dates are eligible."""
    compile_program()
    write_inputs(
        ["SSAL430000001MRC0000000700MRCH4301S20260510"],
        ["CSAL4300000010000000700MRCH430120260510"],
        ["20260510 OPEN", "20260511 OPEN"],
        ["MRCH4301,yes", "BROKENROW", "MRCH9999,true"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "EXCEPTION"
    assert rows[0]["reason"] == ""
    assert summary["applied_count"] == 0
    assert summary["exception_amount_cents"] == 700


def test_merchant_gate_also_applies_in_undated_mode():
    """Undated chargebacks still require an enabled merchant row."""
    compile_program()
    write_inputs(
        ["SSAL440000001F100000000800MRCH4401S"],
        ["CSAL4400000010000000800MRCH4401"],
        ["20991231 CLOSED"],
        ["MRCH4401,false"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "EXCEPTION"
    assert rows[0]["reason"] == ""
    assert summary["applied_count"] == 0
    assert summary["exception_amount_cents"] == 800


def test_enabled_field_case_insensitive_and_whitespace_tolerant():
    """chargeback_enabled values must accept TRUE with leading or trailing whitespace."""
    compile_program()
    write_inputs(
        [
            "SSAL460000001F100000000500MRCH4601S20260508",
            "SSAL460000002F100000000600MRCH4602S20260508",
        ],
        [
            "CSAL4600000010000000500MRCH460120260508",
            "CSAL4600000020000000600MRCH460220260508",
        ],
        ["20260508 OPEN", "20260509 OPEN"],
        ["MRCH4601, TRUE ", "MRCH4602,true "],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["APPLIED", "APPLIED"]
    assert [row["reason"] for row in rows] == ["F10", "F10"]
    assert summary["applied_count"] == 2
    assert summary["applied_amount_cents"] == 1100


def test_merchant_gate_preserves_alias_calendar_and_consumption_rules():
    """Merchant gating must not regress alias normalization, cycle dates, or row consumption."""
    compile_program()
    write_inputs(
        [
            "SSAL470000001FRD0000001100MRCH4701S20260601",
            "SSAL470000001F100000001100MRCH4701S20260601",
            "SSAL470000002M200000002200MRCH4702S20260601",
        ],
        [
            "CSAL4700000010000001100MRCH470120260602",
            "CSAL4700000010000001100MRCH470120260602",
            "CSAL4700000020000002200MRCH470220260602",
        ],
        ["20260601 OPEN", "20260602 OPEN"],
        ["MRCH4701,true", "MRCH4702,true"],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["APPLIED", "APPLIED", "APPLIED"]
    assert [row["reason"] for row in rows] == ["F10", "F10", "F20"]
    assert summary["applied_count"] == 3
    assert summary["exception_count"] == 0
