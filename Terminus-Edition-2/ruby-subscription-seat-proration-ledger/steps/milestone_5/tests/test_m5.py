"""Tests for milestone 5 subscription seat release-calendar reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "seat_events.csv"
ACTION = APP / "data" / "credits.csv"
WINDOWS = APP / "config" / "windows.csv"
POLICY = APP / "config" / "kind_policy.csv"
CALENDAR = APP / "config" / "release_calendar.txt"
LEDGER = APP / "config" / "seat_ledger.csv"
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


def default_ledger_rows(source):
    """Create one open seat-removal credit per source row date for baseline fixtures."""
    capacity = {}
    for row in source:
        subscription_id = row[2].strip()
        source_ts = row[5].strip()
        if subscription_id and len(source_ts) >= 8 and source_ts[:8].isdigit():
            key = (subscription_id, source_ts[:8])
            capacity[key] = capacity.get(key, 0) + 1
    return [[subscription_id, ledger_date, f"-{count}"] for (subscription_id, ledger_date), count in sorted(capacity.items())]


def write_inputs(source, action, windows, policy=None, calendar_lines=None, ledger_rows=None):
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
    write_csv(POLICY, ["kind", "enabled", "priority"], policy or [["BASIC", "Y", "2"], ["PRO", "Y", "1"], ["ENT", "Y", "3"]])
    write_csv(
        ALIASES,
        ["alias", "canonical"],
        [
            ["BSC", "BASIC"],
            ["PROF", "PRO"],
            ["ENTERPRISE", "ENT"],
            ["ENTP", "ENT"],
        ],
    )
    write_csv(
        REASONS,
        ["reason", "eligible"],
        [["DOWNGRADE", "Y"], ["REMOVE", "Y"], ["CORRECT", "Y"]],
    )
    CALENDAR.write_text("\n".join(calendar_lines or ["20260528,OPEN", "20260529,OPEN", "20260530,OPEN"]) + "\n")
    write_csv(
        LEDGER,
        ["subscription_id", "ledger_date", "seat_delta"],
        default_ledger_rows(source) if ledger_rows is None else ledger_rows,
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


class TestMilestone5:
    def test_release_calendar_allows_same_day_and_two_days_but_blocks_three_days(self):
        """Source/action dates must be open and action date must be no more than two days later."""
        build_program()
        write_inputs(
            [
                ["SRC-SAME", "ACCT-1", "SUB-CAL", "BASIC", "10", "20260528100000", "ACTIVE", "L1"],
                ["SRC-TWO", "ACCT-1", "SUB-CAL", "PRO", "20", "20260528100100", "ACTIVE", "L1"],
                ["SRC-THREE", "ACCT-1", "SUB-CAL", "ENT", "30", "20260528100200", "ACTIVE", "L1"],
            ],
            [
                ["ACT-SAME", "SRC-SAME", "ACCT-1", "SUB-CAL", "BASIC", "10", "20260528101000", "DOWNGRADE", "L1"],
                ["ACT-TWO", "SRC-TWO", "ACCT-1", "SUB-CAL", "PRO", "20", "20260530101000", "REMOVE", "L1"],
                ["ACT-THREE", "SRC-THREE", "ACCT-1", "SUB-CAL", "ENT", "30", "20260531101000", "CORRECT", "L1"],
            ],
            [["SUB-CAL", "20260528090000", "20260531235959", "OPEN"]],
            calendar_lines=[" 20260528 , open ", "20260529,OPEN", "20260530,Open", "20260531,OPEN"],
        )
        rows, summary = run_program()

        assert REPORT.read_text().splitlines()[0] == "action_id,event_id,account_id,subscription_id,kind,amount,reason,status"
        assert [row["action_id"] for row in rows] == ["ACT-SAME", "ACT-TWO", "ACT-THREE"]
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["kind"] for row in rows] == ["BASIC", "PRO", ""]
        assert summary == {"matched_count": 2, "matched_amount": 30, "unmatched_count": 1, "unmatched_amount": 30}

    def test_closed_missing_and_malformed_calendar_dates_reject_matches(self):
        """Closed, unlisted, and malformed calendar dates all make rows ineligible."""
        build_program()
        write_inputs(
            [
                ["SRC-CLOSED", "ACCT-2", "SUB-BAD", "BASIC", "11", "20260528100000", "ACTIVE", "L1"],
                ["SRC-MISSING", "ACCT-2", "SUB-BAD", "PRO", "12", "20260529100000", "ACTIVE", "L1"],
                ["SRC-MALFORMED", "ACCT-2", "SUB-BAD", "ENT", "13", "20261301100000", "ACTIVE", "L1"],
            ],
            [
                ["ACT-CLOSED", "SRC-CLOSED", "ACCT-2", "SUB-BAD", "BASIC", "11", "20260528101000", "DOWNGRADE", "L1"],
                ["ACT-MISSING", "SRC-MISSING", "ACCT-2", "SUB-BAD", "PRO", "12", "20260529101000", "REMOVE", "L1"],
                ["ACT-MALFORMED", "SRC-MALFORMED", "ACCT-2", "SUB-BAD", "ENT", "13", "20261301101000", "CORRECT", "L1"],
            ],
            [["SUB-BAD", "20260528090000", "20261301235959", "OPEN"]],
            calendar_lines=["20260528,CLOSED", "bad-line", "20261301,OPEN"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert [row["kind"] for row in rows] == ["", "", ""]
        assert summary["unmatched_amount"] == 36

    def test_calendar_gate_preserves_any_policy_priority_and_consumption(self):
        """Release-calendar checks must compose with ANY selection, policy priority, and consumption."""
        build_program()
        write_inputs(
            [
                ["SRC-ANY-CAL", "ACCT-3", "SUB-ANY-CAL", "ENT", "44", "20260528100000", "ACTIVE", "L1"],
                ["SRC-ANY-CAL", "ACCT-3", "SUB-ANY-CAL", "PRO", "44", "20260528100000", "ACTIVE", "L1"],
            ],
            [
                ["ACT-ANY-CAL-1", "SRC-ANY-CAL", "ACCT-3", "SUB-ANY-CAL", "ANY", "44", "20260529101000", "CORRECT", "L1"],
                ["ACT-ANY-CAL-2", "SRC-ANY-CAL", "ACCT-3", "SUB-ANY-CAL", "ANY", "44", "20260529101100", "CORRECT", "L1"],
                ["ACT-ANY-CAL-3", "SRC-ANY-CAL", "ACCT-3", "SUB-ANY-CAL", "ANY", "44", "20260529101200", "CORRECT", "L1"],
            ],
            [["SUB-ANY-CAL", "20260528090000", "20260529235959", "OPEN"]],
            policy=[["PRO", "Y", "1"], ["ENT", "Y", "3"], ["BASIC", "Y", "2"]],
            calendar_lines=["20260528,OPEN", "20260529,OPEN"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert [row["kind"] for row in rows] == ["PRO", "ENT", ""]
        assert summary == {"matched_count": 2, "matched_amount": 88, "unmatched_count": 1, "unmatched_amount": 44}

    def test_duplicate_calendar_date_last_state_controls_eligibility(self):
        """The last calendar state for a duplicate date controls whether that date is OPEN."""
        build_program()
        write_inputs(
            [["SRC-DUP-CAL", "ACCT-4", "SUB-DUP", "BASIC", "25", "20260528100000", "ACTIVE", "L1"]],
            [["ACT-DUP-CAL", "SRC-DUP-CAL", "ACCT-4", "SUB-DUP", "BASIC", "25", "20260528101000", "DOWNGRADE", "L1"]],
            [["SUB-DUP", "20260528090000", "20260528120000", "OPEN"]],
            calendar_lines=["20260528,OPEN", "20260528,CLOSED"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 25}

    def test_duplicate_calendar_date_reopens_when_last_line_is_open(self):
        """A later valid OPEN line for the same date overrides an earlier CLOSED line."""
        build_program()
        write_inputs(
            [["SRC-DUP-OPEN", "ACCT-5", "SUB-DUP2", "BASIC", "26", "20260528100000", "ACTIVE", "L1"]],
            [["ACT-DUP-OPEN", "SRC-DUP-OPEN", "ACCT-5", "SUB-DUP2", "BASIC", "26", "20260528101000", "DOWNGRADE", "L1"]],
            [["SUB-DUP2", "20260528090000", "20260528120000", "OPEN"]],
            calendar_lines=["20260528,CLOSED", "20260528,OPEN"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["kind"] == "BASIC"
        assert summary == {"matched_count": 1, "matched_amount": 26, "unmatched_count": 0, "unmatched_amount": 0}

    def test_action_calendar_date_before_source_date_stays_unmatched(self):
        """An action calendar date before the source date must stay unmatched even when both dates are open."""
        build_program()
        write_inputs(
            [["SRC-EARLY", "ACCT-6", "SUB-EARLY", "BASIC", "27", "20260529100000", "ACTIVE", "L1"]],
            [["ACT-EARLY", "SRC-EARLY", "ACCT-6", "SUB-EARLY", "BASIC", "27", "20260528101000", "DOWNGRADE", "L1"]],
            [["SUB-EARLY", "20260528090000", "20260529235959", "OPEN"]],
            calendar_lines=["20260528,OPEN", "20260529,OPEN"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 27}

    def test_open_calendar_next_day_still_requires_realtime_window(self):
        """Open source and action calendar dates are not enough when action_ts is after window close."""
        build_program()
        write_inputs(
            [["SRC-WIN-CAL", "ACCT-7", "SUB-WIN-CAL", "BASIC", "28", "20260528100000", "ACTIVE", "L1"]],
            [["ACT-WIN-CAL", "SRC-WIN-CAL", "ACCT-7", "SUB-WIN-CAL", "BASIC", "28", "20260529101000", "DOWNGRADE", "L1"]],
            [["SUB-WIN-CAL", "20260528090000", "20260528120000", "OPEN"]],
            calendar_lines=["20260528,OPEN", "20260529,OPEN"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 28}

    def test_one_calendar_day_later_match_when_both_dates_open(self):
        """An action date exactly one calendar day after the source date may match when both dates are open."""
        build_program()
        write_inputs(
            [["SRC-PLUS1", "ACCT-8", "SUB-PLUS1", "BASIC", "29", "20260528100000", "ACTIVE", "L1"]],
            [["ACT-PLUS1", "SRC-PLUS1", "ACCT-8", "SUB-PLUS1", "BASIC", "29", "20260529101000", "DOWNGRADE", "L1"]],
            [["SUB-PLUS1", "20260528090000", "20260529235959", "OPEN"]],
            calendar_lines=["20260528,OPEN", "20260529,OPEN"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["kind"] == "BASIC"
        assert summary == {"matched_count": 1, "matched_amount": 29, "unmatched_count": 0, "unmatched_amount": 0}

    def test_two_day_span_requires_both_endpoint_dates_open(self):
        """A two-day action span still requires both endpoint calendar dates to be OPEN."""
        build_program()
        write_inputs(
            [["SRC-SPAN", "ACCT-9", "SUB-SPAN", "ENT", "96", "20260528100000", "ACTIVE", "L1"]],
            [["ACT-SPAN", "SRC-SPAN", "ACCT-9", "SUB-SPAN", "ENTERPRISE", "96", "20260530101000", "CORRECT", "L1"]],
            [["SUB-SPAN", "20260528090000", "20260530235959", "OPEN"]],
            calendar_lines=["20260528,OPEN", "20260529,CLOSED", "20260530,OPEN"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["kind"] == "ENT"
        assert summary == {"matched_count": 1, "matched_amount": 96, "unmatched_count": 0, "unmatched_amount": 0}

    def test_unlisted_action_calendar_date_stays_unmatched(self):
        """An open source calendar date is not enough when the action calendar date is unlisted."""
        build_program()
        write_inputs(
            [["SRC-UNLIST-ACT", "ACCT-10", "SUB-UL-ACT", "BASIC", "31", "20260528100000", "ACTIVE", "L1"]],
            [["ACT-UNLIST-ACT", "SRC-UNLIST-ACT", "ACCT-10", "SUB-UL-ACT", "BASIC", "31", "20260529101000", "DOWNGRADE", "L1"]],
            [["SUB-UL-ACT", "20260528090000", "20260529235959", "OPEN"]],
            calendar_lines=["20260528,OPEN"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 31}

    def test_malformed_calendar_lines_do_not_block_valid_open_dates(self):
        """Malformed calendar lines are ignored while valid OPEN dates still allow matching."""
        build_program()
        write_inputs(
            [["SRC-MAL-CAL", "ACCT-11", "SUB-MAL", "PRO", "32", "20260528100000", "ACTIVE", "L1"]],
            [["ACT-MAL-CAL", "SRC-MAL-CAL", "ACCT-11", "SUB-MAL", "PROF", "32", "20260528101000", "REMOVE", "L1"]],
            [["SUB-MAL", "20260528090000", "20260528120000", "OPEN"]],
            calendar_lines=["bad-line", "20260528,OPEN", "not-a-date,OPEN"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["kind"] == "PRO"
        assert summary == {"matched_count": 1, "matched_amount": 32, "unmatched_count": 0, "unmatched_amount": 0}

    def test_two_day_span_rejects_when_action_endpoint_calendar_date_is_closed(self):
        """A two-day action span still fails when the action endpoint date is not OPEN."""
        build_program()
        write_inputs(
            [["SRC-CLOSE-END", "ACCT-12", "SUB-CEND", "BASIC", "33", "20260528100000", "ACTIVE", "L1"]],
            [["ACT-CLOSE-END", "SRC-CLOSE-END", "ACCT-12", "SUB-CEND", "BASIC", "33", "20260530101000", "DOWNGRADE", "L1"]],
            [["SUB-CEND", "20260528090000", "20260530235959", "OPEN"]],
            calendar_lines=["20260528,OPEN", "20260529,OPEN", "20260530,CLOSED"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 33}

    def test_seat_ledger_capacity_limits_matches_for_same_subscription_day(self):
        """Seat ledger removals cap the number of credits that can consume one subscription day."""
        build_program()
        write_inputs(
            [
                ["SRC-LEDGER-A", "ACCT-13", "SUB-LEDGER", "BASIC", "41", "20260528100000", "ACTIVE", "L1"],
                ["SRC-LEDGER-B", "ACCT-13", "SUB-LEDGER", "PRO", "42", "20260528100500", "ACTIVE", "L1"],
            ],
            [
                ["ACT-LEDGER-A", "SRC-LEDGER-A", "ACCT-13", "SUB-LEDGER", "BASIC", "41", "20260528101000", "DOWNGRADE", "L1"],
                ["ACT-LEDGER-B", "SRC-LEDGER-B", "ACCT-13", "SUB-LEDGER", "PRO", "42", "20260528101100", "REMOVE", "L1"],
            ],
            [["SUB-LEDGER", "20260528090000", "20260528120000", "OPEN"]],
            calendar_lines=["20260528,OPEN"],
            ledger_rows=[["SUB-LEDGER", "20260528", "-1"]],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["kind"] for row in rows] == ["BASIC", ""]
        assert summary == {"matched_count": 1, "matched_amount": 41, "unmatched_count": 1, "unmatched_amount": 42}

    def test_failed_action_does_not_consume_seat_ledger_capacity(self):
        """Rejected corrections must not spend ledger capacity needed by a later valid correction."""
        build_program()
        write_inputs(
            [["SRC-NO-SPEND", "ACCT-14", "SUB-NOSPEND", "BASIC", "51", "20260528100000", "ACTIVE", "L1"]],
            [
                ["ACT-BAD-REASON", "SRC-NO-SPEND", "ACCT-14", "SUB-NOSPEND", "BASIC", "51", "20260528101000", "INFO", "L1"],
                ["ACT-GOOD-REASON", "SRC-NO-SPEND", "ACCT-14", "SUB-NOSPEND", "BASIC", "51", "20260528101100", "DOWNGRADE", "L1"],
            ],
            [["SUB-NOSPEND", "20260528090000", "20260528120000", "OPEN"]],
            calendar_lines=["20260528,OPEN"],
            ledger_rows=[["SUB-NOSPEND", "20260528", "-1"]],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert [row["kind"] for row in rows] == ["", "BASIC"]
        assert summary == {"matched_count": 1, "matched_amount": 51, "unmatched_count": 1, "unmatched_amount": 51}

    def test_seat_ledger_ignores_positive_closed_unlisted_and_malformed_rows(self):
        """Only negative seat movements on open valid ledger dates create credit capacity."""
        build_program()
        write_inputs(
            [["SRC-LEDGER-BAD", "ACCT-15", "SUB-BAD-LEDGER", "BASIC", "61", "20260528100000", "ACTIVE", "L1"]],
            [["ACT-LEDGER-BAD", "SRC-LEDGER-BAD", "ACCT-15", "SUB-BAD-LEDGER", "BASIC", "61", "20260528101000", "DOWNGRADE", "L1"]],
            [["SUB-BAD-LEDGER", "20260528090000", "20260528120000", "OPEN"]],
            calendar_lines=["20260528,OPEN", "20260527,CLOSED"],
            ledger_rows=[
                ["SUB-BAD-LEDGER", "20260528", "2"],
                ["SUB-BAD-LEDGER", "20260528", "not-int"],
                ["SUB-BAD-LEDGER", "20260527", "-3"],
                ["SUB-BAD-LEDGER", "20260526", "-3"],
                ["SUB-BAD-LEDGER", "20261301", "-3"],
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 61}

    def test_any_selection_excludes_candidates_with_exhausted_ledger_capacity(self):
        """ANY ranking must ignore otherwise higher-priority rows when their seat capacity is exhausted."""
        build_program()
        write_inputs(
            [
                ["SRC-ANY-LEDGER", "ACCT-16", "SUB-ANY-LEDGER", "PRO", "71", "20260529100000", "ACTIVE", "L1"],
                ["SRC-ANY-LEDGER", "ACCT-16", "SUB-ANY-LEDGER", "ENT", "71", "20260528100000", "ACTIVE", "L1"],
            ],
            [["ACT-ANY-LEDGER", "SRC-ANY-LEDGER", "ACCT-16", "SUB-ANY-LEDGER", "ANY", "71", "20260529101000", "CORRECT", "L1"]],
            [["SUB-ANY-LEDGER", "20260528090000", "20260529235959", "OPEN"]],
            policy=[["PRO", "Y", "1"], ["ENT", "Y", "9"], ["BASIC", "Y", "2"]],
            calendar_lines=["20260528,OPEN", "20260529,OPEN"],
            ledger_rows=[["SUB-ANY-LEDGER", "20260528", "-1"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["kind"] == "ENT"
        assert summary == {"matched_count": 1, "matched_amount": 71, "unmatched_count": 0, "unmatched_amount": 0}
