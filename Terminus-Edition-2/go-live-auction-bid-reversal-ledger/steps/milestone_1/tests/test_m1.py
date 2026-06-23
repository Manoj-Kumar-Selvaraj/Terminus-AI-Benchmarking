"""Milestone 1 tests for live auction bid reversal reconciliation."""

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


def test_every_gate_rejects_bad_candidates_and_consumes_bid_rows_once():
    """Identifier, bidder, session, lot, status, reason, channel, timestamp, and consumption all gate matching."""
    build_program()
    write_inputs(
        [
            ["BID-GATE-0001", "BUYER-1", "S-G", "ONLINE", "0000001000", "20260528140000", "ACCEPTED", "LOT-1"],
            ["BID-GATE-0002", "BUYER-2", "S-G", "ONLINE", "0000002000", "20260528140100", "PENDING", "LOT-2"],
            ["BID-GATE-0003", "BUYER-3", "S-G", "MOBILE", "0000003000", "20260528140200", "ACCEPTED", "LOT-3"],
            ["BID-GATE-0004", "BUYER-4", "S-G", "BAD", "0000004000", "20260528140300", "ACCEPTED", "LOT-4"],
            ["BID-GATE-0005", "BUYER-5", "S-G", "ONSITE", "0000005000", "20260528140400", "ACCEPTED", "LOT-5"],
        ],
        [
            ["REV-A", "BID-GATE-0001", "BUYER-1", "S-G", "ONLINE", "0000001000", "20260528140500", "CANCEL", "LOT-1"],
            ["REV-B", "BID-GATE-0001", "BUYER-1", "S-G", "ONLINE", "0000001000", "20260528140600", "CANCEL", "LOT-1"],
            ["REV-C", "BID-GATE-0002", "BUYER-2", "S-G", "ONLINE", "0000002000", "20260528140700", "CANCEL", "LOT-2"],
            ["REV-D", "BID-GATE-0003", "BUYER-X", "S-G", "MOBILE", "0000003000", "20260528140700", "FRAUD", "LOT-3"],
            ["REV-E", "BID-GATE-0003", "BUYER-3", "S-G", "MOBILE", "0000003999", "20260528140700", "FRAUD", "LOT-3"],
            ["REV-F", "BID-GATE-0003", "BUYER-3", "S-G", "MOBILE", "0000003000", "20260528135959", "FRAUD", "LOT-3"],
            ["REV-G", "BID-GATE-0003", "BUYER-3", "S-G", "MOBILE", "0000003000", "20260528140700", "INFO", "LOT-3"],
            ["REV-H", "BID-GATE-0004", "BUYER-4", "S-G", "BAD", "0000004000", "20260528140700", "VOID", "LOT-4"],
            ["REV-I", "BID-GATE-0005", "BUYER-5", "S-G", "ONSITE", "0000005000", "20260528140700", "VOID", "LOT-X"],
        ],
        [["S-G", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert rows[1]["channel"] == ""
    assert rows[8]["bid_id"] == "BID-GATE-0005"
    assert summary == {"matched_count": 1, "matched_amount_cents": 1000, "unmatched_count": 8, "unmatched_amount_cents": 24999}


def test_session_window_edge_cases_are_enforced_in_milestone_one():
    """Closed, missing, lowercase-open, malformed, and expired windows are handled in milestone 1."""
    build_program()
    write_inputs(
        [
            ["BID-WIN-1", "BUYER-1", "S-LOWER", "ONLINE", "0000000111", "20260528120000", "ACCEPTED", "LOT-1"],
            ["BID-WIN-2", "BUYER-2", "S-CLOSED", "ONLINE", "0000000222", "20260528120000", "ACCEPTED", "LOT-2"],
            ["BID-WIN-3", "BUYER-3", "S-MISSING", "MOBILE", "0000000333", "20260528120000", "ACCEPTED", "LOT-3"],
            ["BID-WIN-4", "BUYER-4", "S-BAD", "ONSITE", "0000000444", "bad-ts", "ACCEPTED", "LOT-4"],
            ["BID-WIN-5", "BUYER-5", "S-LOWER", "ONLINE", "0000000555", "20260528120500", "ACCEPTED", "LOT-5"],
        ],
        [
            ["REV-W1", "BID-WIN-1", "BUYER-1", "S-LOWER", "ONLINE", "0000000111", "20260528121000", "CANCEL", "LOT-1"],
            ["REV-W2", "BID-WIN-2", "BUYER-2", "S-CLOSED", "ONLINE", "0000000222", "20260528121000", "CANCEL", "LOT-2"],
            ["REV-W3", "BID-WIN-3", "BUYER-3", "S-MISSING", "MOBILE", "0000000333", "20260528121000", "FRAUD", "LOT-3"],
            ["REV-W4", "BID-WIN-4", "BUYER-4", "S-BAD", "ONSITE", "0000000444", "20260528121000", "VOID", "LOT-4"],
            ["REV-W5", "BID-WIN-5", "BUYER-5", "S-LOWER", "ONLINE", "0000000555", "20260528130100", "CANCEL", "LOT-5"],
        ],
        [
            ["S-LOWER", "20260528115900", "20260528123000", " open "],
            ["S-CLOSED", "20260528115900", "20260528123000", "closed"],
            ["S-BAD", "bad-open", "20260528123000", "OPEN"],
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary["matched_amount_cents"] == 111
    assert summary["unmatched_amount_cents"] == 1554


def test_first_qualifying_bid_row_is_consumed_before_later_duplicate():
    """Milestone 1 uses file-order selection before the latest-timestamp rule is introduced."""
    build_program()
    write_inputs(
        [
            ["BID-DUP", "BUYER-1", "S-D", "ONLINE", "0000001000", "20260528150000", "ACCEPTED", "LOT-1"],
            ["BID-DUP", "BUYER-1", "S-D", "ONLINE", "0000001000", "20260528150200", "ACCEPTED", "LOT-1"],
        ],
        [
            ["REV-D1", "BID-DUP", "BUYER-1", "S-D", "ONLINE", "0000001000", "20260528150300", "CANCEL", "LOT-1"],
            ["REV-D2", "BID-DUP", "BUYER-1", "S-D", "ONLINE", "0000001000", "20260528150100", "CANCEL", "LOT-1"],
        ],
        [["S-D", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert summary == {"matched_count": 1, "matched_amount_cents": 1000, "unmatched_count": 1, "unmatched_amount_cents": 1000}


def test_legacy_channel_aliases_stay_ineligible_in_milestone_one():
    """WEB, APP, and FLOOR aliases must not match before milestone 2 alias support."""
    build_program()
    write_inputs(
        [
            ["BID-WEB", "BUYER-1", "S-L", "ONLINE", "0000001000", "20260528120000", "ACCEPTED", "LOT-1"],
            ["BID-APP", "BUYER-2", "S-L", "MOBILE", "0000002000", "20260528120100", "ACCEPTED", "LOT-2"],
            ["BID-FLR", "BUYER-3", "S-L", "ONSITE", "0000003000", "20260528120200", "ACCEPTED", "LOT-3"],
        ],
        [
            ["REV-WEB", "BID-WEB", "BUYER-1", "S-L", "WEB", "0000001000", "20260528120500", "CANCEL", "LOT-1"],
            ["REV-APP", "BID-APP", "BUYER-2", "S-L", "APP", "0000002000", "20260528120600", "FRAUD", "LOT-2"],
            ["REV-FLR", "BID-FLR", "BUYER-3", "S-L", "FLOOR", "0000003000", "20260528120700", "VOID", "LOT-3"],
        ],
        [["S-L", "20260528115900", "20260528123000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert all(row["channel"] == "" for row in rows)
    assert summary == {
        "matched_count": 0,
        "matched_amount_cents": 0,
        "unmatched_count": 3,
        "unmatched_amount_cents": 6000,
    }


def test_invalid_amount_formats_stay_unmatched_and_contribute_zero_amount():
    """Malformed, signed, decimal, zero, and negative amounts are ineligible and add zero cents."""
    build_program()
    write_inputs(
        [
            ["BID-AMT-1", "BUYER-1", "S-A", "ONLINE", "0000001000", "20260528120000", "ACCEPTED", "LOT-1"],
            ["BID-AMT-2", "BUYER-2", "S-A", "ONLINE", "0000000000", "20260528120100", "ACCEPTED", "LOT-2"],
            ["BID-AMT-3", "BUYER-3", "S-A", "MOBILE", "0000000500", "20260528120200", "ACCEPTED", "LOT-3"],
        ],
        [
            ["REV-AMT-1", "BID-AMT-1", "BUYER-1", "S-A", "ONLINE", "10O0", "20260528120500", "CANCEL", "LOT-1"],
            ["REV-AMT-2", "BID-AMT-2", "BUYER-2", "S-A", "ONLINE", "0000000000", "20260528120500", "CANCEL", "LOT-2"],
            ["REV-AMT-3", "BID-AMT-3", "BUYER-3", "S-A", "MOBILE", "-000000500", "20260528120500", "FRAUD", "LOT-3"],
        ],
        [["S-A", "20260528115900", "20260528123000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary == {"matched_count": 0, "matched_amount_cents": 0, "unmatched_count": 3, "unmatched_amount_cents": 0}
