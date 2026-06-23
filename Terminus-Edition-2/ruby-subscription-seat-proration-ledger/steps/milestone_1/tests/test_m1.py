"""Tests for milestone 1 subscription seat proration reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "seat_events.csv"
ACTION = APP / "data" / "credits.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "seat_credit_report.csv"
SUMMARY = APP / "out" / "seat_credit_summary.txt"


def build_program():
    """No build step is needed for the Ruby entrypoint."""
    pass


def write_csv(path, header, rows):
    """Write one CSV fixture."""
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(source, action, windows):
    """Overwrite all input files at runtime.

    The windows fixture is written for helper reuse across milestones; milestone 1
    ignores `/app/config/windows.csv` because window eligibility starts in milestone 3.
    """
    write_csv(
        SOURCE,
        ["event_id", "account_id", "subscription_id", "kind", "amount", "source_ts", "status", "location"],
        source,
    )
    write_csv(
        ACTION,
        ["action_id", "event_id", "account_id", "subscription_id", "kind", "amount", "action_ts", "reason", "location"],
        action,
    )
    # Milestone 1 reconciler ignores windows.csv; shared helper shape only.
    write_csv(WINDOWS, ["subscription_id", "open_ts", "close_ts", "state"], windows)
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
    def test_all_gates_consumption_and_exact_summary_totals(self):
        """Only the fully eligible first correction should match; all later gate failures stay unmatched."""
        build_program()
        write_inputs(
            [
                ["SRC-GATE-1", "PARTY-1", "S-G", "BASIC", "10", "20260528140000", "ACTIVE", "L1"],
                ["SRC-GATE-2", "PARTY-2", "S-G", "BASIC", "20", "20260528140100", "BAD", "L2"],
                ["SRC-GATE-3", "PARTY-3", "S-G", "PRO", "30", "20260528140200", "ACTIVE", "L3"],
                ["SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140300", "ACTIVE", "L4"],
            ],
            [
                ["ACT-A", "SRC-GATE-1", "PARTY-1", "S-G", "BASIC", "10", "20260528140500", "DOWNGRADE", "L1"],
                ["ACT-B", "SRC-GATE-1", "PARTY-1", "S-G", "BASIC", "10", "20260528140600", "DOWNGRADE", "L1"],
                ["ACT-C", "SRC-GATE-2", "PARTY-2", "S-G", "BASIC", "20", "20260528140700", "DOWNGRADE", "L2"],
                ["ACT-D", "SRC-GATE-3", "PARTY-X", "S-G", "PRO", "30", "20260528140700", "REMOVE", "L3"],
                ["ACT-E", "SRC-GATE-3", "PARTY-3", "S-G", "PRO", "31", "20260528140700", "REMOVE", "L3"],
                ["ACT-F", "SRC-GATE-3", "PARTY-3", "S-G", "PRO", "30", "20260528135959", "REMOVE", "L3"],
                ["ACT-G", "SRC-GATE-3", "PARTY-3", "S-G", "PRO", "30", "20260528140700", "INFO", "L3"],
                ["ACT-H", "SRC-GATE-4", "PARTY-4", "S-G", "BAD", "40", "20260528140700", "CORRECT", "L4"],
            ],
            [["S-G", "20260528135900", "20260528143000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == [
            "MATCHED",
            "UNMATCHED",
            "UNMATCHED",
            "UNMATCHED",
            "UNMATCHED",
            "UNMATCHED",
            "UNMATCHED",
            "UNMATCHED",
        ]
        assert rows[1]["kind"] == ""
        assert summary == {
            "matched_count": 1,
            "matched_amount": 10,
            "unmatched_count": 7,
            "unmatched_amount": 191,
        }

    def test_report_schema_action_order_blank_kind_and_integer_totals(self):
        """The report should keep correction order, blank unmatched kind, and exact integer totals."""
        build_program()
        write_inputs(
            [
                ["SRC-ORDER-1", "PARTY-1", "S-O", "PRO", "25", "20260528100000", "ACTIVE", "L1"],
                ["SRC-ORDER-2", "PARTY-2", "S-O", "BASIC", "35", "20260528100100", "ACTIVE", "L2"],
            ],
            [
                ["ACT-FIRST", "SRC-ORDER-2", "PARTY-2", "S-O", "BASIC", "35", "20260528101000", "REMOVE", "L2"],
                ["ACT-SECOND", "SRC-MISSING", "PARTY-1", "S-O", "PRO", "25", "20260528101100", "DOWNGRADE", "L1"],
                ["ACT-THIRD", "SRC-ORDER-1", "PARTY-1", "S-O", "PRO", "25", "20260528101200", "DOWNGRADE", "L1"],
            ],
            [["S-O", "20260528090000", "20260528120000", "OPEN"]],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "action_id,event_id,account_id,subscription_id,kind,amount,reason,status"
        assert [row["action_id"] for row in rows] == ["ACT-FIRST", "ACT-SECOND", "ACT-THIRD"]
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["kind"] for row in rows] == ["BASIC", "", "PRO"]
        assert summary == {"matched_count": 2, "matched_amount": 60, "unmatched_count": 1, "unmatched_amount": 25}

    def test_full_event_id_must_match_not_prefix(self):
        """Shared event-id prefixes are not sufficient for a match."""
        build_program()
        write_inputs(
            [["SRC-PREFIX-100", "PARTY-1", "S-P", "BASIC", "15", "20260528100000", "ACTIVE", "L1"]],
            [["ACT-PREFIX", "SRC-PREFIX-10", "PARTY-1", "S-P", "BASIC", "15", "20260528101000", "DOWNGRADE", "L1"]],
            [["S-P", "20260528090000", "20260528120000", "OPEN"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary["unmatched_amount"] == 15

    def test_nonnumeric_action_timestamp_stays_unmatched(self):
        """The action timestamp must be numeric before a correction can match."""
        build_program()
        write_inputs(
            [["SRC-BAD-ACTION-TS", "PARTY-1", "S-TS", "BASIC", "18", "20260528100000", "ACTIVE", "L1"]],
            [["ACT-BAD-ACTION-TS", "SRC-BAD-ACTION-TS", "PARTY-1", "S-TS", "BASIC", "18", "not-a-time", "DOWNGRADE", "L1"]],
            [["S-TS", "20260528090000", "20260528120000", "OPEN"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 18}

    def test_invalid_correction_kind_stays_unmatched(self):
        """A correction whose kind is not BASIC or PRO must stay UNMATCHED even when the source is eligible."""
        build_program()
        write_inputs(
            [["SRC-BAD-KIND", "PARTY-7", "S-K", "BASIC", "42", "20260528100000", "ACTIVE", "L7"]],
            [["ACT-BAD-KIND", "SRC-BAD-KIND", "PARTY-7", "S-K", "BAD", "42", "20260528101000", "DOWNGRADE", "L7"]],
            [["S-K", "20260528090000", "20260528120000", "OPEN"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 42}

    def test_ineligible_reason_stays_unmatched(self):
        """A correction reason outside DOWNGRADE, REMOVE, or CORRECT must not match."""
        build_program()
        write_inputs(
            [["SRC-BAD-REASON", "PARTY-7R", "S-R", "BASIC", "43", "20260528100000", "ACTIVE", "L7R"]],
            [["ACT-BAD-REASON", "SRC-BAD-REASON", "PARTY-7R", "S-R", "BASIC", "43", "20260528101000", "INFO", "L7R"]],
            [["S-R", "20260528090000", "20260528120000", "OPEN"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 43}

    def test_active_status_trim_and_case_fold(self):
        """Source status must be ACTIVE after trimming and case folding."""
        build_program()
        write_inputs(
            [["SRC-ACTIVE-FOLD", "PARTY-8", "S-AF", "BASIC", "19", "20260528100000", " active ", "L8"]],
            [["ACT-ACTIVE-FOLD", "SRC-ACTIVE-FOLD", "PARTY-8", "S-AF", "BASIC", "19", "20260528101000", "DOWNGRADE", "L8"]],
            [["S-AF", "20260528090000", "20260528120000", "OPEN"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["kind"] == "BASIC"
        assert summary == {"matched_count": 1, "matched_amount": 19, "unmatched_count": 0, "unmatched_amount": 0}

    def test_nonnumeric_source_timestamp_stays_unmatched(self):
        """Playback source_ts must be a numeric 14-digit string before matching."""
        build_program()
        write_inputs(
            [["SRC-BAD-SRC-TS", "PARTY-9", "S-BSTS", "BASIC", "21", "not-a-time", "ACTIVE", "L9"]],
            [["ACT-BAD-SRC-TS", "SRC-BAD-SRC-TS", "PARTY-9", "S-BSTS", "BASIC", "21", "20260528101000", "DOWNGRADE", "L9"]],
            [["S-BSTS", "20260528090000", "20260528120000", "OPEN"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 21}

    def test_location_mismatch_stays_unmatched(self):
        """Location must match exactly between source and correction rows."""
        build_program()
        write_inputs(
            [["SRC-LOC", "PARTY-10", "S-LOC", "BASIC", "22", "20260528100000", "ACTIVE", "L10"]],
            [["ACT-LOC", "SRC-LOC", "PARTY-10", "S-LOC", "BASIC", "22", "20260528101000", "DOWNGRADE", "L99"]],
            [["S-LOC", "20260528090000", "20260528120000", "OPEN"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary["unmatched_amount"] == 22

    def test_action_timestamp_equal_to_source_timestamp_still_matches(self):
        """A correction whose action_ts equals source_ts must still match when other gates pass."""
        build_program()
        write_inputs(
            [["SRC-EQ-TS", "PARTY-11", "S-EQ", "PRO", "23", "20260528100000", "ACTIVE", "L11"]],
            [["ACT-EQ-TS", "SRC-EQ-TS", "PARTY-11", "S-EQ", "PRO", "23", "20260528100000", "REMOVE", "L11"]],
            [["S-EQ", "20260528090000", "20260528120000", "OPEN"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["kind"] == "PRO"
        assert summary == {"matched_count": 1, "matched_amount": 23, "unmatched_count": 0, "unmatched_amount": 0}

    def test_invalid_source_kind_stays_unmatched(self):
        """Playback rows whose kind is not BASIC or PRO must never be consumed."""
        build_program()
        write_inputs(
            [["SRC-BAD-SRC-KIND", "PARTY-12", "S-SK", "BAD", "24", "20260528100000", "ACTIVE", "L12"]],
            [["ACT-BAD-SRC-KIND", "SRC-BAD-SRC-KIND", "PARTY-12", "S-SK", "BASIC", "24", "20260528101000", "DOWNGRADE", "L12"]],
            [["S-SK", "20260528090000", "20260528120000", "OPEN"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 24}
