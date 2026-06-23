"""Tests for milestone 4 subscription seat policy and ANY reconciliation."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "seat_events.csv"
ACTION = APP / "data" / "credits.csv"
WINDOWS = APP / "config" / "windows.csv"
POLICY = APP / "config" / "kind_policy.csv"
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


def write_inputs(source, action, windows, policy, aliases=None, reasons=None):
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
    write_csv(POLICY, ["kind", "enabled", "priority"], policy)
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


class TestMilestone4:
    def test_disabled_policy_blocks_exact_and_any_matches(self):
        """A disabled canonical kind is ineligible for concrete and ANY corrections."""
        build_program()
        write_inputs(
            [["SRC-DIS", "ACCT-1", "SUB-DIS", "PRO", "40", "20260528100000", "ACTIVE", "L1"]],
            [
                ["ACT-DIS-EXACT", "SRC-DIS", "ACCT-1", "SUB-DIS", "PRO", "40", "20260528101000", "REMOVE", "L1"],
                ["ACT-DIS-ANY", "SRC-DIS", "ACCT-1", "SUB-DIS", "ANY", "40", "20260528101100", "REMOVE", "L1"],
            ],
            [["SUB-DIS", "20260528090000", "20260528120000", "OPEN"]],
            [["BASIC", "Y", "2"], ["PRO", "N", "1"], ["ENT", "Y", "3"]],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert [row["kind"] for row in rows] == ["", ""]
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 2, "unmatched_amount": 80}

    def test_any_uses_latest_timestamp_then_policy_priority(self):
        """ANY corrections prefer the latest source_ts and then the lowest numeric policy priority."""
        build_program()
        write_inputs(
            [
                ["SRC-ANY", "ACCT-2", "SUB-ANY", "BASIC", "55", "20260528100000", "ACTIVE", "L1"],
                ["SRC-ANY", "ACCT-2", "SUB-ANY", "ENT", "55", "20260528103000", "ACTIVE", "L1"],
                ["SRC-ANY", "ACCT-2", "SUB-ANY", "PRO", "55", "20260528103000", "ACTIVE", "L1"],
            ],
            [["ACT-ANY", "SRC-ANY", "ACCT-2", "SUB-ANY", "ANY", "55", "20260528104000", "CORRECT", "L1"]],
            [["SUB-ANY", "20260528090000", "20260528120000", "OPEN"]],
            [["BASIC", "Y", "2"], ["PRO", "Y", "1"], ["ENT", "Y", "3"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["kind"] == "PRO"
        assert summary == {"matched_count": 1, "matched_amount": 55, "unmatched_count": 0, "unmatched_amount": 0}

    def test_any_equal_priority_tie_uses_source_row_order_and_consumption(self):
        """ANY corrections use source row order when timestamp and priority tie, then consume that row."""
        build_program()
        write_inputs(
            [
                ["SRC-ANY-TIE", "ACCT-2", "SUB-ANY-TIE", "BASIC", "55", "20260528103000", "ACTIVE", "L1"],
                ["SRC-ANY-TIE", "ACCT-2", "SUB-ANY-TIE", "PRO", "55", "20260528103000", "ACTIVE", "L1"],
            ],
            [
                ["ACT-ANY-TIE-1", "SRC-ANY-TIE", "ACCT-2", "SUB-ANY-TIE", "ANY", "55", "20260528104000", "CORRECT", "L1"],
                ["ACT-ANY-TIE-2", "SRC-ANY-TIE", "ACCT-2", "SUB-ANY-TIE", "ANY", "55", "20260528104100", "CORRECT", "L1"],
            ],
            [["SUB-ANY-TIE", "20260528090000", "20260528120000", "OPEN"]],
            [["BASIC", "Y", "1"], ["PRO", "Y", "1"]],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["kind"] for row in rows] == ["BASIC", "PRO"]
        assert summary == {"matched_count": 2, "matched_amount": 110, "unmatched_count": 0, "unmatched_amount": 0}

    def test_policy_rows_trim_and_case_fold_before_matching(self):
        """Policy kind and enabled fields should trim and case-fold before gating."""
        build_program()
        write_inputs(
            [["SRC-CASE-POL", "ACCT-5", "SUB-CASE", "PRO", "66", "20260528100000", "ACTIVE", "L1"]],
            [["ACT-CASE-POL", "SRC-CASE-POL", "ACCT-5", "SUB-CASE", "PROF", "66", "20260528101000", "CORRECT", "L1"]],
            [["SUB-CASE", "20260528090000", "20260528120000", "OPEN"]],
            [[" pro ", " y ", "4"], ["BASIC", "N", "1"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["kind"] == "PRO"
        assert summary == {"matched_count": 1, "matched_amount": 66, "unmatched_count": 0, "unmatched_amount": 0}

    def test_concrete_kind_still_requires_exact_canonical_kind(self):
        """Policy does not allow a concrete PRO correction to consume an enabled BASIC source."""
        build_program()
        write_inputs(
            [["SRC-CONCRETE", "ACCT-3", "SUB-CON", "BASIC", "60", "20260528100000", "ACTIVE", "L1"]],
            [["ACT-CONCRETE", "SRC-CONCRETE", "ACCT-3", "SUB-CON", "PROF", "60", "20260528101000", "CORRECT", "L1"]],
            [["SUB-CON", "20260528090000", "20260528120000", "OPEN"]],
            [["BASIC", "Y", "2"], ["PRO", "Y", "1"], ["ENT", "Y", "3"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary["unmatched_amount"] == 60

    def test_unknown_policy_kind_name_does_not_enable_sources(self):
        """Policy rows whose kind is not canonical BASIC, PRO, or ENT do not enable any source kind."""
        build_program()
        write_inputs(
            [["SRC-UNK-POL", "ACCT-6", "SUB-UNK", "BASIC", "77", "20260528100000", "ACTIVE", "L1"]],
            [["ACT-UNK-POL", "SRC-UNK-POL", "ACCT-6", "SUB-UNK", "BASIC", "77", "20260528101000", "DOWNGRADE", "L1"]],
            [["SUB-UNK", "20260528090000", "20260528120000", "OPEN"]],
            [["BOGUS", "Y", "1"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 77}

    def test_alias_policy_kind_name_does_not_enable_sources(self):
        """Policy rows that use alias names such as BSC do not enable canonical BASIC sources."""
        build_program()
        write_inputs(
            [["SRC-ALIAS-POL", "ACCT-8", "SUB-ALIAS", "BASIC", "88", "20260528100000", "ACTIVE", "L1"]],
            [["ACT-ALIAS-POL", "SRC-ALIAS-POL", "ACCT-8", "SUB-ALIAS", "BASIC", "88", "20260528101000", "DOWNGRADE", "L1"]],
            [["SUB-ALIAS", "20260528090000", "20260528120000", "OPEN"]],
            [["BSC", "Y", "1"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 88}

    def test_missing_or_malformed_policy_row_rejects_source_kind(self):
        """Missing policy rows and malformed priorities make an otherwise valid source ineligible."""
        build_program()
        write_inputs(
            [
                ["SRC-MISS-POL", "ACCT-4", "SUB-POL", "ENT", "70", "20260528100000", "ACTIVE", "L1"],
                ["SRC-BAD-PRI", "ACCT-4", "SUB-POL", "PRO", "80", "20260528100100", "ACTIVE", "L1"],
            ],
            [
                ["ACT-MISS-POL", "SRC-MISS-POL", "ACCT-4", "SUB-POL", "ENTERPRISE", "70", "20260528101000", "CORRECT", "L1"],
                ["ACT-BAD-PRI", "SRC-BAD-PRI", "ACCT-4", "SUB-POL", "PROF", "80", "20260528101100", "CORRECT", "L1"],
            ],
            [["SUB-POL", "20260528090000", "20260528120000", "OPEN"]],
            [["BASIC", "Y", "2"], ["PRO", "Y", "not-a-number"]],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert [row["kind"] for row in rows] == ["", ""]
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 2, "unmatched_amount": 150}

    def test_any_skips_disabled_source_at_latest_timestamp(self):
        """ANY must ignore policy-disabled kinds even when they have the latest source_ts."""
        build_program()
        write_inputs(
            [
                ["SRC-ANY-DIS", "ACCT-7", "SUB-ANY-DIS", "BASIC", "45", "20260528100000", "ACTIVE", "L1"],
                ["SRC-ANY-DIS", "ACCT-7", "SUB-ANY-DIS", "ENT", "45", "20260528103000", "ACTIVE", "L1"],
            ],
            [["ACT-ANY-DIS", "SRC-ANY-DIS", "ACCT-7", "SUB-ANY-DIS", "ANY", "45", "20260528104000", "CORRECT", "L1"]],
            [["SUB-ANY-DIS", "20260528090000", "20260528120000", "OPEN"]],
            [["BASIC", "Y", "2"], ["PRO", "Y", "1"], ["ENT", "N", "3"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["kind"] == "BASIC"
        assert summary == {"matched_count": 1, "matched_amount": 45, "unmatched_count": 0, "unmatched_amount": 0}

    def test_enabled_state_synonyms_yes_and_one(self):
        """Policy enabled values YES and 1 must enable canonical kinds after trimming."""
        build_program()
        write_inputs(
            [
                ["SRC-YES", "ACCT-9", "SUB-SYN", "BASIC", "94", "20260528100000", "ACTIVE", "L1"],
                ["SRC-ONE", "ACCT-9", "SUB-SYN", "PRO", "95", "20260528100100", "ACTIVE", "L1"],
            ],
            [
                ["ACT-YES", "SRC-YES", "ACCT-9", "SUB-SYN", "BASIC", "94", "20260528101000", "DOWNGRADE", "L1"],
                ["ACT-ONE", "SRC-ONE", "ACCT-9", "SUB-SYN", "PROF", "95", "20260528101100", "REMOVE", "L1"],
            ],
            [["SUB-SYN", "20260528090000", "20260528120000", "OPEN"]],
            [["BASIC", " yes ", "2"], ["PRO", "1", "1"], ["ENT", "N", "3"]],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["kind"] for row in rows] == ["BASIC", "PRO"]
        assert summary == {"matched_count": 2, "matched_amount": 189, "unmatched_count": 0, "unmatched_amount": 0}

    def test_any_kind_emitted_as_canonical_not_any_in_report(self):
        """Matched ANY corrections must emit the selected source canonical kind, never ANY, in the kind column."""
        build_program()
        write_inputs(
            [["SRC-ANY-KIND", "ACCT-10", "SUB-ANY-K", "ENT", "97", "20260528100000", "ACTIVE", "L1"]],
            [["ACT-ANY-KIND", "SRC-ANY-KIND", "ACCT-10", "SUB-ANY-K", "ANY", "97", "20260528101000", "CORRECT", "L1"]],
            [["SUB-ANY-K", "20260528090000", "20260528120000", "OPEN"]],
            [["BASIC", "Y", "2"], ["PRO", "Y", "1"], ["ENT", "Y", "3"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["reason"] == "CORRECT"
        assert rows[0]["kind"] == "ENT"
        assert rows[0]["kind"] != "ANY"
        assert summary == {"matched_count": 1, "matched_amount": 97, "unmatched_count": 0, "unmatched_amount": 0}

    def test_absent_reason_from_file_blocks_match(self):
        """A correction reason missing from reasons.csv must stay unmatched under policy gating."""
        build_program()
        write_inputs(
            [["SRC-ABS-R", "ACCT-11", "SUB-ABS-R", "BASIC", "98", "20260528100000", "ACTIVE", "L1"]],
            [["ACT-ABS-R", "SRC-ABS-R", "ACCT-11", "SUB-ABS-R", "BASIC", "98", "20260528101000", "INFO", "L1"]],
            [["SUB-ABS-R", "20260528090000", "20260528120000", "OPEN"]],
            [["BASIC", "Y", "2"], ["PRO", "Y", "1"], ["ENT", "Y", "3"]],
            reasons=[["DOWNGRADE", "Y"], ["CORRECT", "Y"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 98}
