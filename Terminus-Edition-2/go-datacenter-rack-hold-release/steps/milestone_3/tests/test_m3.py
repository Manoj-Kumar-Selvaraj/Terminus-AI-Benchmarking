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
REJECTIONS = APP / "out" / "rack_release_rejections.csv"


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
    REJECTIONS.unlink(missing_ok=True)


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
    with REJECTIONS.open(newline="") as handle:
        rejections = list(csv.DictReader(handle))
    return rows, summary, rejections


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
    rows, summary, _ = run_program()
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
    rows, summary, _ = run_program()
    assert REPORT.read_text().splitlines()[0] == "release_id,hold_id,asset_id,aisle_id,access_tier,amount,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["access_tier"] for row in rows] == ["HOT", "WARM", "COLD"]
    assert summary == {"matched_count": 3, "matched_amount": 102, "unmatched_count": 0, "unmatched_amount": 0}


def test_unknown_access_tier_stays_unmatched_inside_open_window():
    """The M3 window rules must not weaken the canonical access_tier gate."""
    build_program()
    write_inputs(
        [["SRC-BAD-WINDOW", "BOX-BAD", "G-3", "BAD", "90", "20260528150000", "LOCKED", "LANE-B"]],
        [["REL-BAD-WINDOW", "SRC-BAD-WINDOW", "BOX-BAD", "G-3", "BAD", "90", "20260528150100", "OVERRIDE", "LANE-B"]],
        [["G-3", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary, _ = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["access_tier"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 90}


def test_release_after_window_close_is_unmatched():
    """A release after the matching window close_ts must stay unmatched."""
    build_program()
    write_inputs(
        [["SRC-WINDOW-CLOSE", "BOX-WINDOW-CLOSE", "G-3", "COLD", "95", "20260528150000", "LOCKED", "LANE-C"]],
        [["REL-WINDOW-CLOSE", "SRC-WINDOW-CLOSE", "BOX-WINDOW-CLOSE", "G-3", "SE", "95", "20260528153100", "OVERRIDE", "LANE-C"]],
        [["G-3", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary, _ = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["access_tier"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 95}


def test_source_hold_timestamp_before_open_window_is_unmatched():
    """A source hold_ts before open_ts is outside the authoritative window."""
    build_program()
    write_inputs(
        [["SRC-BEFORE-OPEN", "BOX-BEFORE-OPEN", "G-4", "HOT", "41", "20260528145859", "LOCKED", "LANE-D"]],
        [["REL-BEFORE-OPEN", "SRC-BEFORE-OPEN", "BOX-BEFORE-OPEN", "G-4", "HOT", "41", "20260528150000", "DECOMM", "LANE-D"]],
        [["G-4", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary, _ = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["access_tier"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 41}


def test_window_state_malformed_times_and_latest_candidate_order():
    """Closed/malformed window rows reject, while duplicate candidates resolve by latest hold_ts."""
    build_program()
    write_inputs(
        [
            ["SRC-WIN-1", "PARTY-1", "S-O", "HOT", "1", "20260528150000", "LOCKED", "L1"],
            ["SRC-WIN-2", "PARTY-2", "S-C", "HOT", "2", "20260528150000", "LOCKED", "L2"],
            ["SRC-WIN-3", "PARTY-3", "S-M", "WARM", "3", "bad-time", "LOCKED", "L3"],
            ["SRC-DUPE", "PARTY-4", "S-O", "COLD", "4", "20260528150100", "LOCKED", "L4"],
            ["SRC-DUPE", "PARTY-4", "S-O", "COLD", "4", "20260528150200", "LOCKED", "L4"],
        ],
        [
            ["ACT-1", "SRC-WIN-1", "PARTY-1", "S-O", "HOT", "1", "20260528150500", "DECOMM", "L1"],
            ["ACT-2", "SRC-WIN-2", "PARTY-2", "S-C", "HOT", "2", "20260528150500", "DECOMM", "L2"],
            ["ACT-3", "SRC-WIN-3", "PARTY-3", "S-M", "WARM", "3", "20260528150500", "MIGRATE", "L3"],
            ["ACT-4", "SRC-DUPE", "PARTY-4", "S-O", "COLD", "4", "20260528150600", "OVERRIDE", "L4"],
            ["ACT-5", "SRC-DUPE", "PARTY-4", "S-O", "COLD", "4", "20260528150150", "DECOMM", "L4"],
        ],
        [["S-O", "20260528145900", "20260528153000", "OPEN"], ["S-C", "20260528145900", "20260528153000", "CLOSED"], ["S-M", "bad-time", "20260528153000", "OPEN"]],
    )
    rows, summary, _ = run_program()
    assert [row["release_id"] for row in rows] == ["ACT-1", "ACT-2", "ACT-3", "ACT-4", "ACT-5"]
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "MATCHED", "MATCHED"]
    assert [row["access_tier"] for row in rows] == ["HOT", "", "", "COLD", "COLD"]
    assert summary == {"matched_count": 3, "matched_amount": 9, "unmatched_count": 2, "unmatched_amount": 5}


def test_same_hold_timestamp_tie_uses_earliest_source_row():
    """When duplicate hold_id rows share the latest qualifying hold_ts, the earliest source row wins."""
    build_program()
    write_inputs(
        [
            ["SRC-TIE", "PARTY-5", "S-T", "HOT", "22", "20260528150000", "LOCKED", "L5"],
            ["SRC-TIE", "PARTY-5", "S-T", "HOT", "22", "20260528150000", "LOCKED", "L5"],
        ],
        [
            ["ACT-TIE", "SRC-TIE", "PARTY-5", "S-T", "HOT", "22", "20260528150500", "DECOMM", "L5"],
        ],
        [["S-T", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary, _ = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["access_tier"] == "HOT"
    assert summary == {"matched_count": 1, "matched_amount": 22, "unmatched_count": 0, "unmatched_amount": 0}


def test_equal_hold_timestamp_duplicate_rows_are_consumed_by_position():
    """Equal-timestamp duplicate source rows remain independently consumable by row position."""
    build_program()
    write_inputs(
        [
            ["SRC-TIE-POS", "PARTY-6", "S-T", "HOT", "24", "20260528150000", "LOCKED", "L6"],
            ["SRC-TIE-POS", "PARTY-6", "S-T", "HOT", "24", "20260528150000", "LOCKED", "L6"],
        ],
        [
            ["ACT-TIE-POS-1", "SRC-TIE-POS", "PARTY-6", "S-T", "HOT", "24", "20260528150500", "DECOMM", "L6"],
            ["ACT-TIE-POS-2", "SRC-TIE-POS", "PARTY-6", "S-T", "HOT", "24", "20260528150600", "DECOMM", "L6"],
            ["ACT-TIE-POS-3", "SRC-TIE-POS", "PARTY-6", "S-T", "HOT", "24", "20260528150700", "DECOMM", "L6"],
        ],
        [["S-T", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary, _ = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["access_tier"] for row in rows] == ["HOT", "HOT", ""]
    assert summary == {"matched_count": 2, "matched_amount": 48, "unmatched_count": 1, "unmatched_amount": 24}


def test_windowed_alias_matching_still_requires_full_identity_fields():
    """Window-gated alias matching must still require full hold_id, aisle_id, and rack equality."""
    build_program()
    write_inputs(
        [
            ["SRC-M3-PREFIX-100", "BOX-PREFIX", "G-3", "COLD", "31", "20260528150000", "LOCKED", "LANE-P"],
            ["SRC-M3-AISLE", "BOX-AISLE", "G-3", "WARM", "32", "20260528150000", "LOCKED", "LANE-A"],
            ["SRC-M3-RACK", "BOX-RACK", "G-3", "HOT", "33", "20260528150000", "LOCKED", "LANE-R"],
        ],
        [
            ["REL-M3-PREFIX", "SRC-M3-PREFIX-10", "BOX-PREFIX", "G-3", "SE", "31", "20260528150100", "OVERRIDE", "LANE-P"],
            ["REL-M3-AISLE", "SRC-M3-AISLE", "BOX-AISLE", "G-X", "CU", "32", "20260528150100", "MIGRATE", "LANE-A"],
            ["REL-M3-RACK", "SRC-M3-RACK", "BOX-RACK", "G-3", "IN", "33", "20260528150100", "DECOMM", "LANE-X"],
        ],
        [["G-3", "20260528145900", "20260528153000", "OPEN"], ["G-X", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary, _ = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert [row["access_tier"] for row in rows] == ["", "", ""]
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 3, "unmatched_amount": 96}


def test_non_numeric_release_timestamp_stays_unmatched():
    """A correction with non-numeric release_ts must stay unmatched even inside an OPEN window."""
    build_program()
    write_inputs(
        [["SRC-REL-BAD", "PARTY-1", "S-1", "COLD", "15", "20260528140000", "LOCKED", "L1"]],
        [["ACT-REL-BAD", "SRC-REL-BAD", "PARTY-1", "S-1", "SE", "15", "bad-ts", "DECOMM", "L1"]],
        [["S-1", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary, _ = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["access_tier"] == ""
    assert summary["matched_count"] == 0


def test_missing_unlisted_window_is_not_eligible():
    """If windows.csv has no row for the aisle_id, the source must never match."""
    build_program()
    write_inputs(
        [["SRC-NOWIN", "PARTY-1", "S-NOW", "HOT", "10", "20260528140000", "LOCKED", "L1"]],
        [["ACT-NOWIN", "SRC-NOWIN", "PARTY-1", "S-NOW", "HOT", "10", "20260528140100", "DECOMM", "L1"]],
        [["S-OTHER", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary, _ = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["access_tier"] == ""
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 10}


def test_source_access_tier_alias_normalizes_in_milestone3():
    """Milestone 3 should normalize access_tier aliases on source rows as well as correction rows."""
    build_program()
    write_inputs(
        [["SRC-IN-SOURCE", "PARTY-2", "S-A", " in ", "12", "20260528120000", "LOCKED", "L2"]],
        [["ACT-IN-SOURCE", "SRC-IN-SOURCE", "PARTY-2", "S-A", "HOT", "12", "20260528120100", "OVERRIDE", "L2"]],
        [["S-A", "20260528115900", "20260528123000", "OPEN"]],
    )
    rows, summary, _ = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["access_tier"] == "HOT"
    assert summary == {"matched_count": 1, "matched_amount": 12, "unmatched_count": 0, "unmatched_amount": 0}


def test_open_window_state_is_case_insensitive():
    """A lowercase/uppercase variation of OPEN should still allow eligible matching."""
    build_program()
    write_inputs(
        [["SRC-OPEN-CASE", "PARTY-3", "S-CASE", "WARM", "14", "20260528120000", "LOCKED", "L3"]],
        [["ACT-OPEN-CASE", "SRC-OPEN-CASE", "PARTY-3", "S-CASE", "CU", "14", "20260528120100", "MIGRATE", "L3"]],
        [["S-CASE", "20260528115900", "20260528123000", "open"]],
    )
    rows, summary, _ = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["access_tier"] == "WARM"
    assert summary == {"matched_count": 1, "matched_amount": 14, "unmatched_count": 0, "unmatched_amount": 0}


def test_large_batch_dynamic_aliases_overlapping_windows_and_rejections():
    """A larger mixed batch should exercise dynamic aliases, invalid amounts, windows, and diagnostics."""
    build_program()
    write_aliases(
        [
            ["FIRE", "HOT"],
            ["COZY", "WARM"],
            ["VAULT", "COLD"],
            ["BROKEN", "ARCHIVE"],
        ]
    )
    write_inputs(
        [
            ["SRC-LARGE-001", "ASSET-001", "A-L", "FIRE", "100", "20260528120000", "LOCKED", "R01"],
            ["SRC-LARGE-002", "ASSET-002", "A-L", "COZY", "101", "20260528120100", "LOCKED", "R02"],
            ["SRC-LARGE-003", "ASSET-003", "A-L", "VAULT", "102", "20260528120200", "LOCKED", "R03"],
            ["SRC-LARGE-004", "ASSET-004", "A-L", "HOT", "103", "20260528120300", "HELD", "R04"],
            ["SRC-LARGE-005", "ASSET-005", "A-L", "HOT", "0104", "20260528120400", "LOCKED", "R05"],
            ["SRC-LARGE-006", "ASSET-006", "A-L", "BROKEN", "105", "20260528120500", "LOCKED", "R06"],
            ["SRC-LARGE-007", "ASSET-007", "A-OVER", "HOT", "106", "20260528120600", "LOCKED", "R07"],
            ["SRC-LARGE-007", "ASSET-007", "A-OVER", "HOT", "106", "20260528120900", "LOCKED", "R07"],
            ["SRC-LARGE-008", "ASSET-008", "A-TIE", "WARM", "107", "20260528121000", "LOCKED", "R08"],
            ["SRC-LARGE-008", "ASSET-008", "A-TIE", "WARM", "107", "20260528121000", "LOCKED", "R08"],
            ["SRC-LARGE-009", "ASSET-009", "A-CLOSED", "COLD", "108", "20260528121100", "LOCKED", "R09"],
            ["SRC-LARGE-010", "ASSET-010", "A-L", "HOT", "109", "bad-source", "LOCKED", "R10"],
        ],
        [
            ["REL-LARGE-001", "SRC-LARGE-001", "ASSET-001", "A-L", "HOT", "100", "20260528121200", "DECOMM", "R01"],
            ["REL-LARGE-002", "SRC-LARGE-002", "ASSET-002", "A-L", "WARM", "101", "20260528121200", "MIGRATE", "R02"],
            ["REL-LARGE-003", "SRC-LARGE-003", "ASSET-003", "A-L", "COLD", "102", "20260528121200", "OVERRIDE", "R03"],
            ["REL-LARGE-004", "SRC-LARGE-004", "ASSET-004", "A-L", "HOT", "103", "20260528121200", "DECOMM", "R04"],
            ["REL-LARGE-005", "SRC-LARGE-005", "ASSET-005", "A-L", "HOT", "0104", "20260528121200", "DECOMM", "R05"],
            ["REL-LARGE-006", "SRC-LARGE-006", "ASSET-006", "A-L", "BROKEN", "105", "20260528121200", "DECOMM", "R06"],
            ["REL-LARGE-007", "SRC-LARGE-007", "ASSET-007", "A-OVER", "FIRE", "106", "20260528121100", "DECOMM", "R07"],
            ["REL-LARGE-008", "SRC-LARGE-007", "ASSET-007", "A-OVER", "FIRE", "106", "20260528120400", "DECOMM", "R07"],
            ["REL-LARGE-009", "SRC-LARGE-008", "ASSET-008", "A-TIE", "COZY", "107", "20260528121100", "MIGRATE", "R08"],
            ["REL-LARGE-010", "SRC-LARGE-008", "ASSET-008", "A-TIE", "COZY", "107", "20260528121200", "MIGRATE", "R08"],
            ["REL-LARGE-011", "SRC-LARGE-009", "ASSET-009", "A-CLOSED", "VAULT", "108", "20260528121200", "OVERRIDE", "R09"],
            ["REL-LARGE-012", "SRC-LARGE-010", "ASSET-010", "A-L", "HOT", "109", "20260528121200", "DECOMM", "R10"],
            ["REL-LARGE-013", "SRC-LARGE-001", "ASSET-001", "A-L", "HOT", "+100", "20260528121200", "DECOMM", "R01"],
            ["REL-LARGE-014", "SRC-LARGE-001", "ASSET-001", "A-L", "HOT", "100", "bad-release", "DECOMM", "R01"],
            ["REL-LARGE-015", "SRC-MISSING", "ASSET-404", "A-L", "HOT", "111", "20260528121200", "DECOMM", "R99"],
            ["REL-LARGE-016", "SRC-LARGE-001", "ASSET-001", "A-L", "HOT", "100", "20260528121200", "INFO", "R01"],
        ],
        [
            ["A-L", "20260528115900", "20260528123000", "OPEN"],
            ["A-OVER", "20260528120500", "20260528120800", "OPEN"],
            ["A-OVER", "20260528120830", "20260528121500", "OPEN"],
            ["A-TIE", "20260528120900", "20260528121500", "open"],
            ["A-CLOSED", "20260528120900", "20260528121500", "CLOSED"],
            ["A-CLOSED", "bad-open", "20260528121500", "OPEN"],
        ],
    )
    rows, summary, rejections = run_program()

    assert [row["status"] for row in rows] == [
        "MATCHED",
        "MATCHED",
        "MATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "MATCHED",
        "UNMATCHED",
        "MATCHED",
        "MATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
    ]
    assert [row["access_tier"] for row in rows[:3]] == ["HOT", "WARM", "COLD"]
    assert summary == {"matched_count": 6, "matched_amount": 623, "unmatched_count": 10, "unmatched_amount": 842}
    assert rejections == [
        {"release_id": "REL-LARGE-004", "code": "NO_ELIGIBLE_SOURCE"},
        {"release_id": "REL-LARGE-005", "code": "BAD_RELEASE_AMOUNT"},
        {"release_id": "REL-LARGE-006", "code": "NO_ELIGIBLE_SOURCE"},
        {"release_id": "REL-LARGE-008", "code": "NO_ELIGIBLE_SOURCE"},
        {"release_id": "REL-LARGE-011", "code": "WINDOW_INELIGIBLE"},
        {"release_id": "REL-LARGE-012", "code": "NO_ELIGIBLE_SOURCE"},
        {"release_id": "REL-LARGE-013", "code": "BAD_RELEASE_AMOUNT"},
        {"release_id": "REL-LARGE-014", "code": "BAD_RELEASE_TS"},
        {"release_id": "REL-LARGE-015", "code": "NO_SOURCE_IDENTITY"},
        {"release_id": "REL-LARGE-016", "code": "BAD_REASON"},
    ]


def test_rejection_file_has_only_unmatched_rows_in_input_order():
    """Matched corrections must be absent from diagnostics and unmatched rows must keep action order."""
    build_program()
    write_aliases([["IN", "HOT"], ["CU", "WARM"], ["SE", "COLD"]])
    write_inputs(
        [
            ["SRC-DIAG-1", "ASSET-D1", "A-DIAG", "HOT", "10", "20260528120000", "LOCKED", "R1"],
            ["SRC-DIAG-2", "ASSET-D2", "A-DIAG", "WARM", "11", "20260528120100", "LOCKED", "R2"],
        ],
        [
            ["REL-DIAG-1", "SRC-DIAG-1", "ASSET-D1", "A-DIAG", "HOT", "10", "20260528120200", "DECOMM", "R1"],
            ["REL-DIAG-2", "SRC-DIAG-2", "ASSET-D2", "A-DIAG", "WARM", "11", "bad-ts", "MIGRATE", "R2"],
            ["REL-DIAG-3", "SRC-DIAG-404", "ASSET-D4", "A-DIAG", "HOT", "12", "20260528120200", "DECOMM", "R4"],
        ],
        [["A-DIAG", "20260528115900", "20260528123000", "OPEN"]],
    )
    rows, summary, rejections = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 2, "unmatched_amount": 23}
    assert rejections == [
        {"release_id": "REL-DIAG-2", "code": "BAD_RELEASE_TS"},
        {"release_id": "REL-DIAG-3", "code": "NO_SOURCE_IDENTITY"},
    ]
