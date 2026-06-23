"""Milestone 3 tests for live auction bid reversal reconciliation."""

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
            ["REV-A", "BID-GATE-0001", "BUYER-1", "S-G", "WEB", "0000001000", "20260528140500", "CANCEL", "LOT-1"],
            ["REV-B", "BID-GATE-0001", "BUYER-1", "S-G", "WEB", "0000001000", "20260528140600", "CANCEL", "LOT-1"],
            ["REV-C", "BID-GATE-0002", "BUYER-2", "S-G", "WEB", "0000002000", "20260528140700", "CANCEL", "LOT-2"],
            ["REV-D", "BID-GATE-0003", "BUYER-X", "S-G", "APP", "0000003000", "20260528140700", "FRAUD", "LOT-3"],
            ["REV-E", "BID-GATE-0003", "BUYER-3", "S-G", "APP", "0000003999", "20260528140700", "FRAUD", "LOT-3"],
            ["REV-F", "BID-GATE-0003", "BUYER-3", "S-G", "APP", "0000003000", "20260528135959", "FRAUD", "LOT-3"],
            ["REV-G", "BID-GATE-0003", "BUYER-3", "S-G", "APP", "0000003000", "20260528140700", "INFO", "LOT-3"],
            ["REV-H", "BID-GATE-0004", "BUYER-4", "S-G", "BAD", "0000004000", "20260528140700", "VOID", "LOT-4"],
            ["REV-I", "BID-GATE-0005", "BUYER-5", "S-G", "FLOOR", "0000005000", "20260528140700", "VOID", "LOT-X"],
        ],
        [["S-G", "20260528135900", "20260528143000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert rows[1]["channel"] == ""
    assert rows[8]["bid_id"] == "BID-GATE-0005"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 1000
    assert summary["unmatched_count"] == 8
    assert summary["unmatched_amount_cents"] == 24999


def test_aliases_match_full_keys_and_emit_canonical_channels():
    """Channel aliases should match full bid keys and emit canonical bid channels."""
    build_program()
    write_inputs(
        [
            ["BID-100000001", "BUYER-1", "S-A", "ONLINE", "0000001200", "20260528120500", "ACCEPTED", "LOT-1"],
            ["BID-100000002", "BUYER-2", "S-A", "MOBILE", "0000003400", "20260528120600", "ACCEPTED", "LOT-2"],
            ["BID-100000003", "BUYER-3", "S-B", "ONSITE", "0000005600", "20260528130500", "ACCEPTED", "LOT-3"],
        ],
        [
            ["REV-1", "BID-100000001", "BUYER-1", "S-A", " web ", "0000001200", "20260528121000", "CANCEL", "LOT-1"],
            ["REV-2", "BID-100000002", "BUYER-2", "S-A", "app", "0000003400", "20260528121100", "FRAUD", "LOT-2"],
            ["REV-3", "BID-100000003", "BUYER-3", "S-B", "FLOOR", "0000005600", "20260528131000", "VOID", "LOT-3"],
        ],
        [
            ["S-A", "20260528120000", "20260528123000", "OPEN"],
            ["S-B", "20260528130000", "20260528133000", "OPEN"],
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "reversal_id,bid_id,bidder_id,session_id,channel,amount_cents,reason,status"
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["channel"] for row in rows] == ["ONLINE", "MOBILE", "ONSITE"]
    assert [row["amount_cents"] for row in rows] == ["0000001200", "0000003400", "0000005600"]
    assert summary == {"matched_count": 3, "matched_amount_cents": 10200, "unmatched_count": 0, "unmatched_amount_cents": 0}


def test_alias_mismatch_after_canonicalization_stays_unmatched():
    """A known alias cannot bypass canonical channel equality."""
    build_program()
    write_inputs(
        [["BID-X", "BUYER-1", "S-X", "ONLINE", "0000001000", "20260528120000", "ACCEPTED", "LOT-1"]],
        [["REV-X", "BID-X", "BUYER-1", "S-X", "APP", "0000001000", "20260528120500", "CANCEL", "LOT-1"]],
        [["S-X", "20260528115900", "20260528123000", "OPEN"]],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["channel"] == ""
    assert summary == {"matched_count": 0, "matched_amount_cents": 0, "unmatched_count": 1, "unmatched_amount_cents": 1000}


def test_session_window_state_and_close_time_are_enforced():
    """Closed, missing, malformed, lowercase-open, and expired windows should not match."""
    build_program()
    write_inputs(
        [
            ["BID-WIN-0001", "BUYER-1", "S-OPEN", "ONLINE", "0000001111", "20260528150000", "ACCEPTED", "LOT-1"],
            ["BID-WIN-0002", "BUYER-2", "S-CLOSED", "ONLINE", "0000002222", "20260528150000", "ACCEPTED", "LOT-2"],
            ["BID-WIN-0003", "BUYER-3", "S-MISSING", "MOBILE", "0000003333", "20260528150000", "ACCEPTED", "LOT-3"],
            ["BID-WIN-0004", "BUYER-4", "S-BAD", "ONSITE", "0000004444", "bad-time", "ACCEPTED", "LOT-4"],
            ["BID-WIN-0005", "BUYER-5", "S-OPEN", "ONLINE", "0000005555", "20260528150100", "ACCEPTED", "LOT-5"],
        ],
        [
            ["REV-1", "BID-WIN-0001", "BUYER-1", "S-OPEN", "WEB", "0000001111", "20260528150500", "CANCEL", "LOT-1"],
            ["REV-2", "BID-WIN-0002", "BUYER-2", "S-CLOSED", "WEB", "0000002222", "20260528150500", "CANCEL", "LOT-2"],
            ["REV-3", "BID-WIN-0003", "BUYER-3", "S-MISSING", "APP", "0000003333", "20260528150500", "FRAUD", "LOT-3"],
            ["REV-4", "BID-WIN-0004", "BUYER-4", "S-BAD", "FLOOR", "0000004444", "20260528150500", "VOID", "LOT-4"],
            ["REV-5", "BID-WIN-0005", "BUYER-5", "S-OPEN", "WEB", "0000005555", "20260528160100", "CANCEL", "LOT-5"],
        ],
        [
            ["S-OPEN", "20260528145900", "20260528153000", " open "],
            ["S-CLOSED", "20260528145900", "20260528153000", "closed"],
            ["S-BAD", "bad-time", "20260528153000", "OPEN"],
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert [row["channel"] for row in rows] == ["ONLINE", "", "", "", ""]
    assert summary["matched_amount_cents"] == 1111
    assert summary["unmatched_amount_cents"] == 15554


def test_latest_bid_timestamp_selection_is_observable():
    """Choosing the latest eligible bid must leave the earlier bid available for the second reversal."""
    build_program()
    write_inputs(
        [
            ["BID-LATEST", "BUYER-1", "S-L", "ONLINE", "0000001000", "20260528150000", "ACCEPTED", "LOT-1"],
            ["BID-LATEST", "BUYER-1", "S-L", "ONLINE", "0000001000", "20260528150200", "ACCEPTED", "LOT-1"],
        ],
        [
            ["REV-L1", "BID-LATEST", "BUYER-1", "S-L", "WEB", "0000001000", "20260528150500", "CANCEL", "LOT-1"],
            ["REV-L2", "BID-LATEST", "BUYER-1", "S-L", "WEB", "0000001000", "20260528150100", "CANCEL", "LOT-1"],
        ],
        [["S-L", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert summary == {"matched_count": 2, "matched_amount_cents": 2000, "unmatched_count": 0, "unmatched_amount_cents": 0}


def test_latest_timestamp_beats_earlier_bid_row_with_same_match_keys():
    """Latest bid timestamp selection must leave the earlier row for a second eligible reversal."""
    build_program()
    write_inputs(
        [
            ["BID-LATEST", "BUYER-1", "S-L", "ONLINE", "0000001000", "20260528150000", "ACCEPTED", "LOT-1"],
            ["BID-LATEST", "BUYER-1", "S-L", "ONLINE", "0000001000", "20260528150200", "ACCEPTED", "LOT-1"],
        ],
        [
            ["REV-L1", "BID-LATEST", "BUYER-1", "S-L", "WEB", "0000001000", "20260528150500", "CANCEL", "LOT-1"],
            ["REV-L2", "BID-LATEST", "BUYER-1", "S-L", "WEB", "0000001000", "20260528150100", "CANCEL", "LOT-1"],
        ],
        [["S-L", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert summary == {"matched_count": 2, "matched_amount_cents": 2000, "unmatched_count": 0, "unmatched_amount_cents": 0}


def test_tied_latest_timestamp_uses_earliest_physical_row_once():
    """Tied timestamps use earliest physical row and consumption remains row-position based."""
    build_program()
    write_inputs(
        [
            ["BID-TIE", "BUYER-1", "S-T", "MOBILE", "0000000700", "20260528150200", "ACCEPTED", "LOT-7"],
            ["BID-TIE", "BUYER-1", "S-T", "MOBILE", "0000000700", "20260528150200", "ACCEPTED", "LOT-7"],
            ["BID-TIE", "BUYER-1", "S-T", "MOBILE", "0000000700", "20260528150200", "ACCEPTED", "LOT-7"],
        ],
        [
            ["REV-T1", "BID-TIE", "BUYER-1", "S-T", "APP", "0000000700", "20260528150300", "FRAUD", "LOT-7"],
            ["REV-T2", "BID-TIE", "BUYER-1", "S-T", "APP", "0000000700", "20260528150400", "FRAUD", "LOT-7"],
            ["REV-T3", "BID-TIE", "BUYER-1", "S-T", "APP", "0000000700", "20260528150500", "FRAUD", "LOT-7"],
        ],
        [["S-T", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert summary["matched_count"] == 3
    assert summary["matched_amount_cents"] == 2100


def test_tied_latest_timestamp_leaves_second_row_for_followup_reversal():
    """Earliest physical row wins tied latest timestamps so the second tied row remains consumable."""
    build_program()
    write_inputs(
        [
            ["BID-TIE", "BUYER-1", "S-T", "MOBILE", "0000000700", "20260528150200", "ACCEPTED", "LOT-7"],
            ["BID-TIE", "BUYER-1", "S-T", "MOBILE", "0000000700", "20260528150200", "ACCEPTED", "LOT-7"],
        ],
        [
            ["REV-T1", "BID-TIE", "BUYER-1", "S-T", "APP", "0000000700", "20260528150300", "FRAUD", "LOT-7"],
            ["REV-T2", "BID-TIE", "BUYER-1", "S-T", "APP", "0000000700", "20260528150300", "FRAUD", "LOT-7"],
        ],
        [["S-T", "20260528145900", "20260528153000", "OPEN"]],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert summary == {"matched_count": 2, "matched_amount_cents": 1400, "unmatched_count": 0, "unmatched_amount_cents": 0}
