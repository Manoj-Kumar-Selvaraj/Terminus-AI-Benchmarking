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
ALIASES = APP / "config" / "access_tier_aliases.csv"
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


def write_aliases(rows):
    """Overwrite alias config at runtime."""
    write_csv(ALIASES, ["alias", "canonical"], rows)


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


def test_aliases_full_keys_and_canonical_output():
    """Aliases should match full source keys and emit canonical access_tier values."""
    build_program()
    write_inputs(
        [
            ["SRC-100000001", "PARTY-1", "S-A", "HOT", "12", "20260528120500", "LOCKED", "LOC-1"],
            ["SRC-100000002", "PARTY-2", "S-A", "WARM", "34", "20260528120600", "LOCKED", "LOC-2"],
            ["SRC-100000003", "PARTY-3", "S-B", "COLD", "56", "20260528130500", "LOCKED", "LOC-3"],
        ],
        [
            ["ACT-1", "SRC-100000001", "PARTY-1", "S-A", "IN", "12", "20260528121000", "DECOMM", "LOC-1"],
            ["ACT-2", "SRC-100000002", "PARTY-2", "S-A", "CU", "34", "20260528121100", "MIGRATE", "LOC-2"],
            ["ACT-3", "SRC-100000003", "PARTY-3", "S-B", "SE", "56", "20260528131000", "OVERRIDE", "LOC-3"],
        ],
        [["S-A", "20260528120000", "20260528123000", "OPEN"], ["S-B", "20260528130000", "20260528133000", "OPEN"]],
    )
    rows, summary = run_program()
    assert REPORT.read_text().splitlines()[0] == "release_id,hold_id,asset_id,aisle_id,access_tier,amount,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["access_tier"] for row in rows] == ["HOT", "WARM", "COLD"]
    assert summary == {"matched_count": 3, "matched_amount": 102, "unmatched_count": 0, "unmatched_amount": 0}


def test_security_alias_is_valid_canonical_from_milestone_2():
    """The SE alias should normalize to COLD and pass the canonical access_tier gate."""
    build_program()
    write_inputs(
        [["SRC-COLD", "BOX-SEC", "G-2", "COLD", "70", "20260528120000", "LOCKED", "LANE-S"]],
        [["REL-COLD", "SRC-COLD", "BOX-SEC", "G-2", "SE", "70", "20260528120100", "OVERRIDE", "LANE-S"]],
        [["G-2", "20260528115900", "20260528123000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["access_tier"] == "COLD"
    assert summary == {"matched_count": 1, "matched_amount": 70, "unmatched_count": 0, "unmatched_amount": 0}


def test_alias_normalization_trims_and_case_folds_before_matching():
    """Lowercase aliases with surrounding spaces should match and emit canonical access_tier."""
    build_program()
    write_inputs(
        [
            ["SRC-TRIM-1", "BOX-TRIM-1", "G-2", " hot ", "71", "20260528120000", "LOCKED", "LANE-T1"],
            ["SRC-TRIM-2", "BOX-TRIM-2", "G-2", " cold ", "72", "20260528120000", "LOCKED", "LANE-T2"],
        ],
        [
            ["REL-TRIM-1", "SRC-TRIM-1", "BOX-TRIM-1", "G-2", " in ", "71", "20260528120100", "DECOMM", "LANE-T1"],
            ["REL-TRIM-2", "SRC-TRIM-2", "BOX-TRIM-2", "G-2", " se ", "72", "20260528120100", "OVERRIDE", "LANE-T2"],
        ],
        [["G-2", "20260528115900", "20260528123000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["access_tier"] for row in rows] == ["HOT", "COLD"]
    assert summary == {"matched_count": 2, "matched_amount": 143, "unmatched_count": 0, "unmatched_amount": 0}


def test_alias_matching_still_requires_full_hold_id_aisle_and_rack():
    """Alias-aware matching must still reject prefix ids, aisle mismatches, and rack mismatches."""
    build_program()
    write_inputs(
        [
            ["SRC-ALIAS-PREFIX-100", "BOX-PREFIX", "G-2", "HOT", "81", "20260528120000", "LOCKED", "LANE-P"],
            ["SRC-ALIAS-AISLE", "BOX-AISLE", "G-2", "WARM", "82", "20260528120000", "LOCKED", "LANE-A"],
            ["SRC-ALIAS-RACK", "BOX-RACK", "G-2", "COLD", "83", "20260528120000", "LOCKED", "LANE-R"],
        ],
        [
            ["REL-ALIAS-PREFIX", "SRC-ALIAS-PREFIX-10", "BOX-PREFIX", "G-2", "IN", "81", "20260528120100", "DECOMM", "LANE-P"],
            ["REL-ALIAS-AISLE", "SRC-ALIAS-AISLE", "BOX-AISLE", "G-X", "CU", "82", "20260528120100", "MIGRATE", "LANE-A"],
            ["REL-ALIAS-RACK", "SRC-ALIAS-RACK", "BOX-RACK", "G-2", "SE", "83", "20260528120100", "OVERRIDE", "LANE-X"],
        ],
        [["G-2", "20260528115900", "20260528123000", "OPEN"], ["G-X", "20260528115900", "20260528123000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert [row["access_tier"] for row in rows] == ["", "", ""]
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 3, "unmatched_amount": 246}


def test_unknown_access_tier_stays_unmatched_after_alias_normalization():
    """Unknown access_tier values must not match even when source and release use the same value."""
    build_program()
    write_inputs(
        [["SRC-BAD-TYPE", "BOX-BAD", "G-2", "BAD", "80", "20260528120000", "LOCKED", "LANE-B"]],
        [["REL-BAD-TYPE", "SRC-BAD-TYPE", "BOX-BAD", "G-2", "BAD", "80", "20260528120100", "OVERRIDE", "LANE-B"]],
        [["G-2", "20260528115900", "20260528123000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["access_tier"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 80}


def test_source_access_tier_aliases_are_normalized_before_matching():
    """Legacy access_tier aliases should normalize on source rows too (not only on correction rows)."""
    build_program()
    write_inputs(
        [["SRC-IN-SOURCE", "BOX-IN-SOURCE", "G-2", " in ", "12", "20260528120000", "LOCKED", "LANE-IN"]],
        [["REL-IN-SOURCE", "SRC-IN-SOURCE", "BOX-IN-SOURCE", "G-2", "HOT", "12", "20260528120100", "DECOMM", "LANE-IN"]],
        [["G-2", "20260528115900", "20260528123000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED"]
    assert [row["access_tier"] for row in rows] == ["HOT"]
    assert summary == {"matched_count": 1, "matched_amount": 12, "unmatched_count": 0, "unmatched_amount": 0}


def test_milestone2_ignores_windows_file_even_when_rows_are_closed():
    """Milestone 2 must not apply windows.csv gating before milestone 3."""
    build_program()
    write_inputs(
        [["SRC-WIN-IGN", "PARTY-W1", "S-W", "HOT", "19", "20260528120000", "LOCKED", "L1"]],
        [["ACT-WIN-IGN", "SRC-WIN-IGN", "PARTY-W1", "S-W", "IN", "19", "20260528120100", "OVERRIDE", "L1"]],
        [["S-W", "20260528115900", "20260528123000", "CLOSED"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["access_tier"] == "HOT"
    assert summary == {"matched_count": 1, "matched_amount": 19, "unmatched_count": 0, "unmatched_amount": 0}


def test_aliases_are_loaded_from_runtime_config_not_hardcoded():
    """Verifier-overwritten aliases should drive matching, while bad alias targets are ignored."""
    build_program()
    write_aliases(
        [
            ["FIRE", "HOT"],
            ["COZY", "WARM"],
            ["VAULT", "COLD"],
            ["STALE", "ARCHIVE"],
        ]
    )
    write_inputs(
        [
            ["SRC-DYN-1", "ASSET-D1", "A-D", "FIRE", "101", "20260528120000", "LOCKED", "R-D1"],
            ["SRC-DYN-2", "ASSET-D2", "A-D", "COZY", "102", "20260528120100", "LOCKED", "R-D2"],
            ["SRC-DYN-3", "ASSET-D3", "A-D", "VAULT", "103", "20260528120200", "LOCKED", "R-D3"],
            ["SRC-DYN-4", "ASSET-D4", "A-D", "STALE", "104", "20260528120300", "LOCKED", "R-D4"],
        ],
        [
            ["REL-DYN-1", "SRC-DYN-1", "ASSET-D1", "A-D", "HOT", "101", "20260528120400", "DECOMM", "R-D1"],
            ["REL-DYN-2", "SRC-DYN-2", "ASSET-D2", "A-D", "WARM", "102", "20260528120400", "MIGRATE", "R-D2"],
            ["REL-DYN-3", "SRC-DYN-3", "ASSET-D3", "A-D", "COLD", "103", "20260528120400", "OVERRIDE", "R-D3"],
            ["REL-DYN-4", "SRC-DYN-4", "ASSET-D4", "A-D", "STALE", "104", "20260528120400", "DECOMM", "R-D4"],
        ],
        [["A-D", "20260528115900", "20260528123000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["access_tier"] for row in rows] == ["HOT", "WARM", "COLD", ""]
    assert summary == {"matched_count": 3, "matched_amount": 306, "unmatched_count": 1, "unmatched_amount": 104}


def test_amounts_must_be_canonical_positive_integer_strings():
    """Signs, leading zeroes, zero, decimals, and blanks should be ineligible and total as zero when unmatched."""
    build_program()
    write_aliases([["IN", "HOT"], ["CU", "WARM"], ["SE", "COLD"]])
    write_inputs(
        [
            ["SRC-AMT-OK", "ASSET-A0", "A-AMT", "HOT", "99", "20260528120000", "LOCKED", "R-A0"],
            ["SRC-AMT-ZERO", "ASSET-A1", "A-AMT", "HOT", "0", "20260528120000", "LOCKED", "R-A1"],
            ["SRC-AMT-LEAD", "ASSET-A2", "A-AMT", "HOT", "010", "20260528120000", "LOCKED", "R-A2"],
            ["SRC-AMT-SIGN", "ASSET-A3", "A-AMT", "HOT", "+11", "20260528120000", "LOCKED", "R-A3"],
            ["SRC-AMT-DEC", "ASSET-A4", "A-AMT", "HOT", "12.0", "20260528120000", "LOCKED", "R-A4"],
            ["SRC-AMT-NEG", "ASSET-A5", "A-AMT", "HOT", "-5", "20260528120000", "LOCKED", "R-A5"],
        ],
        [
            ["REL-AMT-OK", "SRC-AMT-OK", "ASSET-A0", "A-AMT", "HOT", "99", "20260528120100", "DECOMM", "R-A0"],
            ["REL-AMT-ZERO", "SRC-AMT-ZERO", "ASSET-A1", "A-AMT", "HOT", "0", "20260528120100", "DECOMM", "R-A1"],
            ["REL-AMT-LEAD", "SRC-AMT-LEAD", "ASSET-A2", "A-AMT", "HOT", "010", "20260528120100", "DECOMM", "R-A2"],
            ["REL-AMT-SIGN", "SRC-AMT-SIGN", "ASSET-A3", "A-AMT", "HOT", "+11", "20260528120100", "DECOMM", "R-A3"],
            ["REL-AMT-DEC", "SRC-AMT-DEC", "ASSET-A4", "A-AMT", "HOT", "12.0", "20260528120100", "DECOMM", "R-A4"],
            ["REL-AMT-NEG", "SRC-AMT-NEG", "ASSET-A5", "A-AMT", "HOT", "-5", "20260528120100", "DECOMM", "R-A5"],
        ],
        [["A-AMT", "20260528115900", "20260528123000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary == {"matched_count": 1, "matched_amount": 99, "unmatched_count": 5, "unmatched_amount": 0}
