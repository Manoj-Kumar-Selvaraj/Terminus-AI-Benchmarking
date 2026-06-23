"""Verifier tests for realtime hotel night audit chargeback reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "folios.csv"
ACTION = APP / "data" / "chargebacks.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "chargeback_report.csv"
SUMMARY = APP / "out" / "chargeback_summary.txt"
OPEN_WINDOW = [["S-G", "20260528135900", "20260528143000", "OPEN"]]


def build_program():
    """Prepare the reconciler for one verifier scenario."""
    pass


def write_csv(path, header, rows):
    """Write one CSV fixture."""
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(source, action, windows):
    """Overwrite all input files at runtime."""
    write_csv(SOURCE, ["folio_id", "guest_id", "property_id", "kind", "amount", "source_ts", "status", "location"], source)
    write_csv(ACTION, ["action_id", "folio_id", "guest_id", "property_id", "kind", "amount", "action_ts", "reason", "location"], action)
    write_csv(WINDOWS, ["property_id", "open_ts", "close_ts", "state"], windows)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the reconciler and parse outputs."""
    subprocess.run(["ruby", "/app/app/reconcile.rb"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        summary[key] = int(value)
    return rows, summary


class TestMilestone1:
    def test_consumption_prevents_second_match(self):
        """A consumed source row must not match a second correction."""
        build_program()
        write_inputs(
            [["SRC-CON", "PARTY-1", "S-G", "CARD", "10", "20260528140000", "POSTED", "L1"]],
            [
                ["ACT-1", "SRC-CON", "PARTY-1", "S-G", "CARD", "10", "20260528140500", "DISPUTE", "L1"],
                ["ACT-2", "SRC-CON", "PARTY-1", "S-G", "CARD", "10", "20260528140600", "DISPUTE", "L1"],
            ],
            OPEN_WINDOW,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[1]["kind"] == ""
        assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 1, "unmatched_amount": 10}

    def test_location_mismatch_blocks_match(self):
        """Location must independently match in milestone 1."""
        build_program()
        write_inputs(
            [["SRC-LOC", "PARTY-1", "S-G", "CARD", "15", "20260528140000", "POSTED", "L-ORIG"]],
            [["ACT-LOC", "SRC-LOC", "PARTY-1", "S-G", "CARD", "15", "20260528140500", "DISPUTE", "L-OTHER"]],
            OPEN_WINDOW,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary["matched_count"] == 0

    def test_non_posted_source_status_blocks_match(self):
        """Only POSTED source rows may clear."""
        build_program()
        write_inputs(
            [["SRC-BAD", "PARTY-2", "S-G", "CARD", "20", "20260528140100", "BAD", "L2"]],
            [["ACT-BAD", "SRC-BAD", "PARTY-2", "S-G", "CARD", "20", "20260528140700", "DISPUTE", "L2"]],
            OPEN_WINDOW,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["unmatched_amount"] == 20

    def test_action_after_window_close_is_rejected(self):
        """A correction whose action_ts is after the window close must not match."""
        build_program()
        write_inputs(
            [["SRC-CLOSE", "PARTY-6", "S-G", "CARD", "60", "20260528140400", "POSTED", "L6"]],
            [["ACT-CLOSE", "SRC-CLOSE", "PARTY-6", "S-G", "CARD", "60", "20260528143100", "NOAUTH", "L6"]],
            OPEN_WINDOW,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary["matched_count"] == 0

    def test_guest_id_mismatch_blocks_match(self):
        """Guest identity must match exactly."""
        build_program()
        write_inputs(
            [["SRC-GUEST", "PARTY-3", "S-G", "CASH", "30", "20260528140200", "POSTED", "L3"]],
            [["ACT-GUEST", "SRC-GUEST", "PARTY-X", "S-G", "CASH", "30", "20260528140700", "DUPLICATE", "L3"]],
            OPEN_WINDOW,
        )
        rows, _ = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""

    def test_amount_mismatch_blocks_match(self):
        """Amount must match exactly."""
        build_program()
        write_inputs(
            [["SRC-AMT", "PARTY-3", "S-G", "CASH", "30", "20260528140200", "POSTED", "L3"]],
            [["ACT-AMT", "SRC-AMT", "PARTY-3", "S-G", "CASH", "31", "20260528140700", "DUPLICATE", "L3"]],
            OPEN_WINDOW,
        )
        rows, _ = run_program()
        assert rows[0]["status"] == "UNMATCHED"

    def test_action_before_source_timestamp_is_rejected(self):
        """action_ts must be on or after source_ts."""
        build_program()
        write_inputs(
            [["SRC-EARLY", "PARTY-3", "S-G", "CASH", "30", "20260528140200", "POSTED", "L3"]],
            [["ACT-EARLY", "SRC-EARLY", "PARTY-3", "S-G", "CASH", "30", "20260528135959", "DUPLICATE", "L3"]],
            OPEN_WINDOW,
        )
        rows, _ = run_program()
        assert rows[0]["status"] == "UNMATCHED"

    def test_ineligible_reason_blocks_match(self):
        """Only DISPUTE, DUPLICATE, and NOAUTH reasons are eligible."""
        build_program()
        write_inputs(
            [["SRC-REASON", "PARTY-3", "S-G", "CASH", "30", "20260528140200", "POSTED", "L3"]],
            [["ACT-REASON", "SRC-REASON", "PARTY-3", "S-G", "CASH", "30", "20260528140700", "INFO", "L3"]],
            OPEN_WINDOW,
        )
        rows, _ = run_program()
        assert rows[0]["status"] == "UNMATCHED"

    def test_unknown_kind_blocks_match(self):
        """Only canonical CARD, CASH, and POINTS kinds are eligible in milestone 1."""
        build_program()
        write_inputs(
            [["SRC-KIND", "PARTY-4", "S-G", "BAD", "40", "20260528140300", "POSTED", "L4"]],
            [["ACT-KIND", "SRC-KIND", "PARTY-4", "S-G", "BAD", "40", "20260528140700", "NOAUTH", "L4"]],
            OPEN_WINDOW,
        )
        rows, _ = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""

    def test_nonnumeric_source_timestamp_blocks_match(self):
        """Malformed source timestamps must not match."""
        build_program()
        write_inputs(
            [["SRC-BADTS", "PARTY-5", "S-G", "CARD", "50", "not-a-time", "POSTED", "L5"]],
            [["ACT-BADTS", "SRC-BADTS", "PARTY-5", "S-G", "CARD", "50", "20260528140700", "NOAUTH", "L5"]],
            OPEN_WINDOW,
        )
        rows, _ = run_program()
        assert rows[0]["status"] == "UNMATCHED"

    def test_report_schema_and_positive_summary_totals(self):
        """Valid matches must emit the exact report schema and positive summary totals."""
        build_program()
        write_inputs(
            [["SRC-OK", "PARTY-1", "S-G", "CARD", "10", "20260528140000", "POSTED", "L1"]],
            [["ACT-OK", "SRC-OK", "PARTY-1", "S-G", "CARD", "10", "20260528140500", "DISPUTE", "L1"]],
            OPEN_WINDOW,
        )
        rows, summary = run_program()
        assert REPORT.read_text().splitlines()[0] == "action_id,folio_id,guest_id,property_id,kind,amount,reason,status"
        assert rows[0] == {
            "action_id": "ACT-OK",
            "folio_id": "SRC-OK",
            "guest_id": "PARTY-1",
            "property_id": "S-G",
            "kind": "CARD",
            "amount": "10",
            "reason": "DISPUTE",
            "status": "MATCHED",
        }
        assert summary == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 0, "unmatched_amount": 0}
