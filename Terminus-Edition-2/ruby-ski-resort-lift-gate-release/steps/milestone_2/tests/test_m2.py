"""Tests for realtime ski resort lift gate release reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "lift_sessions.csv"
ACTION = APP / "data" / "gate_releases.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "lift_gate_release_report.csv"
SUMMARY = APP / "out" / "lift_gate_release_summary.txt"


def build_program():
    """Prepare the reconciler for one test scenario."""
    pass


def write_csv(path, header, rows):
    """Write one CSV fixture."""
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(source, action, windows):
    """Overwrite all input files at runtime."""
    write_csv(SOURCE, ["pass_id", "skier_id", "lift_id", "pass_tier", "amount", "scan_ts", "status", "slope"], source)
    write_csv(ACTION, ["release_id", "pass_id", "skier_id", "lift_id", "pass_tier", "amount", "release_ts", "reason", "slope"], action)
    write_csv(WINDOWS, ["lift_id", "open_ts", "close_ts", "state"], windows)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the reconciler and parse outputs."""
    subprocess.run(["ruby", "/app/app/reconcile.rb"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        if not line.strip():
            continue
        key, value = line.split("=", 1)
        summary[key.strip()] = int(value.strip())
    return rows, summary


def test_all_gates_consumption_and_positive_unmatched_totals():
    """Every identity, status, timestamp, reason, and consumption gate should reject bad candidates."""
    build_program()
    write_inputs(
        [
            ["SRC-GATE-1", "PARTY-1", "S-G", "DAY", "10", "20260528140000", "SCANNED", "L1"],
            ["SRC-GATE-2", "PARTY-2", "S-G", "DAY", "20", "20260528140100", "BAD", "L2"],
            ["SRC-GATE-3", "PARTY-3", "S-G", "SEASON", "30", "20260528140200", "SCANNED", "L3"],
            ["SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140300", "SCANNED", "L4"],
        ],
        [
            ["ACT-A", "SRC-GATE-1", "PARTY-1", "S-G", "DAY", "10", "20260528140500", "VOID", "L1"],
            ["ACT-B", "SRC-GATE-1", "PARTY-1", "S-G", "DAY", "10", "20260528140600", "VOID", "L1"],
            ["ACT-C", "SRC-GATE-2", "PARTY-2", "S-G", "DAY", "20", "20260528140700", "VOID", "L2"],
            ["ACT-D", "SRC-GATE-3", "PARTY-X", "S-G", "SEASON", "30", "20260528140700", "COMP", "L3"],
            ["ACT-E", "SRC-GATE-3", "PARTY-3", "S-G", "SEASON", "31", "20260528140700", "COMP", "L3"],
            ["ACT-F", "SRC-GATE-3", "PARTY-3", "S-G", "SEASON", "30", "20260528135959", "COMP", "L3"],
            ["ACT-G", "SRC-GATE-3", "PARTY-3", "S-G", "SEASON", "30", "20260528140700", "INFO", "L3"],
            ["ACT-H", "SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140700", "GUEST", "L4"],
        ],
        [["S-G", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert rows[1]["pass_tier"] == ""
    assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 7, "unmatched_amount": 191}


def test_aliases_full_keys_and_canonical_output():
    """Aliases should match full source keys and emit canonical pass_tier values."""
    build_program()
    write_inputs(
        [
            ["SRC-100000001", "PARTY-1", "S-A", "DAY", "12", "20260528120500", "SCANNED", "LOC-1"],
            ["SRC-100000002", "PARTY-2", "S-A", "SEASON", "34", "20260528120600", "SCANNED", "LOC-2"],
            ["SRC-100000003", "PARTY-3", "S-B", "VIP", "56", "20260528130500", "SCANNED", "LOC-3"],
        ],
        [
            ["ACT-1", "SRC-100000001", "PARTY-1", "S-A", "HR", "12", "20260528121000", "VOID", "LOC-1"],
            ["ACT-2", "SRC-100000002", "PARTY-2", "S-A", "QR", "34", "20260528121100", "COMP", "LOC-2"],
            ["ACT-3", "SRC-100000003", "PARTY-3", "S-B", "CC", "56", "20260528131000", "GUEST", "LOC-3"],
        ],
        [["S-A", "20260528120000", "20260528123000", "OPEN"], ["S-B", "20260528130000", "20260528133000", "OPEN"]],
    )
    rows, summary = run_program()
    assert REPORT.read_text().splitlines()[0] == "release_id,pass_id,skier_id,lift_id,pass_tier,amount,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["pass_tier"] for row in rows] == ["DAY", "SEASON", "VIP"]
    assert summary == {"matched_count": 3, "matched_amount": 102, "unmatched_count": 0, "unmatched_amount": 0}


def test_unknown_pass_tier_stays_unmatched_even_when_both_sides_match():
    """Shared unknown pass_tier values must not match from milestone 2 onward."""
    build_program()
    write_inputs(
        [["SRC-UNK-1", "PARTY-U", "S-U", "BAD", "18", "20260528170000", "SCANNED", "L1"]],
        [["ACT-UNK-1", "SRC-UNK-1", "PARTY-U", "S-U", "BAD", "18", "20260528170100", "VOID", "L1"]],
        [["S-U", "20260528165900", "20260528173000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert summary["matched_count"] == 0


def test_aliases_trim_and_case_fold_before_matching():
    """Legacy pass_tier aliases should normalize after trimming and case folding."""
    build_program()
    write_inputs(
        [
            ["SRC-ALIAS-1", "PARTY-1", "S-A", "day", "12", "20260528120500", "SCANNED", "LOC-1"],
            ["SRC-ALIAS-2", "PARTY-2", "S-A", " season ", "34", "20260528120600", "SCANNED", "LOC-2"],
        ],
        [
            ["ACT-ALIAS-1", "SRC-ALIAS-1", "PARTY-1", "S-A", " hr ", "12", "20260528121000", "VOID", "LOC-1"],
            ["ACT-ALIAS-2", "SRC-ALIAS-2", "PARTY-2", "S-A", "qR", "34", "20260528121100", "COMP", "LOC-2"],
        ],
        [["S-A", "20260528120000", "20260528123000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["pass_tier"] for row in rows] == ["DAY", "SEASON"]
    assert summary == {"matched_count": 2, "matched_amount": 46, "unmatched_count": 0, "unmatched_amount": 0}


def test_latest_scan_ts_wins_then_earliest_source_row_with_aliases():
    """When several aliased candidates qualify, latest scan_ts wins and tied rows use input order."""
    build_program()
    write_inputs(
        [
            ["SRC-DUPE", "PARTY-D", "S-D", "VIP", "11", "20260528160000", "SCANNED", "L1"],
            ["SRC-DUPE", "PARTY-D", "S-D", "VIP", "11", "20260528160200", "SCANNED", "L1"],
            ["SRC-DUPE", "PARTY-D", "S-D", "VIP", "11", "20260528160200", "SCANNED", "L1"],
        ],
        [
            ["ACT-DUPE-1", "SRC-DUPE", "PARTY-D", "S-D", " cc ", "11", "20260528160300", "VOID", "L1"],
            ["ACT-DUPE-2", "SRC-DUPE", "PARTY-D", "S-D", "CC", "11", "20260528160330", "VOID", "L1"],
            ["ACT-DUPE-3", "SRC-DUPE", "PARTY-D", "S-D", "CC", "11", "20260528160100", "VOID", "L1"],
        ],
        [["S-D", "20260528155900", "20260528163000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["pass_tier"] for row in rows] == ["VIP", "VIP", "VIP"]
    assert summary == {"matched_count": 3, "matched_amount": 33, "unmatched_count": 0, "unmatched_amount": 0}


def test_prefix_pass_id_still_rejected_with_aliases():
    """Partial pass_id overlap must stay unmatched after milestone 2 aliases."""
    build_program()
    write_inputs(
        [["SRC-P2", "P-1", "S-P", "DAY", "10", "20260528140000", "SCANNED", "L1"]],
        [["ACT-P2", "SRC-P2-X", "P-1", "S-P", "HR", "10", "20260528140500", "VOID", "L1"]],
        [["S-P", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, _ = run_program()
    assert rows[0]["status"] == "UNMATCHED"


def test_alias_only_on_correction_side():
    """Source canonical tier with alias only on the correction should still match."""
    build_program()
    write_inputs(
        [["SRC-AC", "P-1", "S-A", "VIP", "25", "20260528140000", "SCANNED", "L1"]],
        [["ACT-AC", "SRC-AC", "P-1", "S-A", "CC", "25", "20260528140500", "GUEST", "L1"]],
        [["S-A", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, _ = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["pass_tier"] == "VIP"


def test_empty_files_zero_totals_milestone2():
    """Empty inputs should still write schema-valid outputs with zero totals."""
    build_program()
    write_inputs([], [], [])
    rows, summary = run_program()
    assert rows == []
    assert summary["unmatched_count"] == 0


def test_bad_tier_on_both_sides_stays_unmatched():
    """Shared BAD pass_tier must not match even when alias rules would otherwise apply."""
    build_program()
    write_inputs(
        [["SRC-B2", "P-1", "S-B", "BAD", "18", "20260528170000", "SCANNED", "L1"]],
        [["ACT-B2", "SRC-B2", "P-1", "S-B", "BAD", "18", "20260528170100", "VOID", "L1"]],
        [["S-B", "20260528165900", "20260528173000", "OPEN"]],
    )
    rows, _ = run_program()
    assert rows[0]["pass_tier"] == ""
    assert rows[0]["status"] == "UNMATCHED"


def test_three_sequential_corrections_consume_three_rows():
    """Three corrections against three duplicate pass_id rows should all match."""
    build_program()
    write_inputs(
        [
            ["SRC-3", "P-1", "S-3", "DAY", "9", "20260528160000", "SCANNED", "L1"],
            ["SRC-3", "P-1", "S-3", "DAY", "9", "20260528160100", "SCANNED", "L1"],
            ["SRC-3", "P-1", "S-3", "DAY", "9", "20260528160200", "SCANNED", "L1"],
        ],
        [
            ["A1", "SRC-3", "P-1", "S-3", "HR", "9", "20260528160300", "VOID", "L1"],
            ["A2", "SRC-3", "P-1", "S-3", "DAY", "9", "20260528160400", "VOID", "L1"],
            ["A3", "SRC-3", "P-1", "S-3", " hr ", "9", "20260528160500", "VOID", "L1"],
        ],
        [["S-3", "20260528155900", "20260528163000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert summary["matched_count"] == 3


def test_source_side_alias_normalizes_before_matching():
    """Session rows with HR QR CC aliases must normalize the same way as corrections."""
    build_program()
    write_inputs(
        [["SRC-S1", "P-1", "S-A", "HR", "10", "20260528120500", "SCANNED", "L1"]],
        [["ACT-S1", "SRC-S1", "P-1", "S-A", "DAY", "10", "20260528121000", "VOID", "L1"]],
        [["S-A", "20260528120000", "20260528123000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["pass_tier"] == "DAY"
    assert summary["matched_count"] == 1


def test_session_qr_alias_normalizes_before_matching():
    """Session rows storing QR must normalize to SEASON before tier checks."""
    build_program()
    write_inputs(
        [["SRC-QR", "P-1", "S-Q", "QR", "34", "20260528120600", "SCANNED", "L2"]],
        [["ACT-QR", "SRC-QR", "P-1", "S-Q", "SEASON", "34", "20260528121100", "COMP", "L2"]],
        [["S-Q", "20260528120000", "20260528123000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["pass_tier"] == "SEASON"
    assert summary["matched_count"] == 1
