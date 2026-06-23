"""Milestone 3 verifier tests for dated fleet vehicle rebate matching CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
VEHS = APP / "data" / "vehicles.csv"
REBATES = APP / "data" / "rebates.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "rebate_report.csv"
SUMMARY = APP / "out" / "rebate_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go rebate reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 3 tests."""
    build_program()


def write_inputs(vehicle_rows, rebate_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated rebate scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    VEHS.write_text("vehicle_id,customer_id,amount_cents,status,channel,due_date\n" + "\n".join(vehicle_rows) + "\n")
    REBATES.write_text("vehicle_id,customer_id,amount_cents,channel,rebate_date\n" + "\n".join(rebate_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse its CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone3:
    """Date gates and latest eligible vehicle selection for rebates."""

    def test_open_rebate_date_and_latest_due_date_win(self):
        """Open rebate dates should gate matching and latest eligible due date should win."""
        write_inputs(
            [
                "VEH9301,CUST9301,1000,POSTED,ACH,2026-04-03",
                "VEH9301,CUST9301,1000,POSTED,CARD,2026-04-04",
                "VEH9302,CUST9302,2000,POSTED,CARD,2026-04-02",
                "VEH9303,CUST9303,3000,POSTED,WIRE,2026-04-05",
                "VEH9304,CUST9304,4000,POSTED,WIRE,2026-04-05",
            ],
            [
                "VEH9301,CUST9301,1000,CC,2026-04-02",
                "VEH9302,CUST9302,2000,CC,2026-04-04",
                "VEH9303,CUST9303,3000,WIR,2026-04-06",
                "VEH9304,CUST9304,4000,WIRE,2026-04-07",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
                "2026-04-05 open",
                "2026-04-06 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert rows[0]["channel"] == "CARD"
        assert [row["channel"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_due_date_tie_uses_vehicle_order_and_consumption(self):
        """Same-date candidates should use vehicle order and still enforce consumption."""
        write_inputs(
            [
                "VEH9401,CUST9401,500,POSTED,CARD,2026-04-05",
                "VEH9401,CUST9401,500,POSTED,CARD,2026-04-05",
                "VEH9402,CUST9402,700,POSTED,ACH,2026-04-05",
            ],
            [
                "VEH9401,CUST9401,500,CC,2026-04-04",
                "VEH9401,CUST9401,500,CC,2026-04-04",
                "VEH9401,CUST9401,500,CC,2026-04-04",
                "VEH9402,CUST9402,700,ACH,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["channel"] for row in rows] == ["CARD", "CARD", "", "ACH"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_due_date_wins_before_older_vehicle_is_used(self):
        """A later eligible due date should be consumed before an older eligible vehicle."""
        write_inputs(
            [
                "VEH9501,CUST9501,800,POSTED,CARD,2026-04-03",
                "VEH9501,CUST9501,800,POSTED,CARD,2026-04-06",
            ],
            [
                "VEH9501,CUST9501,800,CC,2026-04-02",
                "VEH9501,CUST9501,800,CC,2026-04-04",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["channel"] for row in rows] == ["CARD", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_closed_rebate_date_is_not_eligible(self):
        """A rebate whose date is listed as closed must not match."""
        write_inputs(
            ["VEH9601,CUST9601,1000,POSTED,CARD,2026-04-10"],
            ["VEH9601,CUST9601,1000,CC,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 1000

    def test_unlisted_rebate_date_is_not_eligible(self):
        """A rebate date absent from the calendar must not be treated as open."""
        write_inputs(
            ["VEH9651,CUST9651,500,POSTED,CARD,2026-04-30"],
            ["VEH9651,CUST9651,500,CC,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 1,
            "unmatched_amount_cents": 500,
        }

    def test_missing_rebate_date_is_not_eligible(self):
        """A rebate with an empty rebate_date must not match any vehicle."""
        write_inputs(
            ["VEH9701,CUST9701,900,POSTED,ACH,2026-04-05"],
            ["VEH9701,CUST9701,900,ACH,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 900

    def test_vehicle_without_due_date_is_not_eligible(self):
        """A vehicle with an empty due_date cannot be consumed."""
        write_inputs(
            ["VEH9801,CUST9801,700,POSTED,WIRE,"],
            ["VEH9801,CUST9801,700,WIR,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 700

    def test_wir_alias_matches_wire_vehicle_and_emits_canonical_channel(self):
        """A WIR rebate should match a WIRE vehicle and report the canonical channel."""
        write_inputs(
            ["VEH9901,CUST9901,600,POSTED,WIRE,2026-04-10"],
            ["VEH9901,CUST9901,600,WIR,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["channel"] == "WIRE"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
