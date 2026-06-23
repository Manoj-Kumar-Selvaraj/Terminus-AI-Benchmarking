"""Verifier tests for realtime datacenter rack hold release reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
GO = Path("/usr/local/go/bin/go")
BIN = APP / "build" / "reconcile"
SOURCE = APP / "data" / "holds.csv"
ACTION = APP / "data" / "releases.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "rack_release_report.csv"
SUMMARY = APP / "out" / "rack_release_summary.txt"


def build_program():
    """Prepare the reconciler for one verifier scenario."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile/main.go"], check=True, cwd=APP, timeout=60)


def write_csv(path, header, rows):
    """Write one CSV fixture."""
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(source, action, windows):
    """Overwrite all input files at runtime."""
    write_csv(SOURCE, ["hold_id", "asset_id", "aisle_id", "access_tier", "amount", "hold_ts", "status", "rack"], source)
    write_csv(ACTION, ["release_id", "hold_id", "asset_id", "aisle_id", "access_tier", "amount", "release_ts", "reason", "rack"], action)
    write_csv(WINDOWS, ["aisle_id", "open_ts", "close_ts", "state"], windows)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the reconciler and parse outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        summary[key] = int(value)
    return rows, summary


def test_all_gates_consumption_and_positive_unmatched_totals():
    """Exercises multiple gates together: identity, status/reason, 14-digit timestamps, and consumption."""
    build_program()
    write_inputs(
        [
            ["SRC-GATE-1", "PARTY-1", "S-G", "HOT", "10", "20260528140000", "LOCKED", "L1"],
            ["SRC-GATE-2", "PARTY-2", "S-G", "HOT", "20", "20260528140100", "BAD", "L2"],
            ["SRC-GATE-3", "PARTY-3", "S-G", "WARM", "30", "20260528140200", "LOCKED", "L3"],
            ["SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140300", "LOCKED", "L4"],
        ],
        [
            ["ACT-A", "SRC-GATE-1", "PARTY-1", "S-G", "HOT", "10", "20260528140500", "DECOMM", "L1"],
            ["ACT-B", "SRC-GATE-1", "PARTY-1", "S-G", "HOT", "10", "20260528140600", "DECOMM", "L1"],
            ["ACT-C", "SRC-GATE-2", "PARTY-2", "S-G", "HOT", "20", "20260528140700", "DECOMM", "L2"],
            ["ACT-D", "SRC-GATE-3", "PARTY-X", "S-G", "WARM", "30", "20260528140700", "MIGRATE", "L3"],
            ["ACT-E", "SRC-GATE-3", "PARTY-3", "S-G", "WARM", "31", "20260528140700", "MIGRATE", "L3"],
            ["ACT-F", "SRC-GATE-3", "PARTY-3", "S-G", "WARM", "30", "20260528135959", "MIGRATE", "L3"],
            ["ACT-G", "SRC-GATE-3", "PARTY-3", "S-G", "WARM", "30", "20260528140700", "INFO", "L3"],
            ["ACT-H", "SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140700", "OVERRIDE", "L4"],
        ],
        [["S-G", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert rows[1]["access_tier"] == ""
    assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 7, "unmatched_amount": 191}


def test_source_status_is_required():
    """A source hold with any status other than LOCKED must not match."""
    build_program()
    write_inputs(
        [["SRC-STATUS", "BOX-1", "G-1", "HOT", "25", "20260528100000", "NOT_OPENED", "LANE-1"]],
        [["REL-STATUS", "SRC-STATUS", "BOX-1", "G-1", "HOT", "25", "20260528100100", "DECOMM", "LANE-1"]],
        [["G-1", "20260528090000", "20260528110000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["access_tier"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 25}


def test_reason_must_be_allowed():
    """A release reason outside the allowed milestone 1 set must not match."""
    build_program()
    write_inputs(
        [["SRC-REASON", "BOX-2", "G-1", "WARM", "35", "20260528100000", "LOCKED", "LANE-2"]],
        [["REL-REASON", "SRC-REASON", "BOX-2", "G-1", "WARM", "35", "20260528100100", "INFO", "LANE-2"]],
        [["G-1", "20260528090000", "20260528110000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["access_tier"] == ""
    assert summary["unmatched_amount"] == 35


def test_hold_id_must_match_full_identifier_not_prefix():
    """A release using only a prefix of the hold_id must not match."""
    build_program()
    write_inputs(
        [["SRC-PREFIX-100", "BOX-PREFIX", "G-1", "HOT", "55", "20260528100000", "LOCKED", "LANE-P"]],
        [["REL-PREFIX", "SRC-PREFIX-10", "BOX-PREFIX", "G-1", "HOT", "55", "20260528100100", "DECOMM", "LANE-P"]],
        [["G-1", "20260528090000", "20260528110000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["access_tier"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 55}


def test_asset_id_must_match_exactly():
    """An asset_id mismatch must block matching even when every other field matches."""
    build_program()
    write_inputs(
        [["SRC-ASSET", "BOX-REAL", "G-1", "HOT", "50", "20260528100000", "LOCKED", "LANE-1"]],
        [["REL-ASSET", "SRC-ASSET", "BOX-WRONG", "G-1", "HOT", "50", "20260528100100", "DECOMM", "LANE-1"]],
        [["G-1", "20260528090000", "20260528110000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["access_tier"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 50}


def test_aisle_id_and_rack_are_required_identity_fields():
    """Aisle and rack mismatches must each block otherwise valid releases."""
    build_program()
    write_inputs(
        [
            ["SRC-AISLE", "BOX-AISLE", "G-1", "HOT", "60", "20260528100000", "LOCKED", "LANE-A"],
            ["SRC-RACK", "BOX-RACK", "G-1", "WARM", "65", "20260528100000", "LOCKED", "LANE-R"],
        ],
        [
            ["REL-AISLE", "SRC-AISLE", "BOX-AISLE", "G-X", "HOT", "60", "20260528100100", "DECOMM", "LANE-A"],
            ["REL-RACK", "SRC-RACK", "BOX-RACK", "G-1", "WARM", "65", "20260528100100", "MIGRATE", "LANE-X"],
        ],
        [["G-1", "20260528090000", "20260528110000", "OPEN"], ["G-X", "20260528090000", "20260528110000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
    assert [row["access_tier"] for row in rows] == ["", ""]
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 2, "unmatched_amount": 125}


def test_consumption_prevents_second_release_match():
    """A matched hold row must be consumed so a later duplicate release stays unmatched."""
    build_program()
    write_inputs(
        [["SRC-CONSUME", "BOX-3", "G-1", "HOT", "45", "20260528100000", "LOCKED", "LANE-3"]],
        [
            ["REL-CONSUME-1", "SRC-CONSUME", "BOX-3", "G-1", "HOT", "45", "20260528100100", "DECOMM", "LANE-3"],
            ["REL-CONSUME-2", "SRC-CONSUME", "BOX-3", "G-1", "HOT", "45", "20260528100200", "DECOMM", "LANE-3"],
        ],
        [["G-1", "20260528090000", "20260528110000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert [row["access_tier"] for row in rows] == ["HOT", ""]
    assert summary == {"matched_count": 1, "matched_amount": 45, "unmatched_count": 1, "unmatched_amount": 45}


def test_first_qualifying_source_row_in_file_order_is_consumed():
    """When two source rows qualify for the first release, milestone 1 must consume the first source row in file order."""
    build_program()
    write_inputs(
        [
            ["SRC-FIRST", "BOX-FIRST", "G-FIRST", "HOT", "90", "20260528100000", "LOCKED", "LANE-FIRST"],
            ["SRC-FIRST", "BOX-FIRST", "G-FIRST", "HOT", "90", "20260528100500", "LOCKED", "LANE-FIRST"],
        ],
        [
            ["REL-FIRST-1", "SRC-FIRST", "BOX-FIRST", "G-FIRST", "HOT", "90", "20260528100600", "DECOMM", "LANE-FIRST"],
            ["REL-FIRST-2", "SRC-FIRST", "BOX-FIRST", "G-FIRST", "HOT", "90", "20260528100400", "DECOMM", "LANE-FIRST"],
        ],
        [["G-FIRST", "20260528090000", "20260528110000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert [row["access_tier"] for row in rows] == ["HOT", ""]
    assert summary == {"matched_count": 1, "matched_amount": 90, "unmatched_count": 1, "unmatched_amount": 90}


def test_windows_file_is_ignored_for_initial_matching_contract():
    """A closed or unrelated windows.csv row must not block otherwise valid initial matches."""
    build_program()
    write_inputs(
        [
            ["SRC-WINDOW-1", "BOX-W1", "G-W", "HOT", "75", "20260528100000", "LOCKED", "LANE-W1"],
            ["SRC-WINDOW-2", "BOX-W2", "G-MISSING", "WARM", "80", "20260528100000", "LOCKED", "LANE-W2"],
        ],
        [
            ["REL-WINDOW-1", "SRC-WINDOW-1", "BOX-W1", "G-W", "HOT", "75", "20260528100100", "DECOMM", "LANE-W1"],
            ["REL-WINDOW-2", "SRC-WINDOW-2", "BOX-W2", "G-MISSING", "WARM", "80", "20260528100100", "OVERRIDE", "LANE-W2"],
        ],
        [
            ["G-W", "20260528090000", "20260528110000", "CLOSED"],
            ["G-OTHER", "20260528090000", "20260528110000", "OPEN"],
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["access_tier"] for row in rows] == ["HOT", "WARM"]
    assert summary == {
        "matched_count": 2,
        "matched_amount": 155,
        "unmatched_count": 0,
        "unmatched_amount": 0,
    }


def test_non_numeric_timestamps_stay_unmatched():
    """Non-numeric hold_ts or release_ts values must reject matching."""
    build_program()
    write_inputs(
        [["SRC-BAD-TS", "PARTY-1", "S-1", "HOT", "10", "bad-ts", "LOCKED", "L1"]],
        [["ACT-BAD-TS", "SRC-BAD-TS", "PARTY-1", "S-1", "HOT", "10", "20260528140500", "DECOMM", "L1"]],
        [["S-1", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["access_tier"] == ""
    assert summary["matched_count"] == 0


def test_non_numeric_release_ts_stays_unmatched():
    """A non-numeric release_ts must reject matching even when the source timestamp is valid."""
    build_program()
    write_inputs(
        [["SRC-OK-TS", "PARTY-1", "S-1", "HOT", "10", "20260528140000", "LOCKED", "L1"]],
        [["ACT-BAD-RTS", "SRC-OK-TS", "PARTY-1", "S-1", "HOT", "10", "bad-release", "DECOMM", "L1"]],
        [["S-1", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["access_tier"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 10}


def test_access_tier_trims_and_case_folds_before_matching():
    """Access-tier matching should ignore surrounding spaces and case differences on both sides."""
    build_program()
    write_inputs(
        [
            ["SRC-TIER-HOT", "PARTY-T1", "S-TIER", " hot ", "15", "20260528100000", "LOCKED", "LANE-T1"],
            ["SRC-TIER-WARM", "PARTY-T2", "S-TIER", " wArM ", "16", "20260528100000", "LOCKED", "LANE-T2"],
        ],
        [
            ["REL-TIER-HOT", "SRC-TIER-HOT", "PARTY-T1", "S-TIER", "HOT", "15", "20260528100100", "DECOMM", "LANE-T1"],
            ["REL-TIER-WARM", "SRC-TIER-WARM", "PARTY-T2", "S-TIER", " warm ", "16", "20260528100100", "OVERRIDE", "LANE-T2"],
        ],
        [["S-TIER", "20260528090000", "20260528110000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["access_tier"] for row in rows] == ["HOT", "WARM"]
    assert summary == {
        "matched_count": 2,
        "matched_amount": 31,
        "unmatched_count": 0,
        "unmatched_amount": 0,
    }


def test_milestone1_rejects_legacy_alias_codes_even_if_both_sides_match():
    """Milestone 1 must reject IN/CU/SE aliases and COLD until milestone 2 alias support is added."""
    build_program()
    write_inputs(
        [
            ["SRC-ALIAS-1", "PARTY-A1", "S-A", "IN", "11", "20260528120000", "LOCKED", "L1"],
            ["SRC-ALIAS-2", "PARTY-A2", "S-A", "COLD", "12", "20260528120000", "LOCKED", "L2"],
        ],
        [
            ["ACT-ALIAS-1", "SRC-ALIAS-1", "PARTY-A1", "S-A", "IN", "11", "20260528120100", "DECOMM", "L1"],
            ["ACT-ALIAS-2", "SRC-ALIAS-2", "PARTY-A2", "S-A", "COLD", "12", "20260528120100", "MIGRATE", "L2"],
        ],
        [["S-A", "20260528115900", "20260528123000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
    assert [row["access_tier"] for row in rows] == ["", ""]
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 2, "unmatched_amount": 23}
