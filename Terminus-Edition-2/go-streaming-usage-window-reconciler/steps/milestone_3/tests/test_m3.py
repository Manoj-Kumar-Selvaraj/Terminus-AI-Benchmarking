"""Verifier tests for realtime streaming usage credit reconciliation."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
GO = Path("/usr/local/go/bin/go")
BIN = APP / "build" / "stream-usage-reconcile"
PLAYBACKS = APP / "data" / "playbacks.csv"
CREDITS = APP / "data" / "credits.csv"
CUTOFFS = APP / "config" / "region_cutoffs.csv"
REPORT = APP / "out" / "usage_credit_report.csv"
SUMMARY = APP / "out" / "usage_credit_summary.txt"


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


def write_inputs(playbacks, credits, cutoffs):
    """Overwrite all input CSVs at runtime."""
    write_csv(PLAYBACKS, ["stream_id", "account_id", "device", "minutes", "start_utc", "end_utc", "status", "region"], playbacks)
    write_csv(CREDITS, ["credit_id", "stream_id", "account_id", "device", "minutes", "event_utc", "reason", "region"], credits)
    write_csv(CUTOFFS, ["region", "cutoff_utc", "state"], cutoffs)
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
    """Account, region, status, reason, device, timestamp, amount, and row consumption should all gate matching."""
    build_program()
    write_inputs(
        [
            ["STREAM-GATE-1", "ACCT-1", "CTV", "10", "20260528100000", "20260528101000", "POSTED", "NA"],
            ["STREAM-GATE-2", "ACCT-2", "CTV", "20", "20260528100000", "20260528102000", "DRAFT", "NA"],
            ["STREAM-GATE-3", "ACCT-3", "MOBILE", "30", "20260528100000", "20260528103000", "POSTED", "NA"],
            ["STREAM-GATE-4", "ACCT-4", "BAD", "40", "20260528100000", "20260528104000", "POSTED", "NA"],
            ["STREAM-GATE-5", "ACCT-5", "BROWSER", "50", "20260528100000", "20260528105000", "POSTED", "EU"],
        ],
        [
            ["CR-A", "STREAM-GATE-1", "ACCT-1", "TV", "10", "20260528101100", "BUFFER", "NA"],
            ["CR-B", "STREAM-GATE-1", "ACCT-1", "TV", "10", "20260528101200", "BUFFER", "NA"],
            ["CR-C", "STREAM-GATE-2", "ACCT-2", "TV", "20", "20260528102100", "BUFFER", "NA"],
            ["CR-D", "STREAM-GATE-3", "ACCT-X", "PHONE", "30", "20260528103100", "DUPLICATE", "NA"],
            ["CR-E", "STREAM-GATE-3", "ACCT-3", "PHONE", "31", "20260528103100", "DUPLICATE", "NA"],
            ["CR-F", "STREAM-GATE-3", "ACCT-3", "PHONE", "30", "20260528102959", "DUPLICATE", "NA"],
            ["CR-G", "STREAM-GATE-3", "ACCT-3", "PHONE", "30", "20260528103100", "INFO", "NA"],
            ["CR-H", "STREAM-GATE-4", "ACCT-4", "BAD", "40", "20260528104100", "OUTAGE", "NA"],
            ["CR-I", "STREAM-GATE-5", "ACCT-5", "WEBAPP", "50", "20260528105100", "OUTAGE", "NA"],
        ],
        [["NA", "20260528235959", "OPEN"], ["EU", "20260528235959", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert rows[1]["device"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_minutes"] == 10
    assert summary["unmatched_count"] == 8
    assert summary["unmatched_minutes"] == 241
def test_aliases_and_full_stream_keys_match_with_canonical_devices():
    """Device aliases should match full stream keys and emit canonical playback devices."""
    build_program()
    write_inputs(
        [
            ["STREAM-10000001", "ACCT-1", "CTV", "45", "20260528120000", "20260528124500", "POSTED", "NA"],
            ["STREAM-10000002", "ACCT-2", "MOBILE", "30", "20260528130000", "20260528133000", "POSTED", "EU"],
            ["STREAM-10000003", "ACCT-3", "BROWSER", "15", "20260528140000", "20260528141500", "POSTED", "APAC"],
        ],
        [
            ["CR-1", "STREAM-10000001", "ACCT-1", "TV", "45", "20260528124600", "BUFFER", "NA"],
            ["CR-2", "STREAM-10000002", "ACCT-2", "PHONE", "30", "20260528133100", "DUPLICATE", "EU"],
            ["CR-3", "STREAM-10000003", "ACCT-3", "WEBAPP", "15", "20260528141600", "OUTAGE", "APAC"],
        ],
        [["NA", "20260528235959", "OPEN"], ["EU", "20260528235959", "OPEN"], ["APAC", "20260528235959", "OPEN"]],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "credit_id,stream_id,account_id,device,minutes,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["device"] for row in rows] == ["CTV", "MOBILE", "BROWSER"]
    assert summary == {"matched_count": 3, "matched_minutes": 90, "unmatched_count": 0, "unmatched_minutes": 0}
def test_cutoff_state_numeric_time_and_latest_end_selection():
    """Cutoff state, malformed timestamps, expired events, and latest eligible playback selection should be enforced."""
    build_program()
    write_inputs(
        [
            ["STREAM-WIN-1", "ACCT-1", "CTV", "11", "20260528100000", "20260528101100", "POSTED", "NA"],
            ["STREAM-WIN-2", "ACCT-2", "CTV", "22", "20260528100000", "20260528102200", "POSTED", "EU"],
            ["STREAM-WIN-3", "ACCT-3", "MOBILE", "33", "bad-time", "20260528103300", "POSTED", "NA"],
            ["STREAM-WIN-4", "ACCT-4", "BROWSER", "44", "20260528100000", "20260528104400", "POSTED", "NA"],
            ["STREAM-DUPE", "ACCT-5", "CTV", "55", "20260528100000", "20260528105000", "POSTED", "NA"],
            ["STREAM-DUPE", "ACCT-5", "CTV", "55", "20260528100100", "20260528105500", "POSTED", "NA"],
        ],
        [
            ["CR-1", "STREAM-WIN-1", "ACCT-1", "TV", "11", "20260528101200", "BUFFER", "NA"],
            ["CR-2", "STREAM-WIN-2", "ACCT-2", "TV", "22", "20260528102300", "BUFFER", "EU"],
            ["CR-3", "STREAM-WIN-3", "ACCT-3", "PHONE", "33", "20260528103400", "DUPLICATE", "NA"],
            ["CR-4", "STREAM-WIN-4", "ACCT-4", "WEBAPP", "44", "20260529000100", "OUTAGE", "NA"],
            ["CR-5", "STREAM-DUPE", "ACCT-5", "TV", "55", "20260528105600", "BUFFER", "NA"],
        ],
        [["NA", "20260528235959", "OPEN"], ["EU", "20260528235959", "CLOS"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert [row["device"] for row in rows] == ["CTV", "", "", "", "CTV"]
    assert summary["matched_minutes"] == 66
    assert summary["unmatched_minutes"] == 99
