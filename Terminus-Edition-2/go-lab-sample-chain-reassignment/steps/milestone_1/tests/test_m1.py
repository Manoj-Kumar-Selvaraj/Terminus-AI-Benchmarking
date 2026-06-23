
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


def test_m1_exact_gates_prefix_collision_consumption_and_schema():
    """M1 rejects shortcut matches and consumes a source only once while preserving output schema."""
    build_program()
    write_inputs(
        [
            ["SRC-100-EXTRA", "PAT-1", "S-A", "CHEM", "10", "20260528120200", "RECEIVED", "LOC-1"],
            ["SRC-100", "PAT-1", "S-A", "CHEM", "10", "20260528120100", "RECEIVED", "LOC-1"],
            ["SRC-200", "PAT-2", "S-A", "HEME", "20", "20260528120300", "PENDING", "LOC-2"],
            ["SRC-300", "PAT-3", "S-A", "MICRO", "30", "20260528120400", "RECEIVED", "LOC-3"],
            ["SRC-400", "PAT-4", "S-A", "CHEM", "40", "20260528120500", "RECEIVED", "LOC-4"],
        ],
        [
            ["ACT-1", "SRC-100", "PAT-1", "S-A", "CHEM", "10", "20260528120600", "SPLIT", "LOC-1"],
            ["ACT-2", "SRC-100", "PAT-1", "S-A", "CHEM", "10", "20260528120700", "SPLIT", "LOC-1"],
            ["ACT-3", "SRC-200", "PAT-2", "S-A", "HEME", "20", "20260528120800", "REROUTE", "LOC-2"],
            ["ACT-4", "SRC-300", "PAT-3", "S-A", "MICRO", "30", "20260528120900", "RECHECK", "LOC-3"],
            ["ACT-5", "SRC-400", "PAT-4", "S-A", "CHEM", "40", "20260528120459", "SPLIT", "LOC-4"],
        ],
    )
    rows, summary = run_program()
    assert report_header() == HEADER
    assert [row["action_id"] for row in rows] == ["ACT-1", "ACT-2", "ACT-3", "ACT-4", "ACT-5"]
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert rows[0]["matched_source_ts"] == "20260528120100"
    assert rows[0]["kind"] == "CHEM"
    assert all(row["kind"] == "" and row["matched_source_ts"] == "" for row in rows[1:])
    assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 4, "unmatched_amount": 100}


def test_m1_full_identifier_amount_reason_and_earliest_source_tie():
    """M1 requires the complete identity tuple and uses earliest eligible source row when duplicated."""
    build_program()
    write_inputs(
        [
            ["SRC-DUP", "PAT-D", "S-A", "HEME", "15", "20260528121000", "RECEIVED", "LOC-D"],
            ["SRC-DUP", "PAT-D", "S-A", "HEME", "15", "20260528121100", "RECEIVED", "LOC-D"],
            ["SRC-LOC", "PAT-L", "S-A", "CHEM", "25", "20260528121200", "RECEIVED", "LOC-L"],
            ["SRC-AMT", "PAT-A", "S-A", "CHEM", "35", "20260528121300", "RECEIVED", "LOC-A"],
            ["SRC-RSN", "PAT-R", "S-A", "CHEM", "45", "20260528121400", "RECEIVED", "LOC-R"],
        ],
        [
            ["ACT-DUP", "SRC-DUP", "PAT-D", "S-A", "HEME", "15", "20260528121500", "REROUTE", "LOC-D"],
            ["ACT-LOC", "SRC-LOC", "PAT-L", "S-A", "CHEM", "25", "20260528121600", "SPLIT", "LOC-X"],
            ["ACT-AMT", "SRC-AMT", "PAT-A", "S-A", "CHEM", "035", "20260528121700", "SPLIT", "LOC-A"],
            ["ACT-RSN", "SRC-RSN", "PAT-R", "S-A", "CHEM", "45", "20260528121800", "INFO", "LOC-R"],
        ],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED", "UNMATCHED"]
    assert rows[0]["matched_source_ts"] == "20260528121000"
    assert rows[2]["amount"] == "035"
    assert summary == {"matched_count": 2, "matched_amount": 50, "unmatched_count": 2, "unmatched_amount": 70}


def test_m1_rejects_malformed_amounts_timestamps_status_and_unknown_kind_without_crashing():
    """M1 should not crash on bad runtime rows and should count only positive integer amounts."""
    build_program()
    write_inputs(
        [
            ["SRC-ZERO", "PAT-Z", "S-A", "CHEM", "0", "20260528122000", "RECEIVED", "LOC-Z"],
            ["SRC-NEG", "PAT-N", "S-A", "CHEM", "-5", "20260528122100", "RECEIVED", "LOC-N"],
            ["SRC-MAL", "PAT-M", "S-A", "CHEM", "abc", "20260528122200", "RECEIVED", "LOC-M"],
            ["SRC-BAD-SRC-TS", "PAT-S", "S-A", "CHEM", "12", "bad-time", "RECEIVED", "LOC-S"],
            ["SRC-BAD-ACT-TS", "PAT-A", "S-A", "CHEM", "13", "20260528122300", "RECEIVED", "LOC-A"],
            ["SRC-STATUS", "PAT-P", "S-A", "CHEM", "14", "20260528122400", "PENDING", "LOC-P"],
            ["SRC-KIND", "PAT-K", "S-A", "MICRO", "15", "20260528122500", "RECEIVED", "LOC-K"],
        ],
        [
            ["ACT-ZERO", "SRC-ZERO", "PAT-Z", "S-A", "CHEM", "0", "20260528123000", "SPLIT", "LOC-Z"],
            ["ACT-NEG", "SRC-NEG", "PAT-N", "S-A", "CHEM", "-5", "20260528123000", "SPLIT", "LOC-N"],
            ["ACT-MAL", "SRC-MAL", "PAT-M", "S-A", "CHEM", "abc", "20260528123000", "SPLIT", "LOC-M"],
            ["ACT-BAD-SRC-TS", "SRC-BAD-SRC-TS", "PAT-S", "S-A", "CHEM", "12", "20260528123000", "SPLIT", "LOC-S"],
            ["ACT-BAD-ACT-TS", "SRC-BAD-ACT-TS", "PAT-A", "S-A", "CHEM", "13", "bad-action", "SPLIT", "LOC-A"],
            ["ACT-STATUS", "SRC-STATUS", "PAT-P", "S-A", "CHEM", "14", "20260528123000", "SPLIT", "LOC-P"],
            ["ACT-KIND", "SRC-KIND", "PAT-K", "S-A", "MICRO", "15", "20260528123000", "RECHECK", "LOC-K"],
        ],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED"] * 7
    assert all(row["kind"] == "" and row["matched_source_ts"] == "" for row in rows)
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 7, "unmatched_amount": 54}


def test_m1_trims_fields_and_matches_amounts_after_base10_parsing():
    """M1 trims CSV fields and compares amounts as parsed positive integers, not raw strings."""
    build_program()
    write_inputs(
        [
            ["  SRC-TRIM  ", " PAT-T ", " S-A ", " CHEM ", " 0018 ", " 20260528123100 ", " RECEIVED ", " LOC-T "],
            ["SRC-CASE", "PAT-C", "S-A", "chem", "19", "20260528123200", "RECEIVED", "LOC-C"],
        ],
        [
            [" ACT-TRIM ", " SRC-TRIM ", " PAT-T ", " S-A ", " CHEM ", "18", " 20260528123300 ", " SPLIT ", " LOC-T "],
            ["ACT-CASE", "SRC-CASE", "PAT-C", "S-A", "CHEM", "19", "20260528123400", "SPLIT", "LOC-C"],
        ],
    )
    rows, summary = run_program()
    assert [row["action_id"] for row in rows] == ["ACT-TRIM", "ACT-CASE"]
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["kind"] for row in rows] == ["CHEM", "CHEM"]
    assert summary == {"matched_count": 2, "matched_amount": 37, "unmatched_count": 0, "unmatched_amount": 0}


def test_m1_outputs_are_regenerated_for_changed_runtime_inputs():
    """M1 must generate outputs from current inputs rather than preserving stale fixture artifacts."""
    build_program()
    write_inputs(
        [["SRC-FIRST", "PAT-1", "S-A", "CHEM", "11", "20260528124000", "RECEIVED", "LOC-1"]],
        [["ACT-FIRST", "SRC-FIRST", "PAT-1", "S-A", "CHEM", "11", "20260528124100", "SPLIT", "LOC-1"]],
    )
    first_rows, first_summary = run_program()
    assert first_rows[0]["action_id"] == "ACT-FIRST"
    assert first_summary == {"matched_count": 1, "matched_amount": 11, "unmatched_count": 0, "unmatched_amount": 0}

    write_inputs(
        [["SRC-SECOND", "PAT-2", "S-A", "HEME", "22", "20260528124200", "RECEIVED", "LOC-2"]],
        [["ACT-SECOND", "SRC-SECOND", "PAT-2", "S-A", "HEME", "22", "20260528124159", "SPLIT", "LOC-2"]],
    )
    rows, summary = run_program()
    assert [row["action_id"] for row in rows] == ["ACT-SECOND"]
    assert rows[0]["status"] == "UNMATCHED"
    assert "ACT-FIRST" not in REPORT.read_text()
    assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 22}


def test_m1_patient_id_and_chain_id_are_independent_identity_gates():
    """M1 rejects rows where only patient_id or only chain_id differs while every other gate passes."""
    build_program()
    write_inputs(
        [
            ["SRC-PID", "PAT-X", "S-A", "CHEM", "50", "20260528121000", "RECEIVED", "LOC-1"],
            ["SRC-CID", "PAT-C", "S-A", "CHEM", "60", "20260528121100", "RECEIVED", "LOC-1"],
            ["SRC-OK", "PAT-OK", "S-B", "HEME", "70", "20260528121200", "RECEIVED", "LOC-2"],
        ],
        [
            ["ACT-PID", "SRC-PID", "PAT-Y", "S-A", "CHEM", "50", "20260528121300", "SPLIT", "LOC-1"],
            ["ACT-CID", "SRC-CID", "PAT-C", "S-B", "CHEM", "60", "20260528121400", "SPLIT", "LOC-1"],
            ["ACT-OK", "SRC-OK", "PAT-OK", "S-B", "HEME", "70", "20260528121500", "RECHECK", "LOC-2"],
        ],
    )
    rows, summary = run_program()
    assert [row["action_id"] for row in rows] == ["ACT-PID", "ACT-CID", "ACT-OK"]
    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[0]["kind"] == rows[0]["matched_source_ts"] == ""
    assert rows[1]["kind"] == rows[1]["matched_source_ts"] == ""
    assert rows[2]["kind"] == "HEME"
    assert summary == {"matched_count": 1, "matched_amount": 70, "unmatched_count": 2, "unmatched_amount": 110}

