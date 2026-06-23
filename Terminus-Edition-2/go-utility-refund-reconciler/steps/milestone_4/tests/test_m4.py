"""Milestone 4 verifier tests for channel-method gated bill refund reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
BILLS = APP / "data" / "bills.csv"
REFUNDS = APP / "data" / "refunds.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
METHODS = APP / "config" / "methods.csv"
REPORT = APP / "out" / "refund_report.csv"
SUMMARY = APP / "out" / "refund_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go refund reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 4 tests."""
    build_program()


def write_inputs(
    bill_rows,
    refund_rows,
    calendar_rows,
    method_rows,
    bill_header="bill_id,customer_id,amount_cents,status,channel,due_date",
    refund_header="bill_id,customer_id,amount_cents,channel,refund_date",
):
    """Replace CSV inputs, calendar, and method config with one verifier scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    BILLS.write_text(bill_header + "\n" + "\n".join(bill_rows) + "\n")
    REFUNDS.write_text(refund_header + "\n" + "\n".join(refund_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    METHODS.write_text("channel,enabled\n" + "\n".join(method_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse its CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone4:
    """Method configuration gates matching after all earlier refund rules pass."""

    def test_methods_gate_blocks_disabled_wire_and_allows_alias_enabled_card(self):
        """Enabled method aliases should allow matching, while disabled methods reject otherwise valid refunds."""
        write_inputs(
            [
                "BILLM401,CUSTM401,1000,POSTED,CARD,2026-05-10",
                "BILLM402,CUSTM402,2000,POSTED,WIRE,2026-05-10",
                "BILLM403,CUSTM403,3000,POSTED,ACH,2026-05-10",
            ],
            [
                "BILLM401,CUSTM401,1000,CC,2026-05-05",
                "BILLM402,CUSTM402,2000,WIR,2026-05-05",
                "BILLM403,CUSTM403,3000,ach,2026-05-05",
            ],
            ["2026-05-05 open"],
            [
                " cc , TRUE",
                "WIRE,false",
                "ACH,true",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["channel"] for row in rows] == ["CARD", "", "ACH"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 4000,
            "unmatched_count": 1,
            "unmatched_amount_cents": 2000,
        }

    def test_missing_and_malformed_methods_do_not_enable_channel(self):
        """Missing, blank, malformed, and non-true method rows should leave channels ineligible."""
        write_inputs(
            [
                "BILLM411,CUSTM411,1100,POSTED,CARD,2026-05-12",
                "BILLM412,CUSTM412,1200,POSTED,WIRE,2026-05-12",
                "BILLM413,CUSTM413,1300,POSTED,ACH,2026-05-12",
            ],
            [
                "BILLM411,CUSTM411,1100,CARD,2026-05-06",
                "BILLM412,CUSTM412,1200,WIR,2026-05-06",
                "BILLM413,CUSTM413,1300,ACH,2026-05-06",
            ],
            ["2026-05-06 open"],
            [
                "CARD,maybe",
                "WIRE",
                ",true",
                "ACH,TRUE",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "MATCHED"]
        assert [row["channel"] for row in rows] == ["", "", "ACH"]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1300,
            "unmatched_count": 2,
            "unmatched_amount_cents": 2300,
        }

    def test_wire_alias_in_methods_config_enables_wire_refund(self):
        """The WIR alias should normalize to WIRE when it appears in methods.csv."""
        write_inputs(
            ["BILLM416,CUSTM416,1600,POSTED,WIRE,2026-05-12"],
            ["BILLM416,CUSTM416,1600,WIR,2026-05-06"],
            ["2026-05-06 open"],
            ["wir,true"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["channel"] == "WIRE"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_methods_gate_preserves_latest_due_date_selection_and_consumption(self):
        """Enabled methods should not weaken latest-date selection or single-use bill consumption."""
        write_inputs(
            [
                "BILLM421,CUSTM421,1400,POSTED,CARD,2026-05-08",
                "BILLM421,CUSTM421,1400,POSTED,CARD,2026-05-14",
                "BILLM421,CUSTM421,1400,POSTED,CARD,2026-05-14",
            ],
            [
                "BILLM421,CUSTM421,1400,CC,2026-05-07",
                "BILLM421,CUSTM421,1400,CC,2026-05-07",
                "BILLM421,CUSTM421,1400,CC,2026-05-07",
                "BILLM421,CUSTM421,1400,CC,2026-05-07",
            ],
            ["2026-05-07 open"],
            ["CARD,true"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["channel"] for row in rows] == ["CARD", "CARD", "CARD", ""]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 4200,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1400,
        }

    def test_enabled_method_does_not_bypass_closed_calendar_date(self):
        """A method-enabled channel must still fail when the refund date is not open."""
        write_inputs(
            ["BILLM431,CUSTM431,1500,POSTED,CARD,2026-05-15"],
            ["BILLM431,CUSTM431,1500,CC,2026-05-09"],
            ["2026-05-09 closed"],
            ["CARD,true"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1500,
        }

    def test_omitted_date_columns_use_methods_gated_undated_matching(self):
        """Without due_date/refund_date columns, milestone 4 should still apply method gating with alias-aware undated matching."""
        write_inputs(
            [
                "BILLM441,CUSTM441,610,POSTED,CARD",
                "BILLM442,CUSTM442,620,POSTED,WIRE",
                "BILLM443,CUSTM443,630,POSTED,ACH",
            ],
            [
                "BILLM441,CUSTM441,610,CC",
                "BILLM442,CUSTM442,620,WIR",
                "BILLM443,CUSTM443,630,ACH",
            ],
            ["2026-05-09 closed"],
            [
                "CARD,true",
                "WIRE,true",
                "ACH,false",
            ],
            bill_header="bill_id,customer_id,amount_cents,status,channel",
            refund_header="bill_id,customer_id,amount_cents,channel",
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["channel"] for row in rows] == ["CARD", "WIRE", ""]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1230,
            "unmatched_count": 1,
            "unmatched_amount_cents": 630,
        }
