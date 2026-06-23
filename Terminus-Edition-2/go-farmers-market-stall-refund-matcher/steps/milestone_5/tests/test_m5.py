"""Milestone 5 tests for market-day calendar controls."""

import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
GO = Path("/usr/local/go/bin/go")
BIN = APP / "build" / "reconcile"
STALLS = APP / "data" / "stalls.csv"
REFUNDS = APP / "data" / "refunds.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
POLICY = APP / "config" / "stall_policy.csv"
MARKET_CAL = APP / "config" / "market_calendar.txt"
REPORT = APP / "out" / "refund_report.csv"
SUMMARY = APP / "out" / "refund_summary.json"


def build_program():
    """Compile the Go reconciler."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


def write_csv(path, header, rows):
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(stalls, refunds, market_calendar, cutoff=None, policy=None):
    write_csv(
        STALLS,
        ["stall_id", "vendor_id", "amount_cents", "status", "stall_type", "market_date"],
        stalls,
    )
    write_csv(
        REFUNDS,
        ["settlement_id", "stall_id", "vendor_id", "amount_cents", "stall_type", "refund_date"],
        refunds,
    )
    write_csv(
        POLICY,
        ["stall_type", "enabled", "priority"],
        policy or [["PRODUCE", "Y", "2"], ["CRAFT", "Y", "1"], ["FOOD", "Y", "3"]],
    )
    CALENDAR.write_text("\n".join(cutoff or ["2026-04-01 open", "2026-04-02 open", "2026-04-03 open"]) + "\n")
    MARKET_CAL.write_text("\n".join(market_calendar) + "\n")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone5:
    def test_market_calendar_allows_two_open_days_but_blocks_three(self):
        """At most two open market days after the stall market_date are eligible."""
        build_program()
        write_inputs(
            [
                ["ST-CAL-1", "V-CAL-1", "10", "RESERVED", "PRODUCE", "2026-04-01"],
                ["ST-CAL-2", "V-CAL-2", "20", "RESERVED", "PRODUCE", "2026-04-01"],
            ],
            [
                ["RF-CAL-1", "ST-CAL-1", "V-CAL-1", "10", "PRODUCE", "2026-04-03"],
                ["RF-CAL-2", "ST-CAL-2", "V-CAL-2", "20", "PRODUCE", "2026-04-04"],
            ],
            [
                "2026-04-01 OPEN",
                "2026-04-02 OPEN",
                "2026-04-03 OPEN",
                "2026-04-04 OPEN",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 10,
            "unmatched_count": 1,
            "unmatched_amount_cents": 20,
        }

    def test_same_day_and_closed_or_absent_market_dates_reject(self):
        """Same-day refunds are eligible, but closed or unlisted market dates are not."""
        build_program()
        write_inputs(
            [
                ["ST-SAME", "V-SAME", "11", "RESERVED", "CRAFT", "2026-04-02"],
                ["ST-CLOSED", "V-CLOSED", "12", "RESERVED", "CRAFT", "2026-04-02"],
                ["ST-ABSENT", "V-ABSENT", "13", "RESERVED", "CRAFT", "2026-04-05"],
            ],
            [
                ["RF-SAME", "ST-SAME", "V-SAME", "11", "CRAFT", "2026-04-02"],
                ["RF-CLOSED", "ST-CLOSED", "V-CLOSED", "12", "CRAFT", "2026-04-04"],
                ["RF-ABSENT", "ST-ABSENT", "V-ABSENT", "13", "CRAFT", "2026-04-05"],
            ],
            [
                "2026-04-02 OPEN",
                "2026-04-03 OPEN",
                "2026-04-04 CLOSED",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED"]
        assert [row["stall_type"] for row in rows] == ["CRAFT", "", ""]
        assert summary["matched_amount_cents"] == 11
        assert summary["unmatched_amount_cents"] == 25

    def test_policy_any_and_row_consumption_still_apply_under_calendar_gate(self):
        """Calendar support must preserve policy-driven ANY selection and row consumption."""
        build_program()
        write_inputs(
            [
                ["ST-MIX", "V-MIX", "30", "RESERVED", "PRODUCE", "2026-04-01"],
                ["ST-MIX", "V-MIX", "30", "RESERVED", "CRAFT", "2026-04-01"],
            ],
            [
                ["RF-MIX-1", "ST-MIX", "V-MIX", "30", "ANY", "2026-04-02"],
                ["RF-MIX-2", "ST-MIX", "V-MIX", "30", "ANY", "2026-04-02"],
            ],
            ["2026-04-01 OPEN", "2026-04-02 OPEN"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["stall_type"] for row in rows] == ["CRAFT", "PRODUCE"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 60
