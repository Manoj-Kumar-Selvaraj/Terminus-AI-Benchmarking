
"""Verifier tests for realtime lab sample chain reassignment reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
GO = Path("/usr/local/go/bin/go")
BIN = APP / "build" / "reconcile"
SOURCE = APP / "data" / "accessions.csv"
ACTION = APP / "data" / "reassignments.csv"
WINDOWS = APP / "config" / "windows.csv"
ALIASES = APP / "config" / "kind_aliases.csv"
REASONS = APP / "config" / "reasons.csv"
REPORT = APP / "out" / "reassignment_report.csv"
SUMMARY = APP / "out" / "reassignment_summary.txt"
HEADER = ["action_id", "sample_id", "patient_id", "chain_id", "kind", "amount", "reason", "matched_source_ts", "status"]


def build_program():
    """Compile the reconciler from the mutable source tree."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile/main.go"], check=True, cwd=APP)


def write_csv(path, header, rows):
    """Write a runtime CSV fixture with an explicit header so tests can replace all input rows safely."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(source, action, windows=None, aliases=None, reasons=None):
    """Install per-test runtime CSV/config fixtures and remove stale output artifacts before execution."""
    write_csv(SOURCE, ["sample_id", "patient_id", "chain_id", "kind", "amount", "source_ts", "status", "location"], source)
    write_csv(ACTION, ["action_id", "sample_id", "patient_id", "chain_id", "kind", "amount", "action_ts", "reason", "location"], action)
    write_csv(WINDOWS, ["chain_id", "open_ts", "close_ts", "state"], windows or [["S-A", "20260528120000", "20260528150000", "OPEN"], ["S-B", "20260528120000", "20260528150000", "OPEN"]])
    write_csv(ALIASES, ["alias", "canonical"], aliases or [["CMP", "CHEM"], ["CBC", "HEME"], ["CUL", "MICRO"]])
    write_csv(REASONS, ["reason", "eligible"], reasons or [["SPLIT", "Y"], ["REROUTE", "Y"], ["RECHECK", "Y"]])
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Execute the compiled reconciler and parse its observable report and key=value summary outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        summary[key] = int(value)
    return rows, summary


def report_header():
    """Return the generated report header exactly as emitted by the reconciler."""
    return REPORT.read_text().splitlines()[0].split(",")


def assert_summary_matches_rows(rows, summary):
    """Cross-check summary counters and base-10 amount totals against report rows."""
    matched = [row for row in rows if row["status"] == "MATCHED"]
    unmatched = [row for row in rows if row["status"] == "UNMATCHED"]
    assert summary["matched_count"] == len(matched)
    assert summary["unmatched_count"] == len(unmatched)
    assert summary["matched_amount"] == sum(int(row["amount"]) for row in matched if row["amount"].strip().isdigit() and int(row["amount"].strip()) > 0)
    assert summary["unmatched_amount"] == sum(int(row["amount"]) for row in unmatched if row["amount"].strip().isdigit() and int(row["amount"].strip()) > 0)


def test_m3_window_eligibility_action_close_latest_and_tie_breaking():
    """M3 enforces OPEN windows and exposes latest-source selection through matched_source_ts."""
    build_program()
    write_inputs(
        [
            ["SRC-W1", "PAT-1", "S-A", "CHEM", "10", "20260528130100", "RECEIVED", "LOC-1"],
            ["SRC-W2", "PAT-2", "S-C", "CHEM", "20", "20260528130100", "RECEIVED", "LOC-2"],
            ["SRC-W3", "PAT-3", "S-M", "HEME", "30", "bad-time", "RECEIVED", "LOC-3"],
            ["SRC-W4", "PAT-4", "S-A", "MICRO", "40", "20260528130200", "RECEIVED", "LOC-4"],
            ["SRC-DUP", "PAT-D", "S-A", "CHEM", "50", "20260528130300", "RECEIVED", "LOC-D"],
            ["SRC-DUP", "PAT-D", "S-A", "CHEM", "50", "20260528130400", "RECEIVED", "LOC-D"],
            ["SRC-TIE", "PAT-T", "S-A", "HEME", "60", "20260528130500", "RECEIVED", "LOC-T"],
            ["SRC-TIE", "PAT-T", "S-A", "HEME", "60", "20260528130500", "RECEIVED", "LOC-T"],
        ],
        [
            ["ACT-W1", "SRC-W1", "PAT-1", "S-A", "CMP", "10", "20260528130600", "SPLIT", "LOC-1"],
            ["ACT-W2", "SRC-W2", "PAT-2", "S-C", "CMP", "20", "20260528130600", "SPLIT", "LOC-2"],
            ["ACT-W3", "SRC-W3", "PAT-3", "S-M", "CBC", "30", "20260528130600", "REROUTE", "LOC-3"],
            ["ACT-W4", "SRC-W4", "PAT-4", "S-A", "CUL", "40", "20260528140101", "RECHECK", "LOC-4"],
            ["ACT-DUP", "SRC-DUP", "PAT-D", "S-A", "CHEM", "50", "20260528130600", "SPLIT", "LOC-D"],
            ["ACT-TIE", "SRC-TIE", "PAT-T", "S-A", "CBC", "60", "20260528130600", "REROUTE", "LOC-T"],
        ],
        windows=[
            ["S-A", "20260528130000", "20260528140100", "OPEN"],
            ["S-C", "20260528130000", "20260528140100", "CLOSED"],
            ["S-M", "not-a-time", "20260528140100", "OPEN"],
        ],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED", "MATCHED"]
    assert [row["matched_source_ts"] for row in rows] == ["20260528130100", "", "", "", "20260528130400", "20260528130500"]
    assert [row["kind"] for row in rows] == ["CHEM", "", "", "", "CHEM", "HEME"]
    assert summary == {"matched_count": 3, "matched_amount": 120, "unmatched_count": 3, "unmatched_amount": 90}


def test_m3_carries_aliases_exact_keys_and_consumes_sources_across_actions():
    """M3 keeps M1/M2 rules while selecting from remaining unused candidates for later actions."""
    build_program()
    write_inputs(
        [
            ["SRC-REUSE", "PAT-R", "S-B", "MICRO", "15", "20260528141000", "RECEIVED", "LOC-R"],
            ["SRC-REUSE", "PAT-R", "S-B", "MICRO", "15", "20260528141100", "RECEIVED", "LOC-R"],
            ["SRC-PREFIX-EXTRA", "PAT-P", "S-B", "CHEM", "25", "20260528141200", "RECEIVED", "LOC-P"],
            ["SRC-PREFIX", "PAT-P", "S-B", "CHEM", "25", "20260528140900", "RECEIVED", "LOC-P"],
            ["SRC-UNK", "PAT-U", "S-B", "legacy", "35", "20260528141300", "RECEIVED", "LOC-U"],
        ],
        [
            ["ACT-R1", "SRC-REUSE", "PAT-R", "S-B", "CUL", "15", "20260528142000", "SPLIT", "LOC-R"],
            ["ACT-R2", "SRC-REUSE", "PAT-R", "S-B", "CUL", "15", "20260528142000", "SPLIT", "LOC-R"],
            ["ACT-P", "SRC-PREFIX", "PAT-P", "S-B", "CMP", "25", "20260528142000", "REROUTE", "LOC-P"],
            ["ACT-U", "SRC-UNK", "PAT-U", "S-B", "legacy", "35", "20260528142000", "RECHECK", "LOC-U"],
        ],
        windows=[["S-B", "20260528140000", "20260528143000", "OPEN"]],
        aliases=[["CUL", "MICRO"], ["CMP", "CHEM"], ["legacy", "ARCHIVE"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["matched_source_ts"] for row in rows] == ["20260528141100", "20260528141000", "20260528140900", ""]
    assert [row["kind"] for row in rows] == ["MICRO", "MICRO", "CHEM", ""]
    assert summary == {"matched_count": 3, "matched_amount": 55, "unmatched_count": 1, "unmatched_amount": 35}


def test_m3_inclusive_window_boundaries_and_multiple_open_windows():
    """M3 treats window bounds inclusively and can find an eligible later OPEN window for the same chain."""
    build_program()
    write_inputs(
        [
            ["SRC-OPEN", "PAT-O", "S-W", "CHEM", "10", "20260528100000", "RECEIVED", "LOC-O"],
            ["SRC-CLOSE", "PAT-C", "S-W", "HEME", "20", "20260528110000", "RECEIVED", "LOC-C"],
            ["SRC-LATEWIN", "PAT-L", "S-W", "MICRO", "30", "20260528130500", "RECEIVED", "LOC-L"],
            ["SRC-BEFORE", "PAT-B", "S-W", "CHEM", "40", "20260528095959", "RECEIVED", "LOC-B"],
            ["SRC-AFTER", "PAT-A", "S-W", "CHEM", "50", "20260528140101", "RECEIVED", "LOC-A"],
        ],
        [
            ["ACT-OPEN", "SRC-OPEN", "PAT-O", "S-W", "CMP", "10", "20260528100000", "SPLIT", "LOC-O"],
            ["ACT-CLOSE", "SRC-CLOSE", "PAT-C", "S-W", "CBC", "20", "20260528110000", "REROUTE", "LOC-C"],
            ["ACT-LATEWIN", "SRC-LATEWIN", "PAT-L", "S-W", "CUL", "30", "20260528135959", "RECHECK", "LOC-L"],
            ["ACT-BEFORE", "SRC-BEFORE", "PAT-B", "S-W", "CHEM", "40", "20260528100000", "SPLIT", "LOC-B"],
            ["ACT-AFTER", "SRC-AFTER", "PAT-A", "S-W", "CHEM", "50", "20260528140101", "SPLIT", "LOC-A"],
        ],
        windows=[
            ["S-W", "20260528090000", "20260528093000", "CLOSED"],
            ["S-W", "20260528100000", "20260528110000", "OPEN"],
            ["S-W", "20260528130000", "20260528140000", "OPEN"],
        ],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED", "UNMATCHED"]
    assert [row["matched_source_ts"] for row in rows] == ["20260528100000", "20260528110000", "20260528130500", "", ""]
    assert summary == {"matched_count": 3, "matched_amount": 60, "unmatched_count": 2, "unmatched_amount": 90}


def test_m3_reasons_config_is_runtime_authoritative():
    """M3 must load reason eligibility from config instead of hardcoding the M1/M2 reason set."""
    build_program()
    write_inputs(
        [
            ["SRC-FOLLOW", "PAT-F", "S-R", "CHEM", "12", "20260528150000", "RECEIVED", "LOC-F"],
            ["SRC-SPLIT", "PAT-S", "S-R", "CHEM", "13", "20260528150100", "RECEIVED", "LOC-S"],
            ["SRC-LOWER", "PAT-L", "S-R", "HEME", "14", "20260528150200", "RECEIVED", "LOC-L"],
            ["SRC-MISSING", "PAT-M", "S-R", "MICRO", "15", "20260528150300", "RECEIVED", "LOC-M"],
        ],
        [
            ["ACT-FOLLOW", "SRC-FOLLOW", "PAT-F", "S-R", "CMP", "12", "20260528151000", "followup", "LOC-F"],
            ["ACT-SPLIT", "SRC-SPLIT", "PAT-S", "S-R", "CMP", "13", "20260528151000", "SPLIT", "LOC-S"],
            ["ACT-LOWER", "SRC-LOWER", "PAT-L", "S-R", "CBC", "14", "20260528151000", "recheck", "LOC-L"],
            ["ACT-MISSING", "SRC-MISSING", "PAT-M", "S-R", "CUL", "15", "20260528151000", "REROUTE", "LOC-M"],
        ],
        windows=[["S-R", "20260528145900", "20260528153000", "OPEN"]],
        reasons=[["FOLLOWUP", "Y"], ["SPLIT", "N"], ["RECHECK", "y"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED", "UNMATCHED"]
    assert [row["kind"] for row in rows] == ["CHEM", "", "HEME", ""]
    assert summary == {"matched_count": 2, "matched_amount": 26, "unmatched_count": 2, "unmatched_amount": 28}


def test_m3_rejects_unlisted_windows_malformed_close_and_action_after_close():
    """M3 rejects missing chain windows, malformed window rows, and corrections after window close."""
    build_program()
    write_inputs(
        [
            ["SRC-NOWIN", "PAT-N", "S-NONE", "CHEM", "10", "20260528160000", "RECEIVED", "LOC-N"],
            ["SRC-BADCLOSE", "PAT-B", "S-BAD", "CHEM", "20", "20260528160000", "RECEIVED", "LOC-B"],
            ["SRC-ACTCLOSE", "PAT-C", "S-CLOSE", "HEME", "30", "20260528160000", "RECEIVED", "LOC-C"],
            ["SRC-VALID", "PAT-V", "S-CLOSE", "HEME", "40", "20260528155959", "RECEIVED", "LOC-V"],
        ],
        [
            ["ACT-NOWIN", "SRC-NOWIN", "PAT-N", "S-NONE", "CHEM", "10", "20260528161000", "SPLIT", "LOC-N"],
            ["ACT-BADCLOSE", "SRC-BADCLOSE", "PAT-B", "S-BAD", "CHEM", "20", "20260528161000", "SPLIT", "LOC-B"],
            ["ACT-ACTCLOSE", "SRC-ACTCLOSE", "PAT-C", "S-CLOSE", "CBC", "30", "20260528170001", "RECHECK", "LOC-C"],
            ["ACT-VALID", "SRC-VALID", "PAT-V", "S-CLOSE", "CBC", "40", "20260528170000", "RECHECK", "LOC-V"],
        ],
        windows=[
            ["S-BAD", "20260528150000", "not-a-close", "OPEN"],
            ["S-CLOSE", "20260528150000", "20260528170000", "OPEN"],
        ],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[3]["matched_source_ts"] == "20260528155959"
    assert summary == {"matched_count": 1, "matched_amount": 40, "unmatched_count": 3, "unmatched_amount": 60}


def test_m3_runtime_outputs_remain_deterministic_after_consumption_and_reexecution():
    """M3 should not reuse stale outputs and should choose the latest remaining eligible source each run."""
    build_program()
    write_inputs(
        [
            ["SRC-SEQ", "PAT-Q", "S-Q", "CHEM", "16", "20260528172000", "RECEIVED", "LOC-Q"],
            ["SRC-SEQ", "PAT-Q", "S-Q", "CHEM", "16", "20260528172100", "RECEIVED", "LOC-Q"],
            ["SRC-SEQ", "PAT-Q", "S-Q", "CHEM", "16", "20260528172200", "RECEIVED", "LOC-Q"],
        ],
        [
            ["ACT-Q1", "SRC-SEQ", "PAT-Q", "S-Q", "CMP", "16", "20260528172500", "SPLIT", "LOC-Q"],
            ["ACT-Q2", "SRC-SEQ", "PAT-Q", "S-Q", "CMP", "16", "20260528172500", "SPLIT", "LOC-Q"],
            ["ACT-Q3", "SRC-SEQ", "PAT-Q", "S-Q", "CMP", "16", "20260528172500", "SPLIT", "LOC-Q"],
            ["ACT-Q4", "SRC-SEQ", "PAT-Q", "S-Q", "CMP", "16", "20260528172500", "SPLIT", "LOC-Q"],
        ],
        windows=[["S-Q", "20260528170000", "20260528173000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["matched_source_ts"] for row in rows] == ["20260528172200", "20260528172100", "20260528172000", ""]
    assert summary == {"matched_count": 3, "matched_amount": 48, "unmatched_count": 1, "unmatched_amount": 16}

    write_inputs(
        [["SRC-NEW", "PAT-N", "S-Q", "HEME", "17", "20260528171000", "RECEIVED", "LOC-N"]],
        [["ACT-NEW", "SRC-NEW", "PAT-N", "S-Q", "CBC", "17", "20260528171500", "RECHECK", "LOC-N"]],
        windows=[["S-Q", "20260528170000", "20260528173000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [row["action_id"] for row in rows] == ["ACT-NEW"]
    assert rows[0]["status"] == "MATCHED"
    assert "ACT-Q1" not in REPORT.read_text()
    assert summary == {"matched_count": 1, "matched_amount": 17, "unmatched_count": 0, "unmatched_amount": 0}
