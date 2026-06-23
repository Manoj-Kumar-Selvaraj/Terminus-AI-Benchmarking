"""Milestone 2 tests for legacy lockbox channel aliases."""

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



class TestMilestone2:
    """Milestone 2 verifier scenarios for legacy lockbox aliases."""

    def test_legacy_payment_channel_aliases_apply_as_canonical_channels(self):
        """LKB, BNK, and CCP payment aliases should match LBX, ACH, and CRD invoices."""
        compile_program()
        write_inputs(
            [
                "IINV810000001CUST81010000001500O20260430LBXN",
                "IINV810000002CUST81020000002500O20260430ACHN",
                "IINV810000003CUST81030000003500O20260430CRDN",
                "IINV810000004CUST81040000004500O20260430WIRN",
                "IINV810000005CUST81050000005500O20260429ACHN",
                "IINV810000006CUST81060000006500O20260429ACHN",
            ],
            [
                "PINV810000001CUST8101000000150020260429LKBP",
                "PINV810000002CUST8102000000250020260429BNKP",
                "PINV810000003CUST8103000000350020260429CCPP",
                "PINV810000004CUST8104000000450020260429WIRP",
                "PINV810000005CUST8105000000550020260429BNKP",
                "PINV810000006CUST8106000000650020260429BNKP",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == [
            "APPLIED",
            "APPLIED",
            "APPLIED",
            "APPLIED",
            "APPLIED",
            "APPLIED",
        ]
        assert [row["channel"] for row in rows] == ["LBX", "ACH", "CRD", "WIR", "ACH", "ACH"]
        assert [row["amount_cents"] for row in rows] == [
            "0000001500",
            "0000002500",
            "0000003500",
            "0000004500",
            "0000005500",
            "0000006500",
        ]
        assert summary["applied_count"] == 6
        assert summary["applied_amount_cents"] == 24000
        assert summary["unapplied_count"] == 0


    def test_unknown_alias_stays_unapplied_and_duplicate_alias_does_not_reuse_invoice(self):
        """Unknown aliases should not apply, and duplicate alias payments may not reuse an invoice."""
        compile_program()
        write_inputs(
            [
                "IINV820000001CUST82010000006000O20260430LBXN",
                "IINV820000002CUST82020000007000O20260430ACHN",
            ],
            [
                "PINV820000001CUST8201000000600020260429LKBP",
                "PINV820000001CUST8201000000600020260429LKBP",
                "PINV820000002CUST8202000000700020260429ZZZP",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "invoice_id,customer_id,channel,amount_cents,payment_date,status"
        assert [row["invoice_id"] for row in rows] == ["INV820000001", "INV820000001", "INV820000002"]
        assert [row["status"] for row in rows] == ["APPLIED", "UNAPPLIED", "UNAPPLIED"]
        assert [row["channel"] for row in rows] == ["LBX", "", ""]
        assert summary["applied_count"] == 1
        assert summary["applied_amount_cents"] == 6000
        assert summary["unapplied_count"] == 2
        assert summary["unapplied_amount_cents"] == 13000


    def test_alias_matching_still_enforces_id_status_hold_and_disposition_gates(self):
        """Alias payments must still obey full invoice id, status, hold, disposition, date, customer, and amount gates."""
        compile_program()
        write_inputs(
            [
                "IINV830000011CUST83010000001111O20260430LBXN",
                "IINV840000001CUST84010000005000O20260430LBXY",
                "IINV850000001CUST85010000002000O20260430LBXN",
                "IINV860000001CUST86010000003000C20260430LBXN",
                "IINV870000001CUST87010000004000O20260428LBXN",
                "IINV880000001CUST88010000004500O20260430LBXN",
                "IINV890000001CUST89010000005500O20260430LBXN",
            ],
            [
                "PINV830000012CUST8301000000111120260429LKBP",
                "PINV840000001CUST8401000000500020260429LKBP",
                "PINV850000001CUST8501000000200020260429LKBR",
                "PINV860000001CUST8601000000300020260429LKBP",
                "PINV870000001CUST8701000000400020260429LKBP",
                "PINV880000001CUST8899000000450020260429LKBP",
                "PINV890000001CUST8901000000650020260429LKBP",
            ],
        )
        rows, summary = run_program()

        assert [row["invoice_id"] for row in rows] == [
            "INV830000012",
            "INV840000001",
            "INV850000001",
            "INV860000001",
            "INV870000001",
            "INV880000001",
            "INV890000001",
        ]
        assert [row["customer_id"] for row in rows] == [
            "CUST8301",
            "CUST8401",
            "CUST8501",
            "CUST8601",
            "CUST8701",
            "CUST8899",
            "CUST8901",
        ]
        assert [row["status"] for row in rows] == [
            "UNAPPLIED",
            "UNAPPLIED",
            "UNAPPLIED",
            "UNAPPLIED",
            "UNAPPLIED",
            "UNAPPLIED",
            "UNAPPLIED",
        ]
        assert [row["channel"] for row in rows] == ["", "", "", "", "", "", ""]
        assert [row["payment_date"] for row in rows] == [
            "20260429",
            "20260429",
            "20260429",
            "20260429",
            "20260429",
            "20260429",
            "20260429",
        ]
        assert summary["applied_count"] == 0
        assert summary["applied_amount_cents"] == 0
        assert summary["unapplied_count"] == 7
        assert summary["unapplied_amount_cents"] == 26111
