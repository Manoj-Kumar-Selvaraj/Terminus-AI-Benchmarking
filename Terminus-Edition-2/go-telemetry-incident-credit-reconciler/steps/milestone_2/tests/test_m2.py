"""Verifier tests for realtime telemetry incident credit reconciliation — milestone 2."""

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
    """Severity aliases should normalize to canonical values and matched rows emit canonical playback severity."""
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


def test_alias_normalization_applies_to_playback_side_too():
    """Playback severity aliases should also be normalized before comparison."""
    build_program()
    write_inputs(
        [
            ["STREAM-PB-ALIAS-1", "ACCT-1", "MEDIUM", "20", "20260528100000", "20260528102000", "POSTED", "NA"],
            ["STREAM-PB-ALIAS-2", "ACCT-2", "PHONE", "35", "20260528100000", "20260528103500", "POSTED", "NA"],
        ],
        [
            ["CR-PB-1", "STREAM-PB-ALIAS-1", "ACCT-1", "CMEDIUM", "20", "20260528102100", "BUFFER", "NA"],
            ["CR-PB-2", "STREAM-PB-ALIAS-2", "ACCT-2", "LOW", "35", "20260528103600", "CREDIT", "NA"],
        ],
        [["NA", "20260528235959", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["severity"] for row in rows] == ["CMEDIUM", "LOW"]
    assert summary["matched_minutes"] == 55


def test_aliases_trim_and_case_fold_on_both_sides():
    """Whitespace-padded mixed-case aliases must normalize on playbacks and credits."""
    build_program()
    write_inputs(
        [
            ["STREAM-TRIM-1", "ACCT-1", " medium ", "14", "20260528100000", "20260528101400", "POSTED", "NA"],
            ["STREAM-TRIM-2", "ACCT-2", " phone ", "16", "20260528100000", "20260528101600", "POSTED", "NA"],
            ["STREAM-TRIM-3", "ACCT-3", " webapp ", "18", "20260528100000", "20260528101800", "POSTED", "NA"],
        ],
        [
            ["CR-TRIM-1", "STREAM-TRIM-1", "ACCT-1", " cmedium ", "14", "20260528101500", "BUFFER", "NA"],
            ["CR-TRIM-2", "STREAM-TRIM-2", "ACCT-2", " low ", "16", "20260528101700", "CREDIT", "NA"],
            ["CR-TRIM-3", "STREAM-TRIM-3", "ACCT-3", " browser ", "18", "20260528101900", "BUFFER", "NA"],
        ],
        [["NA", "20260528235959", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["severity"] for row in rows] == ["CMEDIUM", "LOW", "BROWSER"]
    assert summary == {
        "matched_count": 3,
        "matched_minutes": 48,
        "unmatched_count": 0,
        "unmatched_minutes": 0,
    }


def test_unknown_severity_stays_unmatched():
    """Unknown severity on either side leaves that row unmatched regardless of other fields."""
    build_program()
    write_inputs(
        [
            ["STREAM-UNK-1", "ACCT-1", "CRITICAL", "10", "20260528100000", "20260528101000", "POSTED", "NA"],
            ["STREAM-UNK-2", "ACCT-2", "CMEDIUM", "10", "20260528100000", "20260528101000", "POSTED", "NA"],
        ],
        [
            ["CR-UNK-1", "STREAM-UNK-1", "ACCT-1", "CRITICAL", "10", "20260528101100", "BUFFER", "NA"],
            ["CR-UNK-2", "STREAM-UNK-2", "ACCT-2", "EXTREME", "10", "20260528101100", "BUFFER", "NA"],
        ],
        [["NA", "20260528235959", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
    assert summary["matched_count"] == 0
    assert summary["unmatched_minutes"] == 20
