"""Verifier tests for realtime telemetry incident credit reconciliation — milestone 3."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
GO = Path("/usr/local/go/bin/go")
BIN = APP / "build" / "stream-incident-reconcile"
PLAYBACKS = APP / "data" / "playbacks.csv"
CREDITS = APP / "data" / "credits.csv"
CUTOFFS = APP / "config" / "region_windows.csv"
REPORT = APP / "out" / "incident_credit_report.csv"
SUMMARY = APP / "out" / "incident_credit_summary.txt"


def build_program():
    """Compile the Go reconciler for one verifier scenario."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile/main.go"], check=True, cwd=APP, timeout=60)


def write_csv(path, header, rows):
    """Write one CSV fixture."""
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(playbacks, credits, windows):
    """Overwrite all input CSVs at runtime."""
    write_csv(PLAYBACKS, ["incident_id", "severity_id", "severity", "minutes", "start_utc", "end_utc", "status", "region"], playbacks)
    write_csv(CREDITS, ["credit_id", "incident_id", "severity_id", "severity", "minutes", "event_utc", "reason", "region"], credits)
    write_csv(CUTOFFS, ["region", "window_utc", "state"], windows)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the reconciler and parse report and summary outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        summary[key] = int(value)
    return rows, summary


def test_all_gates_and_row_consumption_are_enforced():
    """Full-id match, account, region, status, reason, severity, timestamp, window, and consumption all gate matching."""
    build_program()
    write_inputs(
        [
            ["STREAM-GATE-1", "ACCT-1", "CMEDIUM", "10", "20260528100000", "20260528101000", "POSTED", "NA"],
            ["STREAM-GATE-2", "ACCT-2", "CMEDIUM", "20", "20260528100000", "20260528102000", "DRAFT", "NA"],
            ["STREAM-GATE-3", "ACCT-3", "LOW", "30", "20260528100000", "20260528103000", "POSTED", "NA"],
            ["STREAM-GATE-4", "ACCT-4", "BAD", "40", "20260528100000", "20260528104000", "POSTED", "NA"],
            ["STREAM-GATE-5", "ACCT-5", "BROWSER", "50", "20260528100000", "20260528105000", "POSTED", "EU"],
        ],
        [
            ["CR-A", "STREAM-GATE-1", "ACCT-1", "MEDIUM", "10", "20260528101100", "BUFFER", "NA"],
            ["CR-B", "STREAM-GATE-1", "ACCT-1", "MEDIUM", "10", "20260528101200", "BUFFER", "NA"],
            ["CR-C", "STREAM-GATE-2", "ACCT-2", "MEDIUM", "20", "20260528102100", "BUFFER", "NA"],
            ["CR-D", "STREAM-GATE-3", "ACCT-X", "PHONE", "30", "20260528103100", "DUPLICATELICATE", "NA"],
            ["CR-E", "STREAM-GATE-3", "ACCT-3", "PHONE", "31", "20260528103100", "DUPLICATELICATE", "NA"],
            ["CR-F", "STREAM-GATE-3", "ACCT-3", "PHONE", "30", "20260528102959", "DUPLICATELICATE", "NA"],
            ["CR-G", "STREAM-GATE-3", "ACCT-3", "PHONE", "30", "20260528103100", "INFO", "NA"],
            ["CR-H", "STREAM-GATE-4", "ACCT-4", "BAD", "40", "20260528104100", "CREDIT", "NA"],
            ["CR-I", "STREAM-GATE-5", "ACCT-5", "WEBAPP", "50", "20260528105100", "CREDIT", "EU"],
        ],
        [["NA", "20260528235959", "OPEN"], ["EU", "20260528235959", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["severity"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_minutes"] == 60
    assert summary["unmatched_count"] == 7
    assert summary["unmatched_minutes"] == 191


def test_aliases_and_full_stream_keys_match_with_canonical_severities():
    """Severity aliases should match full stream keys and emit canonical playback severities."""
    build_program()
    write_inputs(
        [
            ["STREAM-10000001", "ACCT-1", "CMEDIUM", "45", "20260528120000", "20260528124500", "POSTED", "NA"],
            ["STREAM-10000002", "ACCT-2", "LOW", "30", "20260528130000", "20260528133000", "POSTED", "EU"],
            ["STREAM-10000003", "ACCT-3", "BROWSER", "15", "20260528140000", "20260528141500", "POSTED", "APAC"],
        ],
        [
            ["CR-1", "STREAM-10000001", "ACCT-1", "MEDIUM", "45", "20260528124600", "BUFFER", "NA"],
            ["CR-2", "STREAM-10000002", "ACCT-2", "PHONE", "30", "20260528133100", "DUPLICATELICATE", "EU"],
            ["CR-3", "STREAM-10000003", "ACCT-3", "WEBAPP", "15", "20260528141600", "CREDIT", "APAC"],
        ],
        [["NA", "20260528235959", "OPEN"], ["EU", "20260528235959", "OPEN"], ["APAC", "20260528235959", "OPEN"]],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "credit_id,incident_id,severity_id,severity,minutes,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["severity"] for row in rows] == ["CMEDIUM", "LOW", "BROWSER"]
    assert summary == {"matched_count": 3, "matched_minutes": 90, "unmatched_count": 0, "unmatched_minutes": 0}


def test_window_state_numeric_time_and_latest_end_selection():
    """Window state, malformed timestamps, expired events, and latest eligible playback selection should be enforced."""
    build_program()
    write_inputs(
        [
            ["STREAM-WIN-1", "ACCT-1", "CMEDIUM", "11", "20260528100000", "20260528101100", "POSTED", "NA"],
            ["STREAM-WIN-2", "ACCT-2", "CMEDIUM", "22", "20260528100000", "20260528102200", "POSTED", "EU"],
            ["STREAM-WIN-3", "ACCT-3", "LOW", "33", "bad-time", "20260528103300", "POSTED", "NA"],
            ["STREAM-WIN-4", "ACCT-4", "BROWSER", "44", "20260528100000", "20260528104400", "POSTED", "NA"],
            ["STREAM-DUPLICATEE", "ACCT-5", "CMEDIUM", "55", "20260528100000", "20260528105000", "POSTED", "NA"],
            ["STREAM-DUPLICATEE", "ACCT-5", "CMEDIUM", "55", "20260528100100", "20260528105500", "POSTED", "NA"],
        ],
        [
            ["CR-1", "STREAM-WIN-1", "ACCT-1", "MEDIUM", "11", "20260528101200", "BUFFER", "NA"],
            ["CR-2", "STREAM-WIN-2", "ACCT-2", "MEDIUM", "22", "20260528102300", "BUFFER", "EU"],
            ["CR-3", "STREAM-WIN-3", "ACCT-3", "PHONE", "33", "20260528103400", "DUPLICATELICATE", "NA"],
            ["CR-4", "STREAM-WIN-4", "ACCT-4", "WEBAPP", "44", "20260529000100", "CREDIT", "NA"],
            ["CR-5", "STREAM-DUPLICATEE", "ACCT-5", "MEDIUM", "55", "20260528105600", "BUFFER", "NA"],
        ],
        [["NA", "20260528235959", "OPEN"], ["EU", "20260528235959", "CLOS"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert [row["severity"] for row in rows] == ["CMEDIUM", "", "", "", "CMEDIUM"]
    assert summary["matched_minutes"] == 66
    assert summary["unmatched_minutes"] == 99


def test_latest_end_utc_beats_earlier_row_order():
    """Latest selection must leave the earlier playback available for an earlier follow-up credit."""
    build_program()
    write_inputs(
        [
            ["STREAM-TIE-1", "ACCT-1", "LOW", "20", "20260528100000", "20260528102000", "POSTED", "NA"],
            ["STREAM-TIE-1", "ACCT-1", "LOW", "20", "20260528100000", "20260528103000", "POSTED", "NA"],
        ],
        [
            ["CR-TIE-LATEST", "STREAM-TIE-1", "ACCT-1", "LOW", "20", "20260528103100", "BUFFER", "NA"],
            ["CR-TIE-EARLIER", "STREAM-TIE-1", "ACCT-1", "LOW", "20", "20260528102500", "BUFFER", "NA"],
        ],
        [["NA", "20260528235959", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["minutes"] for row in rows] == ["20", "20"]
    assert summary == {
        "matched_count": 2,
        "matched_minutes": 40,
        "unmatched_count": 0,
        "unmatched_minutes": 0,
    }


def test_closed_window_blocks_credit_even_with_matching_playback():
    """A credit whose region window is CLOSED must be UNMATCHED even when a playback matches all other gates."""
    build_program()
    write_inputs(
        [["STREAM-CLOS-1", "ACCT-1", "CMEDIUM", "30", "20260528100000", "20260528103000", "POSTED", "EU"]],
        [["CR-CLOS", "STREAM-CLOS-1", "ACCT-1", "MEDIUM", "30", "20260528103100", "BUFFER", "EU"]],
        [["EU", "20260528235959", "CLOS"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["severity"] == ""
    assert summary["matched_count"] == 0
    assert summary["unmatched_minutes"] == 30


def test_non_numeric_credit_event_utc_blocks_match():
    """A credit with a malformed event_utc must stay UNMATCHED even when a playback qualifies."""
    build_program()
    write_inputs(
        [["STREAM-BADTS-1", "ACCT-1", "CMEDIUM", "18", "20260528100000", "20260528101800", "POSTED", "NA"]],
        [["CR-BADTS", "STREAM-BADTS-1", "ACCT-1", "MEDIUM", "18", "bad-time", "BUFFER", "NA"]],
        [["NA", "20260528235959", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["severity"] == ""
    assert summary["matched_count"] == 0
    assert summary["unmatched_minutes"] == 18


def test_equal_end_utc_tie_uses_earliest_playback_input_row():
    """When end_utc ties, tied candidates must be consumed in physical playback input order."""
    build_program()
    write_inputs(
        [
            ["STREAM-EQEND-1", "ACCT-1", "LOW", "20", "20260528100000", "20260528103000", "POSTED", "NA"],
            ["STREAM-EQEND-1", "ACCT-1", "LOW", "25", "20260528100100", "20260528103000", "POSTED", "NA"],
        ],
        [
            ["CR-EQEND-A", "STREAM-EQEND-1", "ACCT-1", "PHONE", "20", "20260528103100", "BUFFER", "NA"],
            ["CR-EQEND-B", "STREAM-EQEND-1", "ACCT-1", "PHONE", "25", "20260528103200", "BUFFER", "NA"],
        ],
        [["NA", "20260528235959", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["minutes"] for row in rows] == ["20", "25"]
    assert summary == {"matched_count": 2, "matched_minutes": 45, "unmatched_count": 0, "unmatched_minutes": 0}


def test_unlisted_region_blocks_match_under_open_window_rules():
    """Credits for regions absent from region_windows.csv must stay UNMATCHED once OPEN gating applies."""
    build_program()
    write_inputs(
        [["STREAM-UNLIST-1", "ACCT-1", "CMEDIUM", "12", "20260528100000", "20260528101200", "POSTED", "LATAM"]],
        [["CR-UNLIST", "STREAM-UNLIST-1", "ACCT-1", "MEDIUM", "12", "20260528101300", "BUFFER", "LATAM"]],
        [["NA", "20260528235959", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["severity"] == ""
    assert summary["matched_count"] == 0
