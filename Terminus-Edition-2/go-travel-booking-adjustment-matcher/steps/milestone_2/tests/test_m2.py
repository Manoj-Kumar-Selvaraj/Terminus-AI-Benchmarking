"""Milestone 2 verifier tests for channel alias normalization."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
BOOKINGS = APP / "data" / "bookings.csv"
PAYMENTS = APP / "data" / "adjustments.csv"
REPORT = APP / "out" / "adjustment_report.csv"
SUMMARY = APP / "out" / "adjustment_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    build_program()


def write_inputs(booking_rows, adjustment_rows):
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    BOOKINGS.write_text("booking_id,customer_id,amount_cents,status,channel\n" + "\n".join(booking_rows) + "\n")
    PAYMENTS.write_text("booking_id,customer_id,amount_cents,channel\n" + "\n".join(adjustment_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone2:
    """Legacy channel aliases and prior matching gates."""

    def test_card_adjustment_matches_and_counts_positive_amount(self):
        write_inputs(
            [
                "BOOK20260401001,CUST1001,12500,POSTED,ACH",
                "BOOK20260401002,CUST1002,9900,POSTED,CARD",
            ],
            [
                "BOOK20260401001,CUST1001,12500,ACH",
                "BOOK20260401002,CUST1002,9900,CARD",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["channel"] == "CARD"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 22400
        assert summary["unmatched_count"] == 0

    def test_booking_id_match_uses_full_identifier(self):
        write_inputs(
            [
                "BOOK777770001,CUST2001,3300,POSTED,ACH",
                "BOOK777770002,CUST2001,3300,POSTED,ACH",
            ],
            [
                "BOOK777770003,CUST2001,3300,ACH",
                "BOOK777770002,CUST2001,3300,ACH",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["channel"] == ""
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300

    def test_customer_amount_status_and_channel_all_gate_matching(self):
        write_inputs(
            [
                "BOOK3001,CUST3001,1000,POSTED,ACH",
                "BOOK3002,CUST3002,2000,POSTED,CARD",
                "BOOK3003,CUST3003,3000,DRAFT,WIRE",
                "BOOK3004,CUST3004,4000,POSTED,CHECK",
                "BOOK3005,CUST3005,5000,POSTED,WIRE",
            ],
            [
                "BOOK3001,CUST9999,1000,ACH",
                "BOOK3002,CUST3002,2100,CARD",
                "BOOK3003,CUST3003,3000,WIRE",
                "BOOK3004,CUST3004,4000,CHECK",
                "BOOK3005,CUST3005,5000,WIRE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["channel"] == "WIRE"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_count"] == 4
        assert summary["unmatched_amount_cents"] == 10100

    def test_duplicate_adjustments_do_not_reuse_consumed_booking(self):
        write_inputs(
            [
                "BOOK5551,CUST5551,7500,POSTED,CARD",
                "BOOK5552,CUST5552,8800,POSTED,ACH",
            ],
            [
                "BOOK5551,CUST5551,7500,CARD",
                "BOOK5551,CUST5551,7500,CARD",
                "BOOK5552,CUST5552,8800,ACH",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert rows[1]["channel"] == ""
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 16300
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 7500

    def test_matching_trims_fields_and_normalizes_channel_status_case(self):
        write_inputs(
            [
                " BOOK6601 , CUST6601 , 6100 , posted , card ",
                "BOOK6602,CUST6602,7200,POSTED,wire",
            ],
            [
                "BOOK6601,CUST6601, 6100 ,CARD",
                " BOOK6602 , CUST6602 ,7200, WIRE ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["booking_id"] for row in rows] == ["BOOK6601", "BOOK6602"]
        assert [row["customer_id"] for row in rows] == ["CUST6601", "CUST6602"]
        assert [row["channel"] for row in rows] == ["CARD", "WIRE"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 13300

    def test_legacy_channel_aliases_match_and_emit_canonical_channels(self):
        write_inputs(
            [
                "BOOK7701,CUST7701,8800,POSTED,CARD",
                "BOOK7702,CUST7702,9100,posted,wire",
                "BOOK7703,CUST7703,4200,POSTED,ACH",
                "BOOK7704,CUST7704,3300,POSTED,CHECK",
            ],
            [
                "BOOK7701,CUST7701,8800,cc",
                "BOOK7702,CUST7702,9100,WIR",
                "BOOK7703,CUST7703,4200,ach",
                "BOOK7704,CUST7704,3300,chk",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["channel"] for row in rows] == ["CARD", "WIRE", "ACH", ""]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 22100
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 3300

    def test_report_schema_and_adjustment_input_order_are_stable(self):
        write_inputs(
            [
                "BOOK9001,CUST9001,100,POSTED,ACH",
                "BOOK9002,CUST9002,200,POSTED,CARD",
                "BOOK9003,CUST9003,300,POSTED,WIRE",
            ],
            [
                "BOOK9003,CUST9003,300,WIRE",
                "BOOK9001,CUST9001,100,ACH",
                "BOOK9002,CUST9002,200,CARD",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "booking_id,customer_id,channel,amount_cents,status"
        assert [row["booking_id"] for row in rows] == ["BOOK9003", "BOOK9001", "BOOK9002"]
        assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
