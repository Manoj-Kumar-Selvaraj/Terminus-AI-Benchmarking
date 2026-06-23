"""Tests for milestone 3 subscription seat proration reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "seat_events.csv"
ACTION = APP / "data" / "credits.csv"
WINDOWS = APP / "config" / "windows.csv"
ALIASES = APP / "config" / "kind_aliases.csv"
REASONS = APP / "config" / "reasons.csv"
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


def write_inputs(source, action, windows, aliases=None, reasons=None):
    """Overwrite all input files at runtime."""
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
    write_csv(WINDOWS, ["subscription_id", "open_ts", "close_ts", "state"], windows)
    write_csv(
        ALIASES,
        ["alias", "canonical"],
        aliases
        or [
            ["BSC", "BASIC"],
            ["PROF", "PRO"],
            ["ENTERPRISE", "ENT"],
            ["ENTP", "ENT"],
        ],
    )
    write_csv(
        REASONS,
        ["reason", "eligible"],
        reasons or [["DOWNGRADE", "Y"], ["REMOVE", "Y"], ["CORRECT", "Y"]],
    )
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


class TestMilestone3:
    def test_all_gates_consumption_and_exact_summary_totals(self):
        """Only the fully eligible first correction should match while all earlier gates still reject."""
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

    def test_aliases_full_keys_and_canonical_output(self):
        """Aliases should match full source keys and emit canonical kind values."""
        build_program()
        write_inputs(
            [
                ["SRC-100000001", "PARTY-1", "S-A", "BASIC", "12", "20260528120500", "ACTIVE", "LOC-1"],
                ["SRC-100000002", "PARTY-2", "S-A", "PRO", "34", "20260528120600", "ACTIVE", "LOC-2"],
                ["SRC-100000003", "PARTY-3", "S-B", "ENT", "56", "20260528130500", "ACTIVE", "LOC-3"],
            ],
            [
                ["ACT-1", "SRC-100000001", "PARTY-1", "S-A", "BSC", "12", "20260528121000", "DOWNGRADE", "LOC-1"],
                ["ACT-2", "SRC-100000002", "PARTY-2", "S-A", "PROF", "34", "20260528121100", "REMOVE", "LOC-2"],
                ["ACT-3", "SRC-100000003", "PARTY-3", "S-B", "ENTERPRISE", "56", "20260528131000", "CORRECT", "LOC-3"],
            ],
            [
                ["S-A", "20260528120000", "20260528123000", "OPEN"],
                ["S-B", "20260528130000", "20260528133000", "OPEN"],
            ],
        )
        rows, summary = run_program()
        assert (
            REPORT.read_text().splitlines()[0]
            == "action_id,event_id,account_id,subscription_id,kind,amount,reason,status"
        )
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["kind"] for row in rows] == ["BASIC", "PRO", "ENT"]
        assert summary == {
            "matched_count": 3,
            "matched_amount": 102,
            "unmatched_count": 0,
            "unmatched_amount": 0,
        }

    def test_closed_window_stays_unmatched(self):
        """A CLOSED realtime window makes an otherwise valid correction ineligible."""
        build_program()
        write_inputs(
            [["SRC-WIN-CLOSED", "PARTY-2", "S-C", "BASIC", "2", "20260528150000", "ACTIVE", "L2"]],
            [["ACT-WIN-CLOSED", "SRC-WIN-CLOSED", "PARTY-2", "S-C", "BASIC", "2", "20260528150500", "DOWNGRADE", "L2"]],
            [["S-C", "20260528145900", "20260528153000", "CLOSED"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 2}

    def test_malformed_source_timestamp_stays_unmatched(self):
        """A nonnumeric source timestamp cannot satisfy the realtime window gate."""
        build_program()
        write_inputs(
            [["SRC-WIN-MALFORMED", "PARTY-3", "S-M", "PRO", "3", "bad-time", "ACTIVE", "L3"]],
            [["ACT-WIN-MALFORMED", "SRC-WIN-MALFORMED", "PARTY-3", "S-M", "PRO", "3", "20260528150500", "REMOVE", "L3"]],
            [["S-M", "20260528145900", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 3}

    def test_latest_source_timestamp_wins_when_multiple_rows_qualify(self):
        """The later source row wins when event ids tie but kinds and timestamps differ."""
        build_program()
        write_inputs(
            [
                ["SRC-DUPE", "PARTY-4", "S-O", "BASIC", "4", "20260528150100", "ACTIVE", "L4"],
                ["SRC-DUPE", "PARTY-4", "S-O", "PRO", "4", "20260528150200", "ACTIVE", "L4"],
            ],
            [
                ["ACT-DUPE-LATE", "SRC-DUPE", "PARTY-4", "S-O", "PRO", "4", "20260528150600", "CORRECT", "L4"],
                ["ACT-DUPE-EARLY", "SRC-DUPE", "PARTY-4", "S-O", "BASIC", "4", "20260528150130", "CORRECT", "L4"],
            ],
            [["S-O", "20260528145900", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["kind"] for row in rows] == ["PRO", "BASIC"]
        assert summary == {"matched_count": 2, "matched_amount": 8, "unmatched_count": 0, "unmatched_amount": 0}

    def test_same_source_timestamp_tie_uses_earliest_input_row_and_consumption(self):
        """Equal timestamp candidates should use source row order, then consume rows by position."""
        build_program()
        write_inputs(
            [
                ["SRC-TIE", "PARTY-5", "S-TIE", "PRO", "22", "20260528150000", "ACTIVE", "L5"],
                ["SRC-TIE", "PARTY-5", "S-TIE", "PRO", "22", "20260528150000", "ACTIVE", "L5"],
            ],
            [
                ["ACT-TIE-1", "SRC-TIE", "PARTY-5", "S-TIE", "PROF", "22", "20260528150500", "REMOVE", "L5"],
                ["ACT-TIE-2", "SRC-TIE", "PARTY-5", "S-TIE", "PROF", "22", "20260528150600", "REMOVE", "L5"],
                ["ACT-TIE-3", "SRC-TIE", "PARTY-5", "S-TIE", "PROF", "22", "20260528150700", "REMOVE", "L5"],
            ],
            [["S-TIE", "20260528145900", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["kind"] for row in rows] == ["PRO", "PRO", ""]
        assert summary == {"matched_count": 2, "matched_amount": 44, "unmatched_count": 1, "unmatched_amount": 22}

    def test_action_ts_after_window_close_stays_unmatched(self):
        """Correction action_ts after the matching OPEN window close must stay unmatched."""
        build_program()
        write_inputs(
            [["SRC-CLOSE", "PARTY-1", "S-X", "BASIC", "50", "20260528150000", "ACTIVE", "L1"]],
            [["ACT-CLOSE", "SRC-CLOSE", "PARTY-1", "S-X", "BASIC", "50", "20260528153001", "DOWNGRADE", "L1"]],
            [["S-X", "20260528145900", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount": 0,
            "unmatched_count": 1,
            "unmatched_amount": 50,
        }

    def test_action_ts_at_window_close_boundary_matches(self):
        """action_ts equal to window close_ts is eligible when all other gates pass."""
        build_program()
        write_inputs(
            [["SRC-BOUND", "PARTY-1", "S-BND", "BASIC", "51", "20260528150000", "ACTIVE", "L1"]],
            [["ACT-BOUND", "SRC-BOUND", "PARTY-1", "S-BND", "BASIC", "51", "20260528153000", "DOWNGRADE", "L1"]],
            [["S-BND", "20260528145900", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["kind"] == "BASIC"
        assert summary == {
            "matched_count": 1,
            "matched_amount": 51,
            "unmatched_count": 0,
            "unmatched_amount": 0,
        }

    def test_malformed_window_row_does_not_create_eligibility(self):
        """A window row with nonnumeric open or close timestamps must not make that subscription eligible."""
        build_program()
        write_inputs(
            [["SRC-WIN-BAD", "PARTY-6", "S-BAD", "BASIC", "90", "20260528150000", "ACTIVE", "L6"]],
            [["ACT-WIN-BAD", "SRC-WIN-BAD", "PARTY-6", "S-BAD", "BASIC", "90", "20260528150500", "DOWNGRADE", "L6"]],
            [["S-BAD", "not-a-ts", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount": 0,
            "unmatched_count": 1,
            "unmatched_amount": 90,
        }

    def test_malformed_window_close_ts_does_not_create_eligibility(self):
        """A window row whose close_ts is nonnumeric is ignored and does not open that subscription."""
        build_program()
        write_inputs(
            [["SRC-WIN-BAD-CLOSE", "PARTY-7", "S-BAD2", "BASIC", "91", "20260528150000", "ACTIVE", "L7"]],
            [["ACT-WIN-BAD-CLOSE", "SRC-WIN-BAD-CLOSE", "PARTY-7", "S-BAD2", "BASIC", "91", "20260528150500", "DOWNGRADE", "L7"]],
            [["S-BAD2", "20260528145900", "not-a-ts", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount": 0,
            "unmatched_count": 1,
            "unmatched_amount": 91,
        }

    def test_unlisted_subscription_id_stays_unmatched(self):
        """Source subscription_id absent from windows.csv must stay unmatched even when other gates pass."""
        build_program()
        write_inputs(
            [["SRC-MISS", "PARTY-1", "S-MISSING", "BASIC", "75", "20260528150000", "ACTIVE", "L1"]],
            [["ACT-MISS", "SRC-MISS", "PARTY-1", "S-MISSING", "BASIC", "75", "20260528150500", "DOWNGRADE", "L1"]],
            [["S-OTHER", "20260528145900", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary == {
            "matched_count": 0,
            "matched_amount": 0,
            "unmatched_count": 1,
            "unmatched_amount": 75,
        }

    def test_window_state_trim_and_case_fold(self):
        """Window state must be OPEN after trimming and case folding."""
        build_program()
        write_inputs(
            [["SRC-OPEN-FOLD", "PARTY-8", "S-OF", "BASIC", "92", "20260528150000", "ACTIVE", "L8"]],
            [["ACT-OPEN-FOLD", "SRC-OPEN-FOLD", "PARTY-8", "S-OF", "BASIC", "92", "20260528150500", "DOWNGRADE", "L8"]],
            [["S-OF", "20260528145900", "20260528153000", " open "]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["kind"] == "BASIC"
        assert summary == {"matched_count": 1, "matched_amount": 92, "unmatched_count": 0, "unmatched_amount": 0}

    def test_action_must_fit_same_open_window_as_source(self):
        """When multiple OPEN windows exist, source and action must both fit one window row."""
        build_program()
        write_inputs(
            [["SRC-MULTI-WIN", "PARTY-9", "S-MW", "PRO", "93", "20260528150000", "ACTIVE", "L9"]],
            [["ACT-MULTI-WIN", "SRC-MULTI-WIN", "PARTY-9", "S-MW", "PRO", "93", "20260528153001", "REMOVE", "L9"]],
            [
                ["S-MW", "20260528145900", "20260528153000", "OPEN"],
                ["S-MW", "20260528145900", "20260528160000", "OPEN"],
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["kind"] == "PRO"
        assert summary == {"matched_count": 1, "matched_amount": 93, "unmatched_count": 0, "unmatched_amount": 0}

    def test_nonnumeric_source_timestamp_stays_unmatched(self):
        """Playback source_ts must remain numeric under window gating."""
        build_program()
        write_inputs(
            [["SRC-BAD-SRC-TS", "PARTY-10", "S-BSTS", "BASIC", "94", "bad-time", "ACTIVE", "L10"]],
            [["ACT-BAD-SRC-TS", "SRC-BAD-SRC-TS", "PARTY-10", "S-BSTS", "BSC", "94", "20260528150500", "DOWNGRADE", "L10"]],
            [["S-BSTS", "20260528145900", "20260528153000", "OPEN"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary["unmatched_amount"] == 94

    def test_disabled_reason_from_file_blocks_match(self):
        """Runtime reasons.csv eligibility must still gate matching in milestone 3."""
        build_program()
        write_inputs(
            [["SRC-DIS-REASON", "PARTY-11", "S-DR", "PRO", "95", "20260528150000", "ACTIVE", "L11"]],
            [["ACT-DIS-REASON", "SRC-DIS-REASON", "PARTY-11", "S-DR", "PROF", "95", "20260528150500", "REMOVE", "L11"]],
            [["S-DR", "20260528145900", "20260528153000", "OPEN"]],
            reasons=[["DOWNGRADE", "Y"], ["REMOVE", "N"], ["CORRECT", "Y"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 95}
