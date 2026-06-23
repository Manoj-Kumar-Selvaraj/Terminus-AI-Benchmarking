"""Milestone 3 verifier tests for dated pharmacy reversal matching."""

import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
FILLS = APP / "data" / "fills.csv"
REVERSALS = APP / "data" / "reversals.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "reversal_report.csv"
SUMMARY = APP / "out" / "reversal_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go reversal reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


def write_inputs(fill_rows, reversal_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated reversal scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    FILLS.write_text("fill_id,member_id,amount_cents,status,reason,service_date\n" + "\n".join(fill_rows) + "\n")
    REVERSALS.write_text("fill_id,member_id,amount_cents,reason,reversal_date\n" + "\n".join(reversal_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_raw_inputs(fill_header, fill_rows, reversal_header, reversal_rows, calendar_rows):
    """Replace inputs with explicit headers for missing-column compatibility scenarios."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    FILLS.write_text(fill_header + "\n" + "\n".join(fill_rows) + "\n")
    REVERSALS.write_text(reversal_header + "\n" + "\n".join(reversal_rows) + "\n")
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
    """Date gates and latest eligible fill selection for reversals."""

    def test_open_reversal_date_and_latest_service_date_win(self):
        """Open reversal dates should gate matching and latest eligible service date should win."""
        build_program()
        write_inputs(
            [
                "FILL9301,MEM9301,1000,POSTED,RX,2026-04-01",
                "FILL9301,MEM9301,1000,POSTED,COPAY,2026-04-03",
                "FILL9302,MEM9302,2000,POSTED,COB,2026-04-05",
                "FILL9303,MEM9303,3000,POSTED,RX,2026-04-04",
                "FILL9304,MEM9304,4000,POSTED,COB,2026-04-05",
            ],
            [
                "FILL9301,MEM9301,1000,BEN,2026-04-04",
                "FILL9302,MEM9302,2000,CPY,2026-04-04",
                "FILL9303,MEM9303,3000,RX,2026-04-05",
                "FILL9304,MEM9304,4000,CPY,2026-04-07",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 closed",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert rows[0]["reason"] == "COPAY"
        assert [row["reason"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_service_date_tie_uses_fill_order_and_consumption(self):
        """Same-date candidates should use fill order and still enforce consumption."""
        build_program()
        write_inputs(
            [
                "FILL9401,MEM9401,500,POSTED,COPAY,2026-04-05",
                "FILL9401,MEM9401,500,POSTED,COPAY,2026-04-05",
                "FILL9402,MEM9402,700,POSTED,RX,2026-04-05",
            ],
            [
                "FILL9401,MEM9401,500,BEN,2026-04-06",
                "FILL9401,MEM9401,500,BEN,2026-04-06",
                "FILL9401,MEM9401,500,BEN,2026-04-06",
                "FILL9402,MEM9402,700,RX,2026-04-06",
            ],
            [
                "2026-04-06 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["reason"] for row in rows] == ["COPAY", "COPAY", "", "RX"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_service_date_wins_before_older_fill_is_used(self):
        """A later eligible service date should be consumed before an older eligible fill."""
        build_program()
        write_inputs(
            [
                "FILL9501,MEM9501,800,POSTED,RX,2026-04-01",
                "FILL9501,MEM9501,800,POSTED,RX,2026-04-03",
            ],
            [
                "FILL9501,MEM9501,800,RX,2026-04-04",
                "FILL9501,MEM9501,800,RX,2026-04-02",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["reason"] for row in rows] == ["RX", "RX"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_service_date_equal_to_reversal_date_is_eligible(self):
        """A fill whose service date equals the reversal date should still match."""
        build_program()
        write_inputs(
            ["FILL9601,MEM9601,300,POSTED,RX,2026-04-06"],
            ["FILL9601,MEM9601,300,RX,2026-04-06"],
            ["2026-04-06 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["reason"] == "RX"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 300

    def test_missing_and_absent_reversal_dates_are_unmatched_but_readable(self):
        """Missing date values or older no-date CSV shapes should not crash and should not match."""
        build_program()
        write_raw_inputs(
            "fill_id,member_id,amount_cents,status,reason,service_date",
            [
                "FILL9701,MEM9701,400,POSTED,RX,2026-04-06",
                "FILL9702,MEM9702,500,POSTED,COPAY,2026-04-06",
            ],
            "fill_id,member_id,amount_cents,reason,reversal_date",
            [
                "FILL9701,MEM9701,400,RX,",
                "FILL9702,MEM9702,500,BEN,2026-04-07",
            ],
            [
                "2026-04-06 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert [row["reason"] for row in rows] == ["", ""]
        assert summary["unmatched_count"] == 2
        assert summary["unmatched_amount_cents"] == 900

        write_raw_inputs(
            "fill_id,member_id,amount_cents,status,reason",
            ["FILL9703,MEM9703,600,POSTED,RX"],
            "fill_id,member_id,amount_cents,reason",
            ["FILL9703,MEM9703,600,RX"],
            ["2026-04-06 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["reason"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 600
