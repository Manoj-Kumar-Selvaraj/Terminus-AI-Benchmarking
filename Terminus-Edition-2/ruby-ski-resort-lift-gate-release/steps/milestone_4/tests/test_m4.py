"""Tests for reason config, tier matrix, overlapping windows, and audit output."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "lift_sessions.csv"
ACTION = APP / "data" / "gate_releases.csv"
WINDOWS = APP / "config" / "windows.csv"
ALIASES = APP / "config" / "kind_aliases.csv"
REASONS = APP / "config" / "reasons.csv"
REASON_TIERS = APP / "config" / "reason_tiers.csv"
REPORT = APP / "out" / "lift_gate_release_report.csv"
SUMMARY = APP / "out" / "lift_gate_release_summary.txt"
AUDIT = APP / "out" / "lift_gate_release_audit.csv"


def build_program():
    pass


def write_csv(path, header, rows):
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_aliases(rows):
    write_csv(ALIASES, ["alias", "canonical"], rows)


def write_reasons(rows):
    write_csv(REASONS, ["reason", "eligible"], rows)


def write_reason_tiers(rows):
    write_csv(REASON_TIERS, ["reason", "pass_tiers"], rows)


def write_inputs(source, action, windows, aliases=None, reasons=None, tiers=None):
    write_csv(SOURCE, ["pass_id", "skier_id", "lift_id", "pass_tier", "amount", "scan_ts", "status", "slope"], source)
    write_csv(ACTION, ["release_id", "pass_id", "skier_id", "lift_id", "pass_tier", "amount", "release_ts", "reason", "slope"], action)
    write_csv(WINDOWS, ["lift_id", "open_ts", "close_ts", "state"], windows)
    write_aliases(aliases or [["HR", "DAY"], ["QR", "SEASON"], ["CC", "VIP"]])
    write_reasons(reasons or [["VOID", "Y"], ["COMP", "Y"], ["GUEST", "Y"]])
    write_reason_tiers(tiers or [["VOID", "DAY|SEASON|VIP"], ["COMP", "DAY|SEASON"], ["GUEST", "VIP"]])
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    for path in (REPORT, SUMMARY, AUDIT):
        path.unlink(missing_ok=True)


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
    audit = []
    if AUDIT.exists():
        with AUDIT.open(newline="") as handle:
            audit = list(csv.DictReader(handle))
    return rows, summary, audit


def test_reason_info_ineligible_from_csv():
    """INFO with eligible N in reasons.csv must reject with REASON_INELIGIBLE."""
    build_program()
    write_inputs(
        [["SRC-INFO", "P-1", "S-I", "DAY", "10", "20260528140000", "SCANNED", "L1"]],
        [["ACT-INFO", "SRC-INFO", "P-1", "S-I", "DAY", "10", "20260528140500", "INFO", "L1"]],
        [["S-I", "20260528135900", "20260528143000", "OPEN"]],
        reasons=[["VOID", "Y"], ["COMP", "Y"], ["GUEST", "Y"], ["INFO", "N"]],
    )
    rows, _, audit = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert audit == [{"release_id": "ACT-INFO", "reject_code": "REASON_INELIGIBLE"}]


def test_reason_void_lowercase_eligible_y():
    """eligible y after trim and case fold should allow VOID corrections."""
    build_program()
    write_inputs(
        [["SRC-VOID", "P-1", "S-V", "DAY", "12", "20260528140000", "SCANNED", "L1"]],
        [["ACT-VOID", "SRC-VOID", "P-1", "S-V", "DAY", "12", "20260528140500", "void", "L1"]],
        [["S-V", "20260528135900", "20260528143000", "OPEN"]],
        reasons=[["VOID", "y"], ["COMP", "Y"], ["GUEST", "Y"]],
    )
    rows, summary, audit = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert summary["matched_count"] == 1
    assert audit == []


def test_guest_on_day_tier_gets_tier_reason():
    """GUEST is VIP-only in reason_tiers.csv and must emit TIER_REASON on DAY sessions."""
    build_program()
    write_inputs(
        [["SRC-GDAY", "P-1", "S-G", "DAY", "15", "20260528140000", "SCANNED", "L1"]],
        [["ACT-GDAY", "SRC-GDAY", "P-1", "S-G", "DAY", "15", "20260528140500", "GUEST", "L1"]],
        [["S-G", "20260528135900", "20260528143000", "OPEN"]],
    )
    _, _, audit = run_program()
    assert audit[0]["reject_code"] == "TIER_REASON"


def test_overlapping_windows_requires_scan_on_or_after_open_ts():
    """scan_ts before the later-open window must still match via the wider earlier-open window."""
    build_program()
    write_inputs(
        [["SRC-OV1", "P-1", "S-O", "DAY", "20", "20260528139500", "SCANNED", "L1"]],
        [["ACT-OV1", "SRC-OV1", "P-1", "S-O", "DAY", "20", "20260528140500", "VOID", "L1"]],
        [
            ["S-O", "20260528120000", "20260528180000", "OPEN"],
            ["S-O", "20260528140000", "20260528150000", "OPEN"],
        ],
    )
    rows, _, _ = run_program()
    assert rows[0]["status"] == "MATCHED"


def test_release_after_tight_close_requires_wider_window():
    """release_ts after the earliest-close window must still match when a wider window qualifies."""
    build_program()
    write_inputs(
        [["SRC-OV2", "P-1", "S-O", "DAY", "20", "20260528141000", "SCANNED", "L1"]],
        [["ACT-OV2", "SRC-OV2", "P-1", "S-O", "DAY", "20", "20260528151000", "VOID", "L1"]],
        [
            ["S-O", "20260528120000", "20260528180000", "OPEN"],
            ["S-O", "20260528140000", "20260528150000", "OPEN"],
        ],
    )
    rows, _, _ = run_program()
    assert rows[0]["status"] == "MATCHED"


def test_overlap_tie_release_between_closes_only_fits_wider_window():
    """When open_ts ties, release_ts between close values must reject the earliest-close window."""
    build_program()
    write_inputs(
        [["SRC-TC", "P-1", "S-T", "DAY", "18", "20260528140500", "SCANNED", "L1"]],
        [["ACT-TC", "SRC-TC", "P-1", "S-T", "DAY", "18", "20260528150500", "VOID", "L1"]],
        [
            ["S-T", "20260528140000", "20260528160000", "OPEN"],
            ["S-T", "20260528140000", "20260528150000", "OPEN"],
        ],
    )
    rows, _, _ = run_program()
    assert rows[0]["status"] == "MATCHED"


def test_release_after_tight_close_matches_in_wider_window():
    """Release_ts after a tight window close but inside the wider overlapping OPEN window must match."""
    build_program()
    write_inputs(
        [["SRC-WIDE", "P-1", "S-W", "DAY", "22", "20260528140500", "SCANNED", "L1"]],
        [["ACT-WIDE", "SRC-WIDE", "P-1", "S-W", "DAY", "22", "20260528151000", "VOID", "L1"]],
        [
            ["S-W", "20260528140000", "20260528143000", "OPEN"],
            ["S-W", "20260528120000", "20260528180000", "OPEN"],
        ],
    )
    rows, _, _ = run_program()
    assert rows[0]["status"] == "MATCHED"


def test_release_before_scan_is_window_reject():
    """release_ts before scan_ts should yield WINDOW when identity and tier pass."""
    build_program()
    write_inputs(
        [["SRC-EARLY", "P-1", "S-E", "DAY", "10", "20260528150000", "SCANNED", "L1"]],
        [["ACT-EARLY", "SRC-EARLY", "P-1", "S-E", "DAY", "10", "20260528145900", "VOID", "L1"]],
        [["S-E", "20260528145800", "20260528153000", "OPEN"]],
    )
    _, _, audit = run_program()
    assert audit[0]["reject_code"] == "WINDOW"


def test_no_candidate_wrong_amount():
    """Mismatched amount with valid reason should use NO_CANDIDATE."""
    build_program()
    write_inputs(
        [["SRC-NC", "P-1", "S-N", "DAY", "10", "20260528140000", "SCANNED", "L1"]],
        [["ACT-NC", "SRC-NC", "P-1", "S-N", "DAY", "11", "20260528140500", "VOID", "L1"]],
        [["S-N", "20260528135900", "20260528143000", "OPEN"]],
    )
    _, _, audit = run_program()
    assert audit[0]["reject_code"] == "NO_CANDIDATE"


def test_audit_header_and_only_unmatched_rows():
    """Audit CSV must list unmatched releases only with exact header."""
    build_program()
    write_inputs(
        [
            ["SRC-A1", "P-1", "S-A", "DAY", "10", "20260528140000", "SCANNED", "L1"],
            ["SRC-A2", "P-2", "S-A", "DAY", "20", "20260528140100", "SCANNED", "L2"],
        ],
        [
            ["ACT-OK", "SRC-A1", "P-1", "S-A", "DAY", "10", "20260528140500", "VOID", "L1"],
            ["ACT-BAD", "SRC-A2", "P-2", "S-A", "DAY", "21", "20260528140600", "VOID", "L2"],
        ],
        [["S-A", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, _, audit = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[1]["status"] == "UNMATCHED"
    assert AUDIT.read_text().splitlines()[0] == "release_id,reject_code"
    assert len(audit) == 1
    assert audit[0]["release_id"] == "ACT-BAD"


def test_non_numeric_release_timestamp_window_reject():
    """Non-numeric release_ts must stay unmatched with WINDOW when tier and identity align."""
    build_program()
    write_inputs(
        [["SRC-BTS", "P-1", "S-B", "VIP", "15", "20260528140000", "SCANNED", "L1"]],
        [["ACT-BTS", "SRC-BTS", "P-1", "S-B", "CC", "15", "bad-ts", "VOID", "L1"]],
        [["S-B", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, _, audit = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert audit[0]["reject_code"] == "WINDOW"


def test_comp_allowed_on_season_not_guest():
    """COMP should match SEASON but GUEST on SEASON should be TIER_REASON."""
    build_program()
    write_inputs(
        [
            ["SRC-C1", "P-1", "S-C", "SEASON", "30", "20260528140000", "SCANNED", "L1"],
            ["SRC-C2", "P-2", "S-C", "SEASON", "40", "20260528140100", "SCANNED", "L2"],
        ],
        [
            ["ACT-COMP", "SRC-C1", "P-1", "S-C", "QR", "30", "20260528140500", "COMP", "L1"],
            ["ACT-GST", "SRC-C2", "P-2", "S-C", "SEASON", "40", "20260528140600", "GUEST", "L2"],
        ],
        [["S-C", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, _, audit = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[1]["status"] == "UNMATCHED"
    assert audit[0]["reject_code"] == "TIER_REASON"


def test_full_regression_alias_reason_overlap():
    """Combined alias file, reasons.csv, tiers, and overlapping windows."""
    build_program()
    write_inputs(
        [["SRC-FULL", "P-1", "S-F", "VIP", "50", "20260528141000", "SCANNED", "L1"]],
        [["ACT-FULL", "SRC-FULL", "P-1", "S-F", "CC", "50", "20260528142000", "GUEST", "L1"]],
        [
            ["S-F", "20260528120000", "20260528180000", "OPEN"],
            ["S-F", "20260528140000", "20260528150000", "OPEN"],
        ],
    )
    rows, summary, audit = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["pass_tier"] == "VIP"
    assert summary["matched_amount"] == 50
    assert audit == []


def test_report_and_summary_schema_milestone4():
    """Milestone 4 must preserve report header and summary keys."""
    build_program()
    write_inputs(
        [["SRC-SCH", "P-1", "S-S", "DAY", "7", "20260528140000", "SCANNED", "L1"]],
        [["ACT-SCH", "SRC-SCH", "P-1", "S-S", "DAY", "7", "20260528140500", "VOID", "L1"]],
        [["S-S", "20260528135900", "20260528143000", "OPEN"]],
    )
    _, summary, _ = run_program()
    assert REPORT.read_text().splitlines()[0] == "release_id,pass_id,skier_id,lift_id,pass_tier,amount,reason,status"
    assert set(summary.keys()) == {
        "matched_count",
        "matched_amount",
        "unmatched_count",
        "unmatched_amount",
    }


def test_closed_window_overlap_still_rejects():
    """CLOSED rows in windows.csv must not be selected even when times overlap."""
    build_program()
    write_inputs(
        [["SRC-CL", "P-1", "S-C", "DAY", "10", "20260528141000", "SCANNED", "L1"]],
        [["ACT-CL", "SRC-CL", "P-1", "S-C", "DAY", "10", "20260528142000", "VOID", "L1"]],
        [
            ["S-C", "20260528140000", "20260528150000", "CLOSED"],
            ["S-C", "20260528120000", "20260528180000", "OPEN"],
        ],
    )
    rows, _, _ = run_program()
    assert rows[0]["status"] == "MATCHED"


def test_audit_order_follows_correction_input():
    """Audit rows must follow gate_releases.csv order for multiple unmatched corrections."""
    build_program()
    write_inputs(
        [["SRC-ORD", "P-1", "S-O", "DAY", "10", "20260528140000", "SCANNED", "L1"]],
        [
            ["ACT-1", "SRC-ORD", "P-1", "S-O", "DAY", "10", "20260528140500", "INFO", "L1"],
            ["ACT-2", "SRC-ORD", "P-1", "S-O", "DAY", "10", "20260528140500", "GUEST", "L1"],
        ],
        [["S-O", "20260528135900", "20260528143000", "OPEN"]],
        reasons=[["VOID", "Y"], ["COMP", "Y"], ["GUEST", "Y"], ["INFO", "N"]],
    )
    _, _, audit = run_program()
    assert [row["release_id"] for row in audit] == ["ACT-1", "ACT-2"]
    assert audit[0]["reject_code"] == "REASON_INELIGIBLE"
    assert audit[1]["reject_code"] == "TIER_REASON"


def test_summary_amounts_are_positive_in_milestone4():
    """Summary totals must remain non-negative integers under milestone 4 rules."""
    build_program()
    write_inputs(
        [["SRC-S4", "P-1", "S-S", "DAY", "10", "20260528140000", "SCANNED", "L1"]],
        [["ACT-S4", "SRC-S4", "P-1", "S-S", "DAY", "10", "20260528140500", "VOID", "L1"]],
        [["S-S", "20260528135900", "20260528143000", "OPEN"]],
    )
    _, summary, _ = run_program()
    assert summary["matched_amount"] >= 0
    assert summary["unmatched_amount"] >= 0
    assert summary["matched_count"] == 1
