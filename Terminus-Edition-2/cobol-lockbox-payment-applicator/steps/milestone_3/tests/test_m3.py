"""Milestone 3 tests for lockbox payment calendar controls."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
SRC = APP / "src" / "lockbox_apply.cbl"
BIN = APP / "build" / "lockbox_apply"
INVOICES = APP / "data" / "invoices.dat"
PAYMENTS = APP / "data" / "payments.dat"
CALENDAR = APP / "config" / "payment_calendar.txt"
REPORT = APP / "out" / "lockbox_report.csv"
SUMMARY = APP / "out" / "lockbox_summary.txt"


def compile_program():
    """Compile the COBOL lockbox applicator before each scenario."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cobc", "-x", "-free", "-O2", "-o", str(BIN), str(SRC)], check=True, cwd=APP, timeout=60)


def write_inputs(invoice_lines, payment_lines, calendar_lines):
    """Write fixed-width invoice/payment files and the payment calendar."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    INVOICES.write_text("\n".join(invoice_lines) + "\n")
    PAYMENTS.write_text("\n".join(payment_lines) + "\n")
    CALENDAR.write_text("\n".join(calendar_lines) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled applicator and return parsed report and summary data."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        summary[key] = int(value)
    return rows, summary


class TestMilestone3:
    """Verify calendar-open dates and latest eligible invoice cutoff selection."""

    def test_calendar_open_dates_gate_alias_payments_and_latest_cutoff_wins(self):
        """Only open dates should apply, and the latest eligible invoice cutoff should win."""
        compile_program()
        write_inputs(
            [
                "IINV930000001CUST93010000001000O20260429LBXN",
                "IINV930000001CUST93010000001000O20260430LBXN",
                "IINV930000002CUST93020000002000O20260430ACHN",
                "IINV930000003CUST93030000003000O20260501CRDN",
                "IINV930000004CUST93040000004000O20260502WIRN",
            ],
            [
                "PINV930000001CUST9301000000100020260429LKBP",
                "PINV930000002CUST9302000000200020260501BNKP",
                "PINV930000003CUST9303000000300020260430CCPP",
                "PINV930000004CUST9304000000400020260430WIRP",
                "PINV930000001CUST9301000000100020260430LKBP",
            ],
            [
                "20260429 OPEN",
                "20260430 OPEN",
                "20260501 CLOSED",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["APPLIED", "UNAPPLIED", "UNAPPLIED", "UNAPPLIED", "UNAPPLIED"]
        assert [row["channel"] for row in rows] == ["LBX", "", "", "", ""]
        assert [row["payment_date"] for row in rows] == ["20260429", "20260501", "20260430", "20260430", "20260430"]
        assert summary["applied_count"] == 1
        assert summary["applied_amount_cents"] == 1000
        assert summary["unapplied_count"] == 4
        assert summary["unapplied_amount_cents"] == 10000

    def test_same_cutoff_alias_payments_consume_each_invoice_once(self):
        """Same-cutoff alias payments should consume each channel-matched invoice once."""
        compile_program()
        write_inputs(
            [
                "IINV940000001CUST94010000000500O20260430CRDN",
                "IINV940000001CUST94010000000500O20260430ACHN",
                "IINV940000002CUST94020000000700O20260430ACHN",
            ],
            [
                "PINV940000001CUST9401000000050020260429CCPP",
                "PINV940000001CUST9401000000050020260429BNKP",
                "PINV940000001CUST9401000000050020260429CCPP",
                "PINV940000002CUST9402000000070020260430BNKP",
            ],
            [
                "20260429 OPEN",
                "20260430 OPEN",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["APPLIED", "APPLIED", "UNAPPLIED", "APPLIED"]
        assert [row["channel"] for row in rows] == ["CRD", "ACH", "", "ACH"]
        assert summary["applied_count"] == 3
        assert summary["applied_amount_cents"] == 1700
        assert summary["unapplied_count"] == 1
        assert summary["unapplied_amount_cents"] == 500

    def test_payment_date_absent_from_calendar_is_not_open(self):
        """A missing payment date must remain unapplied even when the cutoff date is open."""
        compile_program()
        write_inputs(
            [
                "IINV950000001CUST95010000001000O20260502ACHN",
            ],
            [
                "PINV950000001CUST9501000000100020260501ACHP",
            ],
            [
                "20260430 OPEN",
                "20260502 OPEN",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNAPPLIED"
        assert rows[0]["channel"] == ""
        assert rows[0]["payment_date"] == "20260501"
        assert summary["applied_count"] == 0
        assert summary["applied_amount_cents"] == 0
        assert summary["unapplied_count"] == 1
        assert summary["unapplied_amount_cents"] == 1000

    def test_closed_payment_date_is_not_open_even_when_cutoff_is_open(self):
        """A CLOSED payment date must not apply when every non-calendar gate passes."""
        compile_program()
        write_inputs(
            [
                "IINV960000001CUST96010000001500O20260430ACHN",
            ],
            [
                "PINV960000001CUST9601000000150020260429BNKP",
            ],
            [
                "20260429 CLOSED",
                "20260430 OPEN",
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNAPPLIED"
        assert rows[0]["channel"] == ""
        assert rows[0]["payment_date"] == "20260429"
        assert summary["applied_count"] == 0
        assert summary["applied_amount_cents"] == 0
        assert summary["unapplied_count"] == 1
        assert summary["unapplied_amount_cents"] == 1500
