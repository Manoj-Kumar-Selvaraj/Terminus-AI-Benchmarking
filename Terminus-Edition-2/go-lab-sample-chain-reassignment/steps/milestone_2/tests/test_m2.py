
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


def test_m2_config_driven_aliases_micro_and_canonical_output():
    """M2 loads aliases from config, accepts MICRO, and emits canonical matched kind values."""
    build_program()
    write_inputs(
        [
            ["SRC-A1", "PAT-1", "S-A", "CHEM", "12", "20260528122000", "RECEIVED", "LOC-1"],
            ["SRC-A2", "PAT-2", "S-A", "blood", "34", "20260528122100", "RECEIVED", "LOC-2"],
            ["SRC-A3", "PAT-3", "S-B", "MICRO", "56", "20260528122200", "RECEIVED", "LOC-3"],
            ["SRC-A4", "PAT-4", "S-B", "BAD", "78", "20260528122300", "RECEIVED", "LOC-4"],
            ["SRC-A5", "PAT-5", "S-B", "legacy-x", "90", "20260528122400", "RECEIVED", "LOC-5"],
        ],
        [
            ["ACT-A1", "SRC-A1", "PAT-1", "S-A", "cmp", "12", "20260528122500", "SPLIT", "LOC-1"],
            ["ACT-A2", "SRC-A2", "PAT-2", "S-A", "HEME", "34", "20260528122600", "REROUTE", "LOC-2"],
            ["ACT-A3", "SRC-A3", "PAT-3", "S-B", "serology", "56", "20260528122700", "RECHECK", "LOC-3"],
            ["ACT-A4", "SRC-A4", "PAT-4", "S-B", "BAD", "78", "20260528122800", "RECHECK", "LOC-4"],
            ["ACT-A5", "SRC-A5", "PAT-5", "S-B", "legacy-x", "90", "20260528122900", "SPLIT", "LOC-5"],
        ],
        aliases=[["cmp", "chem"], ["blood", "HEME"], ["serology", "MICRO"], ["legacy-x", "ARCHIVE"]],
    )
    rows, summary = run_program()
    assert report_header() == HEADER
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED", "UNMATCHED"]
    assert [row["kind"] for row in rows] == ["CHEM", "HEME", "MICRO", "", ""]
    assert [row["matched_source_ts"] for row in rows] == ["20260528122000", "20260528122100", "20260528122200", "", ""]
    assert summary == {"matched_count": 3, "matched_amount": 102, "unmatched_count": 2, "unmatched_amount": 168}


def test_m2_carries_forward_full_identity_order_timestamp_and_consumption():
    """M2 must not regress exact matching, timestamp ordering, or one-time source consumption."""
    build_program()
    write_inputs(
        [
            ["SRC-C1", "PAT-1", "S-A", "CHEM", "10", "20260528123000", "RECEIVED", "LOC-1"],
            ["SRC-C2", "PAT-2", "S-A", "HEME", "20", "20260528123100", "RECEIVED", "LOC-2"],
            ["SRC-C3", "PAT-3", "S-A", "MICRO", "30", "20260528123200", "RECEIVED", "LOC-3"],
        ],
        [
            ["ACT-C1", "SRC-C1", "PAT-1", "S-A", "CMP", "10", "20260528123300", "SPLIT", "LOC-1"],
            ["ACT-C2", "SRC-C1", "PAT-1", "S-A", "CMP", "10", "20260528123400", "SPLIT", "LOC-1"],
            ["ACT-C3", "SRC-C2", "PAT-X", "S-A", "CBC", "20", "20260528123500", "REROUTE", "LOC-2"],
            ["ACT-C4", "SRC-C3", "PAT-3", "S-A", "CUL", "30", "20260528123159", "RECHECK", "LOC-3"],
        ],
    )
    rows, summary = run_program()
    assert [row["action_id"] for row in rows] == ["ACT-C1", "ACT-C2", "ACT-C3", "ACT-C4"]
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert rows[0]["kind"] == "CHEM"
    assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 3, "unmatched_amount": 60}


def test_m2_alias_file_is_runtime_authoritative_not_hardcoded_to_shipped_rows():
    """M2 must honor changed alias files and must not secretly accept removed shipped aliases."""
    build_program()
    write_inputs(
        [
            ["SRC-BIO", "PAT-B", "S-A", "bio", "44", "20260528124000", "RECEIVED", "LOC-B"],
            ["SRC-CMP", "PAT-C", "S-A", "CMP", "55", "20260528124100", "RECEIVED", "LOC-C"],
            ["SRC-CANON", "PAT-H", "S-A", "HEME", "66", "20260528124200", "RECEIVED", "LOC-H"],
        ],
        [
            ["ACT-BIO", "SRC-BIO", "PAT-B", "S-A", "CHEM", "44", "20260528124300", "SPLIT", "LOC-B"],
            ["ACT-CMP", "SRC-CMP", "PAT-C", "S-A", "CHEM", "55", "20260528124400", "SPLIT", "LOC-C"],
            ["ACT-CANON", "SRC-CANON", "PAT-H", "S-A", "HEME", "66", "20260528124500", "RECHECK", "LOC-H"],
        ],
        aliases=[[" bio ", " chem "]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert [row["kind"] for row in rows] == ["CHEM", "", "HEME"]
    assert summary == {"matched_count": 2, "matched_amount": 110, "unmatched_count": 1, "unmatched_amount": 55}


def test_m2_rejects_invalid_alias_targets_unknown_kinds_and_preserves_unmatched_blanks():
    """M2 rejects non-canonical alias targets and unknown kinds without leaking aliases into report rows."""
    build_program()
    write_inputs(
        [
            ["SRC-ARCH", "PAT-A", "S-B", "archive-src", "21", "20260528125000", "RECEIVED", "LOC-A"],
            ["SRC-UNK", "PAT-U", "S-B", "mystery", "22", "20260528125100", "RECEIVED", "LOC-U"],
            ["SRC-VALID", "PAT-V", "S-B", "culture", "23", "20260528125200", "RECEIVED", "LOC-V"],
        ],
        [
            ["ACT-ARCH", "SRC-ARCH", "PAT-A", "S-B", "ARCHIVE", "21", "20260528125300", "REROUTE", "LOC-A"],
            ["ACT-UNK", "SRC-UNK", "PAT-U", "S-B", "mystery", "22", "20260528125400", "REROUTE", "LOC-U"],
            ["ACT-VALID", "SRC-VALID", "PAT-V", "S-B", "MICRO", "23", "20260528125500", "REROUTE", "LOC-V"],
        ],
        aliases=[["archive-src", "ARCHIVE"], ["culture", "micro"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "MATCHED"]
    assert [row["kind"] for row in rows] == ["", "", "MICRO"]
    assert [row["matched_source_ts"] for row in rows] == ["", "", "20260528125200"]
    assert summary == {"matched_count": 1, "matched_amount": 23, "unmatched_count": 2, "unmatched_amount": 43}


def test_m2_keeps_earliest_source_selection_and_generates_clean_summary_for_mixed_rows():
    """M2 still uses M1 earliest-source selection and derives summary from generated report rows."""
    build_program()
    write_inputs(
        [
            ["SRC-MIX", "PAT-M", "S-A", "CMP", "31", "20260528130000", "RECEIVED", "LOC-M"],
            ["SRC-MIX", "PAT-M", "S-A", "CHEM", "31", "20260528125900", "RECEIVED", "LOC-M"],
            ["SRC-MISS", "PAT-X", "S-A", "CBC", "32", "20260528130100", "RECEIVED", "LOC-X"],
        ],
        [
            ["ACT-MIX", "SRC-MIX", "PAT-M", "S-A", "CHEM", "31", "20260528130200", "SPLIT", "LOC-M"],
            ["ACT-MISS", "SRC-MISS", "PAT-X", "S-A", "HEME", "32", "20260528130200", "INFO", "LOC-X"],
        ],
        aliases=[["CMP", "CHEM"], ["CBC", "HEME"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert rows[0]["matched_source_ts"] == "20260528130000"
    assert_summary_matches_rows(rows, summary)
    assert summary == {"matched_count": 1, "matched_amount": 31, "unmatched_count": 1, "unmatched_amount": 32}


def test_m2_preserves_leading_zero_amount_text_and_totals_by_parsed_value():
    """M2 preserves the correction amount string verbatim in the report while totaling by parsed value."""
    build_program()
    write_inputs(
        [["SRC-ZERO", "PAT-Z", "S-A", "CMP", "35", "20260528131000", "RECEIVED", "LOC-Z"]],
        [["ACT-ZERO", "SRC-ZERO", "PAT-Z", "S-A", "CHEM", "035", "20260528131100", "SPLIT", "LOC-Z"]],
        aliases=[["CMP", "CHEM"]],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED"]
    assert rows[0]["amount"] == "035"
    assert rows[0]["kind"] == "CHEM"
    assert summary == {"matched_count": 1, "matched_amount": 35, "unmatched_count": 0, "unmatched_amount": 0}


def test_m2_invalid_correction_amounts_do_not_match_or_contribute_to_totals():
    """M2 treats blank, signed, decimal, zero, and negative correction amounts as invalid and untotaled."""
    build_program()
    write_inputs(
        [
            ["SRC-BLANK", "PAT-1", "S-A", "CHEM", "1", "20260528132000", "RECEIVED", "LOC-1"],
            ["SRC-NEG", "PAT-2", "S-A", "CHEM", "5", "20260528132100", "RECEIVED", "LOC-2"],
            ["SRC-DEC", "PAT-3", "S-A", "CHEM", "3", "20260528132200", "RECEIVED", "LOC-3"],
            ["SRC-ZERO", "PAT-4", "S-A", "CHEM", "1", "20260528132300", "RECEIVED", "LOC-4"],
            ["SRC-SIGN", "PAT-5", "S-A", "CHEM", "12", "20260528132400", "RECEIVED", "LOC-5"],
            ["SRC-GOOD", "PAT-6", "S-A", "CHEM", "9", "20260528132500", "RECEIVED", "LOC-6"],
        ],
        [
            ["ACT-BLANK", "SRC-BLANK", "PAT-1", "S-A", "CHEM", "", "20260528133000", "SPLIT", "LOC-1"],
            ["ACT-NEG", "SRC-NEG", "PAT-2", "S-A", "CHEM", "-5", "20260528133100", "SPLIT", "LOC-2"],
            ["ACT-DEC", "SRC-DEC", "PAT-3", "S-A", "CHEM", "3.14", "20260528133200", "SPLIT", "LOC-3"],
            ["ACT-ZERO", "SRC-ZERO", "PAT-4", "S-A", "CHEM", "0", "20260528133300", "SPLIT", "LOC-4"],
            ["ACT-SIGN", "SRC-SIGN", "PAT-5", "S-A", "CHEM", "+12", "20260528133400", "SPLIT", "LOC-5"],
            ["ACT-GOOD", "SRC-GOOD", "PAT-6", "S-A", "CHEM", "9", "20260528133500", "SPLIT", "LOC-6"],
        ],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert [row["amount"] for row in rows] == ["", "-5", "3.14", "0", "+12", "9"]
    assert all(row["kind"] == "" and row["matched_source_ts"] == "" for row in rows[:5])
    assert rows[5]["kind"] == "CHEM"
    assert summary == {"matched_count": 1, "matched_amount": 9, "unmatched_count": 5, "unmatched_amount": 0}
    assert_summary_matches_rows(rows, summary)

