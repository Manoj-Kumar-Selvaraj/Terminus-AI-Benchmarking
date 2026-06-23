"""Tests for milestone 2 subscription seat proration reconciliation."""

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


class TestMilestone2:
    def test_all_gates_consumption_and_exact_summary_totals(self):
        """Only the fully eligible first correction should match while carried-forward gates still reject."""
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

    def test_unknown_kind_stays_unmatched_after_alias_normalization(self):
        """Unknown normalized kinds should not match even when source and correction agree."""
        build_program()
        write_inputs(
            [["SRC-BAD-KIND", "PARTY-4", "S-BAD", "BAD", "90", "20260528120000", "ACTIVE", "LOC-B"]],
            [["ACT-BAD-KIND", "SRC-BAD-KIND", "PARTY-4", "S-BAD", "BAD", "90", "20260528121000", "CORRECT", "LOC-B"]],
            [["S-BAD", "20260528115900", "20260528123000", "OPEN"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 90}

    def test_runtime_alias_entp_from_file(self):
        """Alias rows loaded from kind_aliases.csv must normalize ENTP to ENT."""
        build_program()
        write_inputs(
            [["SRC-ENTP", "PARTY-5", "S-E", "ENT", "61", "20260528120500", "ACTIVE", "LOC-5"]],
            [["ACT-ENTP", "SRC-ENTP", "PARTY-5", "S-E", "ENTP", "61", "20260528121000", "CORRECT", "LOC-5"]],
            [["S-E", "20260528120000", "20260528123000", "OPEN"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["kind"] == "ENT"
        assert summary == {"matched_count": 1, "matched_amount": 61, "unmatched_count": 0, "unmatched_amount": 0}

    def test_source_side_alias_matches_canonical_correction(self):
        """Source-side alias normalization must match a canonical correction kind."""
        build_program()
        write_inputs(
            [["SRC-BSC-SRC", "PARTY-6", "S-B", "BSC", "62", "20260528120500", "ACTIVE", "LOC-6"]],
            [["ACT-BSC-SRC", "SRC-BSC-SRC", "PARTY-6", "S-B", "BASIC", "62", "20260528121000", "DOWNGRADE", "LOC-6"]],
            [["S-B", "20260528120000", "20260528123000", "OPEN"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["kind"] == "BASIC"
        assert summary == {"matched_count": 1, "matched_amount": 62, "unmatched_count": 0, "unmatched_amount": 0}

    def test_reason_trim_and_case_fold_from_file(self):
        """Eligible reasons from reasons.csv must trim and case-fold before matching."""
        build_program()
        write_inputs(
            [["SRC-REASON", "PARTY-7", "S-R", "PRO", "63", "20260528120500", "ACTIVE", "LOC-7"]],
            [["ACT-REASON", "SRC-REASON", "PARTY-7", "S-R", "PROF", "63", "20260528121000", " remove ", "LOC-7"]],
            [["S-R", "20260528120000", "20260528123000", "OPEN"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["kind"] == "PRO"
        assert summary == {"matched_count": 1, "matched_amount": 63, "unmatched_count": 0, "unmatched_amount": 0}

    def test_disabled_reason_from_file_blocks_match(self):
        """Reasons with eligible=N in reasons.csv must block matching."""
        build_program()
        write_inputs(
            [["SRC-DIS-REASON", "PARTY-8", "S-DR", "BASIC", "64", "20260528120500", "ACTIVE", "LOC-8"]],
            [["ACT-DIS-REASON", "SRC-DIS-REASON", "PARTY-8", "S-DR", "BASIC", "64", "20260528121000", "REMOVE", "LOC-8"]],
            [["S-DR", "20260528120000", "20260528123000", "OPEN"]],
            reasons=[["DOWNGRADE", "Y"], ["REMOVE", "N"], ["CORRECT", "Y"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 64}

    def test_absent_reason_from_file_blocks_match(self):
        """A correction reason missing from reasons.csv must stay unmatched."""
        build_program()
        write_inputs(
            [["SRC-ABS-REASON", "PARTY-9", "S-AR", "PRO", "65", "20260528120500", "ACTIVE", "LOC-9"]],
            [["ACT-ABS-REASON", "SRC-ABS-REASON", "PARTY-9", "S-AR", "PROF", "65", "20260528121000", "INFO", "LOC-9"]],
            [["S-AR", "20260528120000", "20260528123000", "OPEN"]],
            reasons=[["DOWNGRADE", "Y"], ["CORRECT", "Y"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary["unmatched_amount"] == 65

    def test_alias_trim_and_case_fold_on_correction_kind(self):
        """Padded or mixed-case alias values on corrections must normalize before matching."""
        build_program()
        write_inputs(
            [["SRC-ALIAS-FOLD", "PARTY-10", "S-AF", "BASIC", "66", "20260528120500", "ACTIVE", "LOC-10"]],
            [["ACT-ALIAS-FOLD", "SRC-ALIAS-FOLD", "PARTY-10", "S-AF", " Bsc ", "66", "20260528121000", "DOWNGRADE", "LOC-10"]],
            [["S-AF", "20260528120000", "20260528123000", "OPEN"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["kind"] == "BASIC"
        assert summary == {"matched_count": 1, "matched_amount": 66, "unmatched_count": 0, "unmatched_amount": 0}

    def test_full_event_id_must_match_not_prefix(self):
        """Shared event-id prefixes are not sufficient for a match."""
        build_program()
        write_inputs(
            [["SRC-PREFIX-100", "PARTY-11", "S-P", "BASIC", "67", "20260528100000", "ACTIVE", "L11"]],
            [["ACT-PREFIX", "SRC-PREFIX-10", "PARTY-11", "S-P", "BASIC", "67", "20260528101000", "DOWNGRADE", "L11"]],
            [["S-P", "20260528090000", "20260528120000", "OPEN"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["kind"] == ""
        assert summary["unmatched_amount"] == 67
