"""Tests for the property lease deposit reconciliation CLI."""

# Milestone 2 intentionally repeats milestone 1 gate tests as regression
# coverage, then adds alias-specific scenarios below.

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
LEASES = APP / "data" / "leases.csv"
PAYMENTS = APP / "data" / "deposits.csv"
REPORT = APP / "out" / "deposit_report.csv"
SUMMARY = APP / "out" / "deposit_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go reconciliation CLI for the current source tree."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 2 tests."""
    build_program()


def write_inputs(lease_rows, deposit_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    LEASES.write_text("lease_id,customer_id,amount_cents,status,channel\n" + "\n".join(lease_rows) + "\n")
    PAYMENTS.write_text("lease_id,customer_id,amount_cents,channel\n" + "\n".join(deposit_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())



class TestMilestone2:
    def test_card_deposit_matches_and_counts_positive_amount(self):
        """CARD deposits should match posted leases and add positive cents to matched totals."""
        write_inputs(
            [
                "LEAS20260401001,CUST1001,12500,POSTED,ACH",
                "LEAS20260401002,CUST1002,9900,POSTED,CARD",
            ],
            [
                "LEAS20260401001,CUST1001,12500,ACH",
                "LEAS20260401002,CUST1002,9900,CARD",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert rows[1]["channel"] == "CARD"
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 22400
        assert summary["unmatched_count"] == 0


    def test_lease_id_match_uses_full_identifier(self):
        """A deposit must not match a lease that only shares the leading lease prefix."""
        write_inputs(
            [
                "LEAS777770001,CUST2001,3300,POSTED,ACH",
                "LEAS777770002,CUST2001,3300,POSTED,ACH",
            ],
            [
                "LEAS777770003,CUST2001,3300,ACH",
                "LEAS777770002,CUST2001,3300,ACH",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert rows[0]["channel"] == ""
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 3300
        assert summary["unmatched_amount_cents"] == 3300


    def test_customer_amount_status_and_channel_all_gate_matching(self):
        """Customer, amount, posted status, and allowed channel must all be satisfied."""
        write_inputs(
            [
                "LEAS3001,CUST3001,1000,POSTED,ACH",
                "LEAS3002,CUST3002,2000,POSTED,CARD",
                "LEAS3003,CUST3003,3000,DRAFT,WIRE",
                "LEAS3004,CUST3004,4000,POSTED,CHECK",
                "LEAS3005,CUST3005,5000,POSTED,WIRE",
            ],
            [
                "LEAS3001,CUST9999,1000,ACH",
                "LEAS3002,CUST3002,2100,CARD",
                "LEAS3003,CUST3003,3000,WIRE",
                "LEAS3004,CUST3004,4000,CHECK",
                "LEAS3005,CUST3005,5000,WIRE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
        assert rows[-1]["channel"] == "WIRE"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 5000
        assert summary["unmatched_count"] == 4
        assert summary["unmatched_amount_cents"] == 10100


    def test_channel_must_match_even_when_both_channels_are_allowed(self):
        """A deposit with an allowed channel must not match a lease with a different allowed channel."""
        write_inputs(
            ["LEAS3401,CUST3401,2400,POSTED,ACH"],
            ["LEAS3401,CUST3401,2400,CARD"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 2400


    def test_duplicate_deposits_do_not_reuse_consumed_lease(self):
        """Only the earliest eligible deposit may consume a matching lease."""
        write_inputs(
            [
                "LEAS5551,CUST5551,7500,POSTED,CARD",
                "LEAS5552,CUST5552,8800,POSTED,ACH",
            ],
            [
                "LEAS5551,CUST5551,7500,CARD",
                "LEAS5551,CUST5551,7500,CARD",
                "LEAS5552,CUST5552,8800,ACH",
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
        """Matching should tolerate surrounding spaces and case differences in channel/status values."""
        write_inputs(
            [
                " LEAS6601 , CUST6601 , 6100 , posted , card ",
                "LEAS6602,CUST6602,7200,POSTED,wire",
            ],
            [
                "LEAS6601,CUST6601, 6100 ,CARD",
                " LEAS6602 , CUST6602 ,7200, WIRE ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["lease_id"] for row in rows] == ["LEAS6601", "LEAS6602"]
        assert [row["customer_id"] for row in rows] == ["CUST6601", "CUST6602"]
        assert [row["channel"] for row in rows] == ["CARD", "WIRE"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 13300


    def test_legacy_channel_aliases_match_and_emit_canonical_channels(self):
        """Legacy CC and WIR deposit channels should match as CARD and WIRE and report canonical channels."""
        write_inputs(
            [
                "LEAS7701,CUST7701,8800,POSTED,CARD",
                "LEAS7702,CUST7702,9100,posted,wire",
                "LEAS7703,CUST7703,4200,POSTED,ACH",
                "LEAS7704,CUST7704,3300,POSTED,CHECK",
            ],
            [
                "LEAS7701,CUST7701,8800,cc",
                "LEAS7702,CUST7702,9100,WIR",
                "LEAS7703,CUST7703,4200,ach",
                "LEAS7704,CUST7704,3300,chk",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["channel"] for row in rows] == ["CARD", "WIRE", "ACH", ""]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 22100
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 3300

    def test_lease_aliases_and_surrounding_whitespace_are_normalized(self):
        """Lease-side aliases and aliases surrounded by whitespace should match canonical channels."""
        write_inputs(
            [
                "LEAS7751,CUST7751,5100,POSTED, cc ",
                "LEAS7752,CUST7752,6200,POSTED, WIR ",
            ],
            [
                "LEAS7751,CUST7751,5100, CARD ",
                "LEAS7752,CUST7752,6200, wir ",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["channel"] for row in rows] == ["CARD", "WIRE"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 11300,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }


    def test_report_schema_and_deposit_input_order_are_stable(self):
        """The report should use the required schema and preserve deposit input order."""
        write_inputs(
            [
                "LEAS9001,CUST9001,100,POSTED,ACH",
                "LEAS9002,CUST9002,200,POSTED,CARD",
                "LEAS9003,CUST9003,300,POSTED,WIRE",
            ],
            [
                "LEAS9003,CUST9003,300,WIRE",
                "LEAS9001,CUST9001,100,ACH",
                "LEAS9002,CUST9002,200,CARD",
            ],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "lease_id,customer_id,channel,amount_cents,status"
        assert [row["lease_id"] for row in rows] == ["LEAS9003", "LEAS9001", "LEAS9002"]
        assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
