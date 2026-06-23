"""Milestone 4 tests for live auction bid reversal reconciliation."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
GO = Path("/usr/local/go/bin/go")
BIN = APP / "build" / "auction-reconcile"
BIDS = APP / "data" / "bids.csv"
REVERSALS = APP / "data" / "reversals.csv"
WINDOWS = APP / "config" / "session_windows.csv"
ALIASES = APP / "config" / "channel_aliases.csv"
REASONS = APP / "config" / "reversal_reasons.csv"
REPORT = APP / "out" / "reversal_report.csv"
SUMMARY = APP / "out" / "reversal_summary.txt"
AUDIT = APP / "out" / "reversal_audit.csv"


def build_program():
    """Compile the Go reconciler for one reconciliation scenario."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile/main.go"], check=True, cwd=APP, timeout=60)


def write_csv(path, header, rows):
    """Write a CSV fixture for one scenario."""
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(bids, reversals, windows, aliases=None, reasons=None):
    """Overwrite inputs with scenario-specific fixtures."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    write_csv(BIDS, ["bid_id", "bidder_id", "session_id", "channel", "amount_cents", "event_ts", "status", "lot_id"], bids)
    write_csv(REVERSALS, ["reversal_id", "bid_id", "bidder_id", "session_id", "channel", "amount_cents", "event_ts", "reason", "lot_id"], reversals)
    write_csv(WINDOWS, ["session_id", "open_ts", "close_ts", "state"], windows)
    if aliases is not None:
        write_csv(ALIASES, ["alias", "canonical"], aliases)
    if reasons is not None:
        write_csv(REASONS, ["reason", "eligible"], reasons)
    for path in [REPORT, SUMMARY, AUDIT]:
        path.unlink(missing_ok=True)


def run_program(read_audit=False):
    """Run the reconciler and parse its output artifacts."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        summary[key] = int(value)
    if not read_audit:
        return rows, summary
    with AUDIT.open(newline="") as handle:
        audit = list(csv.DictReader(handle))
    return rows, summary, audit


def test_dynamic_alias_and_reason_configuration_controls_matching():
    """Runtime alias and reason files replace shipped hardcoded values in milestone 4."""
    build_program()
    write_inputs(
        [
            ["BID-DYN-1", "BUYER-1", "S-M4A", "ONLINE", "0000000700", "20260528100500", "ACCEPTED", "LOT-1"],
            ["BID-DYN-2", "BUYER-2", "S-M4A", "MOBILE", "0000000800", "20260528100600", "ACCEPTED", "LOT-2"],
            ["BID-DYN-3", "BUYER-3", "S-M4B", "ONSITE", "0000000900", "20260528110500", "ACCEPTED", "LOT-3"],
            ["BID-DYN-4", "BUYER-4", "S-M4B", "ONLINE", "0000000600", "20260528110600", "ACCEPTED", "LOT-4"],
        ],
        [
            ["REV-DYN-1", "BID-DYN-1", "BUYER-1", "S-M4A", "STREAM", "0000000700", "20260528101000", "RESCIND", "LOT-1"],
            ["REV-DYN-2", "BID-DYN-2", "BUYER-2", "S-M4A", "PHONE", "0000000800", "20260528101100", "CHARGEBACK", "LOT-2"],
            ["REV-DYN-3", "BID-DYN-3", "BUYER-3", "S-M4B", "WEB", "0000000900", "20260528111000", "RESCIND", "LOT-3"],
            ["REV-DYN-4", "BID-DYN-4", "BUYER-4", "S-M4B", "STREAM", "0000000600", "20260528111100", "CANCEL", "LOT-4"],
        ],
        [
            ["S-M4A", "20260528100000", "20260528103000", "OPEN"],
            ["S-M4B", "20260528110000", "20260528113000", "OPEN"],
        ],
        aliases=[["STREAM", "ONLINE"], ["PHONE", "MOBILE"], ["HALL", "ONSITE"]],
        reasons=[["RESCIND", "true"], ["CHARGEBACK", "YES"], ["CANCEL", "false"]],
    )
    rows, summary, audit = run_program(read_audit=True)

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "UNMATCHED"]
    assert [row["channel"] for row in rows] == ["ONLINE", "MOBILE", "", ""]
    assert summary == {"matched_count": 2, "matched_amount_cents": 1500, "unmatched_count": 2, "unmatched_amount_cents": 1500}
    assert REPORT.read_text().splitlines()[0] == "reversal_id,bid_id,bidder_id,session_id,channel,amount_cents,reason,status"
    assert AUDIT.read_text().splitlines()[0] == "session_id,channel,total_reversals,matched_count,unmatched_count,matched_amount_cents,unmatched_amount_cents"
    assert audit == [
        {"session_id": "S-M4A", "channel": "MOBILE", "total_reversals": "1", "matched_count": "1", "unmatched_count": "0", "matched_amount_cents": "800", "unmatched_amount_cents": "0"},
        {"session_id": "S-M4A", "channel": "ONLINE", "total_reversals": "1", "matched_count": "1", "unmatched_count": "0", "matched_amount_cents": "700", "unmatched_amount_cents": "0"},
        {"session_id": "S-M4B", "channel": "ONLINE", "total_reversals": "1", "matched_count": "0", "unmatched_count": "1", "matched_amount_cents": "0", "unmatched_amount_cents": "600"},
        {"session_id": "S-M4B", "channel": "UNKNOWN", "total_reversals": "1", "matched_count": "0", "unmatched_count": "1", "matched_amount_cents": "0", "unmatched_amount_cents": "900"},
    ]


def test_dynamic_config_trims_case_folds_and_last_alias_row_wins():
    """Configuration parsing is whitespace-tolerant, case-insensitive, and duplicate-aware."""
    build_program()
    write_inputs(
        [
            ["BID-CFG-1", "BUYER-1", "S-CFG", "MOBILE", "0000001200", "20260528120000", "ACCEPTED", "LOT-1"],
            ["BID-CFG-2", "BUYER-2", "S-CFG", "ONSITE", "0000001300", "20260528120100", "ACCEPTED", "LOT-2"],
        ],
        [
            ["REV-CFG-1", "BID-CFG-1", "BUYER-1", "S-CFG", "stream", "0000001200", "20260528120500", "rescind", "LOT-1"],
            ["REV-CFG-2", "BID-CFG-2", "BUYER-2", "S-CFG", "hall", "0000001300", "20260528120600", "voided", "LOT-2"],
        ],
        [["S-CFG", "20260528115900", "20260528123000", " open "]],
        aliases=[[" stream ", " online "], ["STREAM", "mobile"], [" hall ", " onsite "]],
        reasons=[[" rescind ", " 1 "], ["voided", "Y"]],
    )
    rows, summary, audit = run_program(read_audit=True)

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["channel"] for row in rows] == ["MOBILE", "ONSITE"]
    assert summary["matched_count"] == 2
    assert [(row["session_id"], row["channel"], row["matched_count"]) for row in audit] == [("S-CFG", "MOBILE", "1"), ("S-CFG", "ONSITE", "1")]


def test_duplicate_reason_rows_last_row_is_authoritative():
    """Duplicate reason rows in reversal_reasons.csv must use the last row as authoritative."""
    build_program()
    write_inputs(
        [
            ["BID-RSN-1", "BUYER-1", "S-R", "ONLINE", "0000001000", "20260528120000", "ACCEPTED", "LOT-1"],
            ["BID-RSN-2", "BUYER-2", "S-R", "MOBILE", "0000002000", "20260528120100", "ACCEPTED", "LOT-2"],
        ],
        [
            ["REV-ON", "BID-RSN-1", "BUYER-1", "S-R", "STREAM", "0000001000", "20260528120500", "RESCIND", "LOT-1"],
            ["REV-OFF", "BID-RSN-2", "BUYER-2", "S-R", "PHONE", "0000002000", "20260528120600", "CHARGEBACK", "LOT-2"],
        ],
        [["S-R", "20260528115900", "20260528123000", "OPEN"]],
        aliases=[["STREAM", "ONLINE"], ["PHONE", "MOBILE"]],
        reasons=[
            ["RESCIND", "true"],
            ["CHARGEBACK", "false"],
            ["RESCIND", "false"],
            ["CHARGEBACK", "YES"],
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert summary == {"matched_count": 1, "matched_amount_cents": 2000, "unmatched_count": 1, "unmatched_amount_cents": 1000}


def test_audit_grouped_counts_reconcile_with_summary_totals():
    """Audit matched and unmatched counts must sum to the summary totals."""
    build_program()
    write_inputs(
        [
            ["BID-AUD-1", "BUYER-1", "S-AUD", "ONLINE", "0000000500", "20260528120000", "ACCEPTED", "LOT-1"],
            ["BID-AUD-2", "BUYER-2", "S-AUD", "MOBILE", "0000000600", "20260528120100", "ACCEPTED", "LOT-2"],
            ["BID-AUD-3", "BUYER-3", "S-B", "ONSITE", "0000000700", "20260528130500", "ACCEPTED", "LOT-3"],
        ],
        [
            ["REV-AUD-1", "BID-AUD-1", "BUYER-1", "S-AUD", "STREAM", "0000000500", "20260528120500", "RESCIND", "LOT-1"],
            ["REV-AUD-2", "BID-AUD-2", "BUYER-2", "S-AUD", "PHONE", "0000000600", "20260528120600", "RESCIND", "LOT-2"],
            ["REV-AUD-3", "BID-AUD-3", "BUYER-3", "S-B", "HALL", "0000000700", "20260528131000", "VOIDED", "LOT-3"],
            ["REV-AUD-4", "BID-AUD-3", "BUYER-3", "S-B", "MYSTERY", "0000000700", "20260528131100", "RESCIND", "LOT-3"],
        ],
        [
            ["S-AUD", "20260528115900", "20260528123000", "OPEN"],
            ["S-B", "20260528130000", "20260528133000", "OPEN"],
        ],
        aliases=[["STREAM", "ONLINE"], ["PHONE", "MOBILE"], ["HALL", "ONSITE"]],
        reasons=[["RESCIND", "TRUE"], ["VOIDED", "Y"]],
    )
    rows, summary, audit = run_program(read_audit=True)

    assert summary["matched_count"] == 3
    assert summary["unmatched_count"] == 1
    assert sum(int(row["matched_count"]) for row in audit) == summary["matched_count"]
    assert sum(int(row["unmatched_count"]) for row in audit) == summary["unmatched_count"]
    assert sum(int(row["matched_amount_cents"]) for row in audit) == summary["matched_amount_cents"]
    assert sum(int(row["unmatched_amount_cents"]) for row in audit) == summary["unmatched_amount_cents"]


def test_audit_reconciles_with_summary_for_invalid_amounts_and_unknown_channels():
    """Audit rows include unknown channels and use zero amount for malformed refund amounts."""
    build_program()
    write_inputs(
        [["BID-AUD-1", "BUYER-1", "S-AUD", "ONLINE", "0000000500", "20260528120000", "ACCEPTED", "LOT-1"]],
        [
            ["REV-AUD-1", "BID-AUD-1", "BUYER-1", "S-AUD", "STREAM", "0000000500", "20260528120500", "RESCIND", "LOT-1"],
            ["REV-AUD-2", "BID-AUD-1", "BUYER-1", "S-AUD", "MYSTERY", "12O0", "20260528120600", "RESCIND", "LOT-1"],
        ],
        [["S-AUD", "20260528115900", "20260528123000", "OPEN"]],
        aliases=[["STREAM", "ONLINE"]],
        reasons=[["RESCIND", "TRUE"]],
    )
    rows, summary, audit = run_program(read_audit=True)

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert summary == {"matched_count": 1, "matched_amount_cents": 500, "unmatched_count": 1, "unmatched_amount_cents": 0}
    assert audit == [
        {"session_id": "S-AUD", "channel": "ONLINE", "total_reversals": "1", "matched_count": "1", "unmatched_count": "0", "matched_amount_cents": "500", "unmatched_amount_cents": "0"},
        {"session_id": "S-AUD", "channel": "UNKNOWN", "total_reversals": "1", "matched_count": "0", "unmatched_count": "1", "matched_amount_cents": "0", "unmatched_amount_cents": "0"},
    ]
