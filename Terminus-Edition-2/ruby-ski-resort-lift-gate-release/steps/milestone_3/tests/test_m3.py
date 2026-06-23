"""Tests for config-driven pass_tier aliases."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "lift_sessions.csv"
ACTION = APP / "data" / "gate_releases.csv"
WINDOWS = APP / "config" / "windows.csv"
ALIASES = APP / "config" / "kind_aliases.csv"
REPORT = APP / "out" / "lift_gate_release_report.csv"
SUMMARY = APP / "out" / "lift_gate_release_summary.txt"


def build_program():
    """Prepare the reconciler for one test scenario."""
    pass


def write_csv(path, header, rows):
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_aliases(rows):
    write_csv(ALIASES, ["alias", "canonical"], rows)


def write_inputs(source, action, windows, aliases=None):
    write_csv(SOURCE, ["pass_id", "skier_id", "lift_id", "pass_tier", "amount", "scan_ts", "status", "slope"], source)
    write_csv(ACTION, ["release_id", "pass_id", "skier_id", "lift_id", "pass_tier", "amount", "release_ts", "reason", "slope"], action)
    write_csv(WINDOWS, ["lift_id", "open_ts", "close_ts", "state"], windows)
    write_aliases(aliases or [["HR", "DAY"], ["QR", "SEASON"], ["CC", "VIP"]])
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
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


def test_aliases_from_csv_emit_canonical_pass_tier():
    """kind_aliases.csv should drive HR QR CC normalization in matched rows."""
    build_program()
    write_inputs(
        [
            ["SRC-CSV-1", "P-1", "S-A", "DAY", "12", "20260528120500", "SCANNED", "L1"],
            ["SRC-CSV-2", "P-2", "S-A", "SEASON", "34", "20260528120600", "SCANNED", "L2"],
        ],
        [
            ["ACT-1", "SRC-CSV-1", "P-1", "S-A", "HR", "12", "20260528121000", "VOID", "L1"],
            ["ACT-2", "SRC-CSV-2", "P-2", "S-A", "QR", "34", "20260528121100", "COMP", "L2"],
        ],
        [["S-A", "20260528120000", "20260528123000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["pass_tier"] for row in rows] == ["DAY", "SEASON"]
    assert summary["matched_count"] == 2


def test_runtime_extra_alias_row_maps_unknown_code():
    """Runtime alias rows in kind_aliases.csv should map XX to DAY when configured."""
    build_program()
    write_inputs(
        [["SRC-XX", "P-1", "S-X", "DAY", "10", "20260528140000", "SCANNED", "L1"]],
        [["ACT-XX", "SRC-XX", "P-1", "S-X", "XX", "10", "20260528140500", "VOID", "L1"]],
        [["S-X", "20260528135900", "20260528143000", "OPEN"]],
        aliases=[["HR", "DAY"], ["QR", "SEASON"], ["CC", "VIP"], ["XX", "DAY"]],
    )
    rows, _ = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["pass_tier"] == "DAY"


def test_duplicate_alias_rows_first_wins():
    """When kind_aliases.csv lists the same alias twice, the first canonical value wins."""
    build_program()
    write_inputs(
        [["SRC-DUP-A", "P-1", "S-D", "SEASON", "20", "20260528140000", "SCANNED", "L1"]],
        [["ACT-DUP-A", "SRC-DUP-A", "P-1", "S-D", "QR", "20", "20260528140500", "VOID", "L1"]],
        [["S-D", "20260528135900", "20260528143000", "OPEN"]],
        aliases=[["QR", "DAY"], ["QR", "SEASON"]],
    )
    rows, _ = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["pass_tier"] == ""


def test_alias_resolved_correction_tier_must_match_session_tier():
    """QR resolving to SEASON must not match a VIP session row."""
    build_program()
    write_inputs(
        [["SRC-TIER", "P-1", "S-T", "VIP", "20", "20260528140000", "SCANNED", "L1"]],
        [["ACT-TIER", "SRC-TIER", "P-1", "S-T", "QR", "20", "20260528140500", "VOID", "L1"]],
        [["S-T", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, _ = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["pass_tier"] == ""


def test_alias_whitespace_trim_on_csv_columns():
    """Spaces around alias and canonical cells must still map correctly."""
    build_program()
    write_inputs(
        [["SRC-WS", "P-1", "S-W", "DAY", "11", "20260528140000", "SCANNED", "L1"]],
        [["ACT-WS", "SRC-WS", "P-1", "S-W", " hr ", "11", "20260528140500", "VOID", "L1"]],
        [["S-W", "20260528135900", "20260528143000", "OPEN"]],
        aliases=[["  hr  ", " DAY "]],
    )
    rows, _ = run_program()
    assert rows[0]["status"] == "MATCHED"


def test_unknown_alias_not_in_file_stays_unmatched():
    """ZZ is not in kind_aliases.csv and must not become match-eligible."""
    build_program()
    write_inputs(
        [["SRC-ZZ", "P-1", "S-Z", "ZZ", "15", "20260528140000", "SCANNED", "L1"]],
        [["ACT-ZZ", "SRC-ZZ", "P-1", "S-Z", "ZZ", "15", "20260528140500", "VOID", "L1"]],
        [["S-Z", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, _ = run_program()
    assert rows[0]["status"] == "UNMATCHED"


def test_full_pass_id_still_required_with_csv_aliases():
    """Prefix pass_id overlap must not match when aliases come from CSV."""
    build_program()
    write_inputs(
        [["SRC-PFX", "P-1", "S-P", "DAY", "10", "20260528140000", "SCANNED", "L1"]],
        [["ACT-PFX", "SRC-PFX-999", "P-1", "S-P", "HR", "10", "20260528140500", "VOID", "L1"]],
        [["S-P", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, _ = run_program()
    assert rows[0]["status"] == "UNMATCHED"


def test_vip_alias_cc_matches_guest_reason():
    """CC alias from CSV should allow VIP session with GUEST correction."""
    build_program()
    write_inputs(
        [["SRC-VIP", "P-1", "S-V", "VIP", "40", "20260528140000", "SCANNED", "L1"]],
        [["ACT-VIP", "SRC-VIP", "P-1", "S-V", "CC", "40", "20260528140500", "GUEST", "L1"]],
        [["S-V", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, _ = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["pass_tier"] == "VIP"


def test_report_header_exact_with_csv_aliases():
    """Report header must remain the milestone contract."""
    build_program()
    write_inputs(
        [["SRC-HDR", "P-1", "S-H", "DAY", "5", "20260528140000", "SCANNED", "L1"]],
        [["ACT-HDR", "SRC-HDR", "P-1", "S-H", "DAY", "5", "20260528140500", "VOID", "L1"]],
        [["S-H", "20260528135900", "20260528143000", "OPEN"]],
    )
    run_program()
    assert REPORT.read_text().splitlines()[0] == "release_id,pass_id,skier_id,lift_id,pass_tier,amount,reason,status"


def test_latest_scan_ts_consumption_with_csv_aliases():
    """Latest scan_ts wins and tied rows use earliest source input order."""
    build_program()
    write_inputs(
        [
            ["SRC-TIE", "P-T", "S-T", "DAY", "11", "20260528160000", "SCANNED", "L1"],
            ["SRC-TIE", "P-T", "S-T", "DAY", "11", "20260528160200", "SCANNED", "L1"],
        ],
        [
            ["ACT-T1", "SRC-TIE", "P-T", "S-T", "HR", "11", "20260528160300", "VOID", "L1"],
            ["ACT-T2", "SRC-TIE", "P-T", "S-T", "HR", "11", "20260528160100", "VOID", "L1"],
        ],
        [["S-T", "20260528155900", "20260528163000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount"] == 22
    assert summary["unmatched_amount"] == 0


def test_non_scanned_source_is_excluded():
    """Only SCANNED source rows may be consumed."""
    build_program()
    write_inputs(
        [["SRC-NS", "P-1", "S-N", "DAY", "10", "20260528140000", "PENDING", "L1"]],
        [["ACT-NS", "SRC-NS", "P-1", "S-N", "DAY", "10", "20260528140500", "VOID", "L1"]],
        [["S-N", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert summary["matched_count"] == 0


def test_invalid_reason_causes_unmatched():
    """Only VOID COMP GUEST reasons are allowed before milestone 4 config rules."""
    build_program()
    write_inputs(
        [["SRC-IR", "P-1", "S-I", "DAY", "10", "20260528140000", "SCANNED", "L1"]],
        [["ACT-IR", "SRC-IR", "P-1", "S-I", "DAY", "10", "20260528140500", "REFUND", "L1"]],
        [["S-I", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, _ = run_program()
    assert rows[0]["status"] == "UNMATCHED"


def test_summary_amounts_are_positive_in_milestone3():
    """Summary amount fields must be non-negative integers."""
    build_program()
    write_inputs(
        [["SRC-SM", "P-1", "S-S", "DAY", "10", "20260528140000", "SCANNED", "L1"]],
        [["ACT-SM", "SRC-SM", "P-1", "S-S", "DAY", "10", "20260528140500", "VOID", "L1"]],
        [["S-S", "20260528135900", "20260528143000", "OPEN"]],
    )
    _, summary = run_program()
    assert summary["matched_amount"] >= 0
    assert summary["unmatched_amount"] >= 0


def test_release_ts_before_scan_ts_is_unmatched():
    """release_ts earlier than scan_ts must stay unmatched."""
    build_program()
    write_inputs(
        [["SRC-TS", "P-1", "S-T", "DAY", "10", "20260528150000", "SCANNED", "L1"]],
        [["ACT-TS", "SRC-TS", "P-1", "S-T", "DAY", "10", "20260528145900", "VOID", "L1"]],
        [["S-T", "20260528145800", "20260528153000", "OPEN"]],
    )
    rows, _ = run_program()
    assert rows[0]["status"] == "UNMATCHED"


def test_closed_window_causes_unmatched():
    """CLOSED window rows must not allow matching."""
    build_program()
    write_inputs(
        [["SRC-CL", "P-1", "S-C", "DAY", "10", "20260528140000", "SCANNED", "L1"]],
        [["ACT-CL", "SRC-CL", "P-1", "S-C", "DAY", "10", "20260528140500", "VOID", "L1"]],
        [["S-C", "20260528135900", "20260528143000", "CLOSED"]],
    )
    rows, _ = run_program()
    assert rows[0]["status"] == "UNMATCHED"
