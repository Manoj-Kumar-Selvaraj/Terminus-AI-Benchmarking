"""Verifier tests for realtime telemetry incident credit reconciliation — milestone 1."""

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
            ["CR-A", "STREAM-GATE-1", "ACCT-1", "CMEDIUM", "10", "20260528101100", "BUFFER", "NA"],
            ["CR-B", "STREAM-GATE-1", "ACCT-1", "CMEDIUM", "10", "20260528101200", "BUFFER", "NA"],
            ["CR-C", "STREAM-GATE-2", "ACCT-2", "CMEDIUM", "20", "20260528102100", "BUFFER", "NA"],
            ["CR-D", "STREAM-GATE-3", "ACCT-X", "LOW", "30", "20260528103100", "DUPLICATELICATE", "NA"],
            ["CR-E", "STREAM-GATE-3", "ACCT-3", "LOW", "31", "20260528103100", "DUPLICATELICATE", "NA"],
            ["CR-F", "STREAM-GATE-3", "ACCT-3", "LOW", "30", "20260528102959", "DUPLICATELICATE", "NA"],
            ["CR-G", "STREAM-GATE-3", "ACCT-3", "LOW", "30", "20260528103100", "INFO", "NA"],
            ["CR-H", "STREAM-GATE-4", "ACCT-4", "BAD", "40", "20260528104100", "CREDIT", "NA"],
            ["CR-I", "STREAM-GATE-5", "ACCT-5", "BROWSER", "50", "20260528105100", "CREDIT", "APAC"],
        ],
        [["NA", "20260528235959", "OPEN"], ["EU", "20260528235959", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert rows[1]["severity"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_minutes"] == 10
    assert summary["unmatched_count"] == 8
    assert summary["unmatched_minutes"] == 241


def test_report_schema_and_order_follow_credit_input():
    """Report header and row order must follow credit input order."""
    build_program()
    write_inputs(
        [
            ["STREAM-ORD-3", "ACCT-3", "LOW", "15", "20260528130000", "20260528131500", "POSTED", "NA"],
            ["STREAM-ORD-1", "ACCT-1", "CMEDIUM", "10", "20260528110000", "20260528111000", "POSTED", "NA"],
            ["STREAM-ORD-2", "ACCT-2", "BROWSER", "20", "20260528120000", "20260528122000", "POSTED", "NA"],
        ],
        [
            ["CR-3", "STREAM-ORD-3", "ACCT-3", "LOW", "15", "20260528131600", "CREDIT", "NA"],
            ["CR-1", "STREAM-ORD-1", "ACCT-1", "CMEDIUM", "10", "20260528111100", "BUFFER", "NA"],
            ["CR-2", "STREAM-ORD-2", "ACCT-2", "BROWSER", "20", "20260528122100", "DUPLICATELICATE", "NA"],
        ],
        [["NA", "20260528235959", "OPEN"]],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "credit_id,incident_id,severity_id,severity,minutes,reason,status"
    assert [row["credit_id"] for row in rows] == ["CR-3", "CR-1", "CR-2"]
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["severity"] for row in rows] == ["LOW", "CMEDIUM", "BROWSER"]
    assert summary == {"matched_count": 3, "matched_minutes": 45, "unmatched_count": 0, "unmatched_minutes": 0}


def test_positive_summary_amounts_and_unmatched_severity_blank():
    """matched_minutes must be positive and unmatched rows must have blank severity."""
    build_program()
    write_inputs(
        [["STREAM-POS-1", "ACCT-1", "CMEDIUM", "25", "20260528100000", "20260528102500", "POSTED", "NA"]],
        [
            ["CR-OK", "STREAM-POS-1", "ACCT-1", "CMEDIUM", "25", "20260528102600", "BUFFER", "NA"],
            ["CR-NO", "STREAM-POS-1", "ACCT-1", "CMEDIUM", "25", "20260528102700", "BUFFER", "NA"],
        ],
        [["NA", "20260528235959", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "MATCHED"
    assert rows[1]["status"] == "UNMATCHED"
    assert rows[1]["severity"] == ""
    assert summary["matched_minutes"] == 25
    assert summary["unmatched_minutes"] == 25
    assert summary["matched_minutes"] > 0


def test_region_window_blocks_credit_when_event_utc_exceeds_cutoff():
    """A credit past the region window cutoff must stay UNMATCHED even when all other gates pass."""
    build_program()
    write_inputs(
        [["STREAM-WIN-1", "ACCT-1", "CMEDIUM", "15", "20260528100000", "20260528101500", "POSTED", "NA"]],
        [["CR-LATE", "STREAM-WIN-1", "ACCT-1", "CMEDIUM", "15", "20260529000100", "BUFFER", "NA"]],
        [["NA", "20260528235959", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["severity"] == ""
    assert summary["matched_count"] == 0
    assert summary["unmatched_minutes"] == 15


def test_missing_region_window_makes_credit_unmatched():
    """Credits for regions absent from region_windows.csv must not match."""
    build_program()
    write_inputs(
        [["STREAM-NOWIN-1", "ACCT-1", "LOW", "12", "20260528100000", "20260528101200", "POSTED", "APAC"]],
        [["CR-NOWIN", "STREAM-NOWIN-1", "ACCT-1", "LOW", "12", "20260528101300", "CREDIT", "APAC"]],
        [["NA", "20260528235959", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert summary["matched_count"] == 0


def test_incident_id_requires_full_match_not_prefix():
    """A credit must not match a playback that shares only a leading incident_id prefix."""
    build_program()
    write_inputs(
        [
            ["STREAM-PREFIX01", "ACCT-1", "CMEDIUM", "10", "20260528100000", "20260528101000", "POSTED", "NA"],
            ["STREAM-PREFIX02", "ACCT-1", "CMEDIUM", "10", "20260528100000", "20260528101000", "POSTED", "NA"],
        ],
        [
            ["CR-PFX-OK", "STREAM-PREFIX01", "ACCT-1", "CMEDIUM", "10", "20260528101100", "BUFFER", "NA"],
            ["CR-PFX-BAD", "STREAM-PREFIX0", "ACCT-1", "CMEDIUM", "10", "20260528101100", "BUFFER", "NA"],
        ],
        [["NA", "20260528235959", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert summary["matched_count"] == 1
    assert summary["unmatched_count"] == 1


def test_malformed_playback_start_utc_blocks_match():
    """Non-numeric playback start_utc must make the row ineligible even when other gates pass."""
    build_program()
    write_inputs(
        [["STREAM-BADSTART", "ACCT-1", "CMEDIUM", "14", "NOTVALID12345", "20260528101400", "POSTED", "NA"]],
        [["CR-BADSTART", "STREAM-BADSTART", "ACCT-1", "CMEDIUM", "14", "20260528101500", "BUFFER", "NA"]],
        [["NA", "20260528235959", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["severity"] == ""
    assert summary["matched_count"] == 0
