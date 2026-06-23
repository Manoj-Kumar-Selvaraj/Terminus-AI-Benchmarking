"""Milestone 5 tests for coldchain open-day release calendar controls."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
GO = Path("/usr/local/go/bin/go")
BIN = APP / "build" / "reconcile"
SOURCE = APP / "data" / "holds.csv"
ACTION = APP / "data" / "releases.csv"
WINDOWS = APP / "config" / "windows.csv"
POLICY = APP / "config" / "band_policy.csv"
CALENDAR = APP / "config" / "release_calendar.txt"
REPORT = APP / "out" / "pallet_release_report.csv"
SUMMARY = APP / "out" / "pallet_release_summary.txt"


def build_program():
    """Compile the Go reconciler."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile/main.go"], check=True, cwd=APP, timeout=60)


def write_csv(path, header, rows):
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(source, action, calendar, windows=None, policy=None):
    write_csv(SOURCE, ["hold_id", "pallet_id", "zone_id", "temp_band", "amount", "hold_ts", "status", "bay"], source)
    write_csv(ACTION, ["release_id", "hold_id", "pallet_id", "zone_id", "temp_band", "amount", "release_ts", "reason", "bay"], action)
    write_csv(WINDOWS, ["zone_id", "open_ts", "close_ts", "state"], windows or [["Z-C", "20260528000000", "20260605235959", "OPEN"]])
    write_csv(POLICY, ["temp_band", "enabled", "priority"], policy or [["FROZEN", "Y", "2"], ["CHILL", "Y", "1"], ["AMBIENT", "Y", "3"]])
    CALENDAR.write_text("\n".join(calendar) + "\n")
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        summary[key] = int(value)
    return rows, summary


class TestMilestone5:
    def test_calendar_open_day_window_allows_two_but_blocks_three(self):
        """At most two open release days after hold date are eligible."""
        build_program()
        write_inputs(
            [
                ["SRC-CAL-1", "PAL-1", "Z-C", "FROZEN", "10", "20260528100000", "QUARANTINED", "B1"],
                ["SRC-CAL-2", "PAL-2", "Z-C", "FROZEN", "20", "20260528100000", "QUARANTINED", "B2"],
            ],
            [
                ["REL-CAL-1", "SRC-CAL-1", "PAL-1", "Z-C", "FROZEN", "10", "20260531100000", "SPOIL", "B1"],
                ["REL-CAL-2", "SRC-CAL-2", "PAL-2", "Z-C", "FROZEN", "20", "20260601100000", "SPOIL", "B2"],
            ],
            ["20260528 open", "20260529 Open", "20260530 CLOSED", "20260531 oPeN", "20260601 OPEN"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 1, "unmatched_amount": 20}

    def test_same_day_counts_zero_and_closed_or_absent_dates_reject(self):
        """Same-day releases are eligible, but closed or unlisted dates are not."""
        build_program()
        write_inputs(
            [
                ["SRC-SAME", "PAL-1", "Z-C", "CHILL", "11", "20260528100000", "QUARANTINED", "B1"],
                ["SRC-CLOSED", "PAL-2", "Z-C", "CHILL", "12", "20260529100000", "QUARANTINED", "B2"],
                ["SRC-ABSENT", "PAL-3", "Z-C", "CHILL", "13", "20260602100000", "QUARANTINED", "B3"],
            ],
            [
                ["REL-SAME", "SRC-SAME", "PAL-1", "Z-C", "CHILL", "11", "20260528101000", "QUAR", "B1"],
                ["REL-CLOSED", "SRC-CLOSED", "PAL-2", "Z-C", "CHILL", "12", "20260530101000", "QUAR", "B2"],
                ["REL-ABSENT", "SRC-ABSENT", "PAL-3", "Z-C", "CHILL", "13", "20260602101000", "QUAR", "B3"],
            ],
            ["20260528 open", "20260529 Open", "20260530 CLOSED"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED"]
        assert [row["temp_band"] for row in rows] == ["CHILL", "", ""]
        assert summary["matched_amount"] == 11
        assert summary["unmatched_amount"] == 25

    def test_policy_any_and_row_consumption_still_apply_under_calendar_gate(self):
        """Calendar support must preserve policy-driven ANY selection and row consumption."""
        build_program()
        write_inputs(
            [
                ["SRC-MIX", "PAL-9", "Z-C", "FROZEN", "30", "20260528100000", "QUARANTINED", "B9"],
                ["SRC-MIX", "PAL-9", "Z-C", "CHILL", "30", "20260528100000", "QUARANTINED", "B9"],
            ],
            [
                ["REL-MIX-1", "SRC-MIX", "PAL-9", "Z-C", "ANY", "30", "20260529100000", "OVERRIDE", "B9"],
                ["REL-MIX-2", "SRC-MIX", "PAL-9", "Z-C", "ANY", "30", "20260529100500", "OVERRIDE", "B9"],
                ["REL-MIX-3", "SRC-MIX", "PAL-9", "Z-C", "ANY", "30", "20260529101000", "OVERRIDE", "B9"],
            ],
            ["20260528 OPEN", "20260529 OPEN"],
            policy=[["FROZEN", "Y", "2"], ["CHILL", "Y", "1"], ["AMBIENT", "Y", "3"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["temp_band"] for row in rows] == ["CHILL", "FROZEN", ""]
        assert summary["matched_count"] == 2

    def test_hold_date_must_be_open_release_day(self):
        """Both hold and release calendar dates must be explicitly OPEN."""
        build_program()
        write_inputs(
            [["SRC-HOLD-D", "PAL-H", "Z-C", "FROZEN", "14", "20260530100000", "QUARANTINED", "B1"]],
            [["REL-HOLD-D", "SRC-HOLD-D", "PAL-H", "Z-C", "FROZEN", "14", "20260531100000", "SPOIL", "B1"]],
            ["20260528 OPEN", "20260529 OPEN", "20260531 OPEN"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert summary["unmatched_amount"] == 14

    def test_malformed_calendar_dates_are_ignored(self):
        """Malformed calendar date tokens should be ignored while valid OPEN dates still apply."""
        build_program()
        write_inputs(
            [
                ["SRC-CAL-GOOD", "PAL-G", "Z-C", "FROZEN", "15", "20260528100000", "QUARANTINED", "B1"],
                ["SRC-CAL-BAD", "PAL-B", "Z-C", "FROZEN", "16", "20260529100000", "QUARANTINED", "B2"],
            ],
            [
                ["REL-CAL-GOOD", "SRC-CAL-GOOD", "PAL-G", "Z-C", "FROZEN", "15", "20260529100000", "SPOIL", "B1"],
                ["REL-CAL-BAD", "SRC-CAL-BAD", "PAL-B", "Z-C", "FROZEN", "16", "20260530100000", "SPOIL", "B2"],
            ],
            ["20260528 OPEN", "20260529 OPEN", "2026052X OPEN", "202605301 OPEN"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["temp_band"] for row in rows] == ["FROZEN", ""]
        assert summary == {"matched_count": 1, "matched_amount": 15, "unmatched_count": 1, "unmatched_amount": 16}
