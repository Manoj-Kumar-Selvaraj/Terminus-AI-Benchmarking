"""Milestone 4 tests for stall policy and ANY refunds."""

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


def write_inputs(stalls, refunds, policy, calendar=None):
    write_csv(STALLS, ["stall_id", "vendor_id", "amount_cents", "status", "stall_type"], stalls)
    write_csv(REFUNDS, ["settlement_id", "stall_id", "vendor_id", "amount_cents", "stall_type"], refunds)
    write_csv(POLICY, ["stall_type", "enabled", "priority"], policy)
    CALENDAR.write_text("\n".join(calendar or ["2026-04-01 open"]) + "\n")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone4:
    def test_disabled_stall_type_rejects_exact_and_any_matches(self):
        """Disabled canonical stall types are ineligible for both exact and ANY refunds."""
        build_program()
        write_inputs(
            [
                ["ST-POL-1", "V-POL-1", "10", "RESERVED", "FOOD"],
                ["ST-POL-2", "V-POL-2", "20", "RESERVED", "FOOD"],
            ],
            [
                ["RF-POL-1", "ST-POL-1", "V-POL-1", "10", "FOOD"],
                ["RF-POL-2", "ST-POL-2", "V-POL-2", "20", "ANY"],
            ],
            [["PRODUCE", "Y", "2"], ["CRAFT", "Y", "1"], ["FOOD", "N", "3"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert [row["stall_type"] for row in rows] == ["", ""]
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 2,
            "unmatched_amount_cents": 30,
        }

    def test_any_uses_priority_then_row_order_when_undated(self):
        """ANY refunds choose lower policy priority, then earliest stall row when undated."""
        build_program()
        write_inputs(
            [
                ["ST-ANY", "V-ANY", "50", "RESERVED", "PRODUCE"],
                ["ST-ANY", "V-ANY", "50", "RESERVED", "CRAFT"],
                ["ST-ANY", "V-ANY", "50", "RESERVED", "PRODUCE"],
                ["ST-ANY", "V-ANY", "50", "RESERVED", "CRAFT"],
            ],
            [
                ["RF-ANY-1", "ST-ANY", "V-ANY", "50", "ANY"],
                ["RF-ANY-2", "ST-ANY", "V-ANY", "50", "ANY"],
            ],
            [["PRODUCE", "Y", "2"], ["CRAFT", "Y", "1"], ["FOOD", "Y", "3"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["stall_type"] for row in rows] == ["CRAFT", "CRAFT"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 100

    def test_non_any_still_requires_exact_canonical_stall_type(self):
        """Policy support must not make concrete refund stall types behave like ANY."""
        build_program()
        write_inputs(
            [["ST-EXACT", "V-EXACT", "70", "RESERVED", "CRAFT"]],
            [["RF-EXACT", "ST-EXACT", "V-EXACT", "70", "PRODUCE"]],
            [["PRODUCE", "Y", "2"], ["CRAFT", "Y", "1"], ["FOOD", "Y", "3"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["stall_type"] == ""
        assert summary["unmatched_amount_cents"] == 70

    def test_any_skips_disabled_type_even_with_better_priority(self):
        """ANY must not select a disabled stall type when an enabled type is available."""
        build_program()
        write_inputs(
            [
                ["ST-POL-A", "V-POL-A", "40", "RESERVED", "FOOD"],
                ["ST-POL-A", "V-POL-A", "40", "RESERVED", "CRAFT"],
            ],
            [["RF-POL-A", "ST-POL-A", "V-POL-A", "40", "ANY"]],
            [["PRODUCE", "Y", "2"], ["CRAFT", "Y", "1"], ["FOOD", "N", "3"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["stall_type"] == "CRAFT"
        assert summary["matched_amount_cents"] == 40
