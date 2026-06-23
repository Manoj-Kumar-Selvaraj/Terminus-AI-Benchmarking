"""Milestone 4 tests for coldchain band policy and ANY releases."""

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


def write_inputs(source, action, windows, policy):
    write_csv(SOURCE, ["hold_id", "pallet_id", "zone_id", "temp_band", "amount", "hold_ts", "status", "bay"], source)
    write_csv(ACTION, ["release_id", "hold_id", "pallet_id", "zone_id", "temp_band", "amount", "release_ts", "reason", "bay"], action)
    write_csv(WINDOWS, ["zone_id", "open_ts", "close_ts", "state"], windows)
    write_csv(POLICY, ["temp_band", "enabled", "priority"], policy)
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


class TestMilestone4:
    def test_disabled_band_rejects_exact_and_any_matches(self):
        """Disabled canonical bands are ineligible for both exact and ANY releases."""
        build_program()
        write_inputs(
            [
                ["SRC-POL-1", "PAL-1", "Z-P", "AMBIENT", "10", "20260528100000", "QUARANTINED", "B1"],
                ["SRC-POL-2", "PAL-2", "Z-P", "AMBIENT", "20", "20260528100100", "QUARANTINED", "B2"],
            ],
            [
                ["REL-POL-1", "SRC-POL-1", "PAL-1", "Z-P", "SE", "10", "20260528101000", "OVERRIDE", "B1"],
                ["REL-POL-2", "SRC-POL-2", "PAL-2", "Z-P", "ANY", "20", "20260528101000", "OVERRIDE", "B2"],
            ],
            [["Z-P", "20260528090000", "20260528110000", "OPEN"]],
            [["FROZEN", "Y", "2"], ["CHILL", "Y", "1"], ["AMBIENT", "N", "3"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert [row["temp_band"] for row in rows] == ["", ""]
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 2, "unmatched_amount": 30}

    def test_policy_names_are_trimmed_and_case_folded(self):
        """Policy temp_band names should be trimmed and case-folded before enabled checks."""
        build_program()
        write_inputs(
            [
                ["SRC-POL-TRIM-1", "PAL-T1", "Z-P", "FROZEN", "31", "20260528100000", "QUARANTINED", "B1"],
                ["SRC-POL-TRIM-2", "PAL-T2", "Z-P", "CHILL", "32", "20260528100100", "QUARANTINED", "B2"],
            ],
            [
                ["REL-POL-TRIM-1", "SRC-POL-TRIM-1", "PAL-T1", "Z-P", "IN", "31", "20260528101000", "SPOIL", "B1"],
                ["REL-POL-TRIM-2", "SRC-POL-TRIM-2", "PAL-T2", "Z-P", "CU", "32", "20260528101000", "QUAR", "B2"],
            ],
            [["Z-P", "20260528090000", "20260528110000", "OPEN"]],
            [[" frozen ", "Y", "2"], ["chill", "Y", "1"], ["AMBIENT", "N", "3"]],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["temp_band"] for row in rows] == ["FROZEN", "CHILL"]
        assert summary == {"matched_count": 2, "matched_amount": 63, "unmatched_count": 0, "unmatched_amount": 0}

    def test_any_uses_latest_timestamp_then_priority_then_row_order(self):
        """ANY releases choose latest hold_ts, then lower policy priority, then earliest row."""
        build_program()
        write_inputs(
            [
                ["SRC-ANY", "PAL-9", "Z-A", "FROZEN", "50", "20260528100000", "QUARANTINED", "B9"],
                ["SRC-ANY", "PAL-9", "Z-A", "CHILL", "50", "20260528100500", "QUARANTINED", "B9"],
                ["SRC-ANY", "PAL-9", "Z-A", "FROZEN", "50", "20260528100500", "QUARANTINED", "B9"],
                ["SRC-ANY", "PAL-9", "Z-A", "CHILL", "50", "20260528100500", "QUARANTINED", "B9"],
            ],
            [
                ["REL-ANY-1", "SRC-ANY", "PAL-9", "Z-A", "ANY", "50", "20260528101000", "SPOIL", "B9"],
                ["REL-ANY-2", "SRC-ANY", "PAL-9", "Z-A", "ANY", "50", "20260528101100", "SPOIL", "B9"],
            ],
            [["Z-A", "20260528090000", "20260528110000", "OPEN"]],
            [["FROZEN", "Y", "2"], ["CHILL", "Y", "1"], ["AMBIENT", "Y", "3"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["temp_band"] for row in rows] == ["CHILL", "CHILL"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount"] == 100

    def test_any_same_band_tie_consumes_duplicate_rows_in_order(self):
        """ANY releases with tied CHILL candidates consume duplicate rows before the third release."""
        build_program()
        write_inputs(
            [
                ["SRC-CHILL-TIE", "PAL-C", "Z-C", "CHILL", "41", "20260528100500", "QUARANTINED", "B1"],
                ["SRC-CHILL-TIE", "PAL-C", "Z-C", "CHILL", "41", "20260528100500", "QUARANTINED", "B1"],
            ],
            [
                ["REL-CHILL-TIE-1", "SRC-CHILL-TIE", "PAL-C", "Z-C", "ANY", "41", "20260528101000", "SPOIL", "B1"],
                ["REL-CHILL-TIE-2", "SRC-CHILL-TIE", "PAL-C", "Z-C", "ANY", "41", "20260528101100", "SPOIL", "B1"],
                ["REL-CHILL-TIE-3", "SRC-CHILL-TIE", "PAL-C", "Z-C", "ANY", "41", "20260528101200", "SPOIL", "B1"],
            ],
            [["Z-C", "20260528090000", "20260528110000", "OPEN"]],
            [["FROZEN", "Y", "2"], ["CHILL", "Y", "1"], ["AMBIENT", "Y", "3"]],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["temp_band"] for row in rows] == ["CHILL", "CHILL", ""]
        assert summary == {"matched_count": 2, "matched_amount": 82, "unmatched_count": 1, "unmatched_amount": 41}

    def test_non_any_still_requires_exact_canonical_band(self):
        """Policy support must not make concrete release bands behave like ANY."""
        build_program()
        write_inputs(
            [["SRC-EXACT", "PAL-X", "Z-E", "CHILL", "70", "20260528100000", "QUARANTINED", "B1"]],
            [["REL-EXACT", "SRC-EXACT", "PAL-X", "Z-E", "FROZEN", "70", "20260528101000", "SPOIL", "B1"]],
            [["Z-E", "20260528090000", "20260528110000", "OPEN"]],
            [["FROZEN", "Y", "2"], ["CHILL", "Y", "1"], ["AMBIENT", "Y", "3"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["temp_band"] == ""
        assert summary["unmatched_amount"] == 70

    def test_any_skips_disabled_band_even_with_latest_timestamp(self):
        """ANY must not select a disabled band when an enabled band has an earlier hold_ts."""
        build_program()
        write_inputs(
            [
                ["SRC-POL-A", "PAL-A", "Z-P", "AMBIENT", "40", "20260528102000", "QUARANTINED", "B1"],
                ["SRC-POL-A", "PAL-A", "Z-P", "CHILL", "40", "20260528101000", "QUARANTINED", "B1"],
            ],
            [["REL-POL-A", "SRC-POL-A", "PAL-A", "Z-P", "ANY", "40", "20260528103000", "SPOIL", "B1"]],
            [["Z-P", "20260528090000", "20260528110000", "OPEN"]],
            [["FROZEN", "Y", "2"], ["CHILL", "Y", "1"], ["AMBIENT", "N", "3"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["temp_band"] == "CHILL"
        assert summary["matched_amount"] == 40
