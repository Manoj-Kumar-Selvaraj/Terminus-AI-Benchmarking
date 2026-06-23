"""Verifier tests for the COBOL lockbox payment applicator."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
SRC = APP / "src" / "lockbox_apply.cbl"
BIN = APP / "build" / "lockbox_apply"
INVOICES = APP / "data" / "invoices.dat"
PAYMENTS = APP / "data" / "payments.dat"
REPORT = APP / "out" / "lockbox_report.csv"
SUMMARY = APP / "out" / "lockbox_summary.txt"


def compile_program():
    """Compile the COBOL lockbox applicator before each scenario."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["cobc", "-x", "-free", "-O2", "-o", str(BIN), str(SRC)], check=True, cwd=APP, timeout=60)


def write_inputs(invoice_lines, payment_lines):
    """Write fixed-width invoice and payment files for a test scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    INVOICES.write_text("\n".join(invoice_lines) + "\n")
    PAYMENTS.write_text("\n".join(payment_lines) + "\n")
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



class TestMilestone1:
    """Milestone 1 verifier scenarios for lockbox payment application."""

    def test_lbx_payment_on_cutoff_date_applies_and_counts_positive_amount(self):
        """LBX payments on the invoice cutoff date should apply and count as positive cents."""
        compile_program()
        write_inputs(
            [
                "IINV202604101CUST10010000012500O20260430ACHN",
                "IINV202604102CUST10020000008450O20260430LBXN",
            ],
            [
                "PINV202604101CUST1001000001250020260430ACHP",
                "PINV202604102CUST1002000000845020260430LBXP",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["APPLIED", "APPLIED"]
        assert rows[1]["channel"] == "LBX"
        assert summary["applied_count"] == 2
        assert summary["applied_amount_cents"] == 20950
        assert summary["unapplied_count"] == 0


    def test_invoice_id_match_uses_all_12_characters(self):
        """A payment must not apply to an invoice sharing only the leading invoice prefix."""
        compile_program()
        write_inputs(
            [
                "IINV777770001CUST20010000003300O20260430ACHN",
                "IINV777770002CUST20010000003300O20260430ACHN",
            ],
            [
                "PINV777770003CUST2001000000330020260429ACHP",
                "PINV777770002CUST2001000000330020260429ACHP",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNAPPLIED", "APPLIED"]
        assert rows[0]["channel"] == ""
        assert summary["applied_count"] == 1
        assert summary["applied_amount_cents"] == 3300
        assert summary["unapplied_amount_cents"] == 3300


    def test_customer_amount_status_date_channel_hold_and_disposition_all_gate_application(self):
        """Customer, amount, open status, cutoff date, channel, hold flag, and payment disposition must all be satisfied."""
        compile_program()
        write_inputs(
            [
                "IINV300000001CUST30010000001000O20260430ACHN",
                "IINV300000002CUST30020000002000O20260430WIRN",
                "IINV300000003CUST30030000003000P20260430CRDN",
                "IINV300000004CUST30040000004000O20260430CHKN",
                "IINV300000005CUST30050000005000O20260430WIRN",
                "IINV300000006CUST30060000006000O20260430ACHH",
                "IINV300000007CUST30070000007000O20260430WIRN",
            ],
            [
                "PINV300000001CUST9999000000100020260429ACHP",
                "PINV300000002CUST3002000000210020260429WIRP",
                "PINV300000003CUST3003000000300020260429CRDP",
                "PINV300000004CUST3004000000400020260429CHKP",
                "PINV300000005CUST3005000000500020260501WIRP",
                "PINV300000006CUST3006000000600020260429ACHP",
                "PINV300000007CUST3007000000700020260429WIRR",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == [
            "UNAPPLIED",
            "UNAPPLIED",
            "UNAPPLIED",
            "UNAPPLIED",
            "UNAPPLIED",
            "UNAPPLIED",
            "UNAPPLIED",
        ]
        assert summary["applied_count"] == 0
        assert summary["unapplied_count"] == 7
        assert summary["unapplied_amount_cents"] == 28100


    def test_duplicate_payments_do_not_reuse_consumed_invoice(self):
        """Only the earliest eligible payment may consume a matching invoice."""
        compile_program()
        write_inputs(
            [
                "IINV555500001CUST55510000007200O20260430CRDN",
                "IINV555500002CUST55520000004100O20260430ACHN",
            ],
            [
                "PINV555500001CUST5551000000720020260429CRDP",
                "PINV555500001CUST5551000000720020260429CRDP",
                "PINV555500002CUST5552000000410020260429ACHP",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["APPLIED", "UNAPPLIED", "APPLIED"]
        assert rows[1]["channel"] == ""
        assert summary["applied_count"] == 2
        assert summary["applied_amount_cents"] == 11300
        assert summary["unapplied_count"] == 1
        assert summary["unapplied_amount_cents"] == 7200


    def test_report_schema_payment_order_and_zero_padded_amounts_are_stable(self):
        """The report should use the required schema, preserve input order, and keep zero-padded amounts."""
        compile_program()
        write_inputs(
            [
                "IINV900000001CUST90010000000100O20260501ACHN",
                "IINV900000002CUST90020000000200O20260501LBXN",
                "IINV900000003CUST90030000000300O20260501WIRN",
            ],
            [
                "PINV900000003CUST9003000000030020260430WIRP",
                "PINV900000001CUST9001000000010020260430ACHP",
                "PINV900000002CUST9002000000020020260430LBXP",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "invoice_id,customer_id,channel,amount_cents,payment_date,status"
        assert [row["invoice_id"] for row in rows] == ["INV900000003", "INV900000001", "INV900000002"]
        assert [row["customer_id"] for row in rows] == ["CUST9003", "CUST9001", "CUST9002"]
        assert [row["amount_cents"] for row in rows] == ["0000000300", "0000000100", "0000000200"]
        assert [row["payment_date"] for row in rows] == ["20260430", "20260430", "20260430"]
        assert summary["applied_count"] == 3
        assert summary["applied_amount_cents"] == 600
