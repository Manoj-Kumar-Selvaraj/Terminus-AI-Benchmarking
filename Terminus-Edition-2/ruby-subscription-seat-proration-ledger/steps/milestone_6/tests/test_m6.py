"""Tests for milestone 6 contract-rate proration controls."""

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
CONTRACTS = APP / "config" / "proration_contracts.csv"
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


def default_contract_rows(source):
    """Create exact NEAREST contracts for source rows unless a test overrides them."""
    rows = []
    seen = set()
    for row in source:
        subscription_id = row[2].strip()
        kind = row[3].strip().upper()
        amount = row[4].strip()
        source_ts = row[5].strip()
        if not subscription_id or not source_ts[:8].isdigit() or (subscription_id, kind, amount, source_ts[:8]) in seen:
            continue
        seen.add((subscription_id, kind, amount, source_ts[:8]))
        rows.append([subscription_id, source_ts[:8], source_ts[:8], kind, source_ts[:8], amount, "NEAREST", "Y"])
    return rows


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


def write_inputs(source, action, windows, policy=None, calendar_lines=None, ledger_rows=None, contract_rows=None):
    """Overwrite all runtime inputs and config files."""
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
    write_csv(ALIASES, ["alias", "canonical"], [["BSC", "BASIC"], ["PROF", "PRO"], ["ENTERPRISE", "ENT"], ["ENTP", "ENT"]])
    write_csv(REASONS, ["reason", "eligible"], [["DOWNGRADE", "Y"], ["REMOVE", "Y"], ["CORRECT", "Y"]])
    CALENDAR.write_text("\n".join(calendar_lines or ["20260528,OPEN", "20260529,OPEN", "20260530,OPEN", "20260531,OPEN"]) + "\n")
    write_csv(LEDGER, ["subscription_id", "ledger_date", "seat_delta"], default_ledger_rows(source) if ledger_rows is None else ledger_rows)
    write_csv(
        CONTRACTS,
        ["subscription_id", "period_start", "period_end", "kind", "cutover_date", "rate_cents", "rounding_mode", "enabled"],
        default_contract_rows(source) if contract_rows is None else contract_rows,
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


class TestMilestone6:
    def test_rounding_modes_and_amount_gate_are_runtime_contract_driven(self):
        """FLOOR, CEIL, and NEAREST contract rows must compute different eligible amounts."""
        build_program()
        source = [
            ["SRC-FLOOR", "ACCT-1", "SUB-RND", "BASIC", "23", "20260529100000", "ACTIVE", "L1"],
            ["SRC-CEIL", "ACCT-1", "SUB-RND", "PRO", "24", "20260529100100", "ACTIVE", "L1"],
            ["SRC-NEAR", "ACCT-1", "SUB-RND", "ENT", "25", "20260529100200", "ACTIVE", "L1"],
            ["SRC-WRONG", "ACCT-1", "SUB-RND", "BASIC", "24", "20260529100300", "ACTIVE", "L1"],
        ]
        write_inputs(
            source,
            [
                ["ACT-FLOOR", "SRC-FLOOR", "ACCT-1", "SUB-RND", "BASIC", "23", "20260529101000", "DOWNGRADE", "L1"],
                ["ACT-CEIL", "SRC-CEIL", "ACCT-1", "SUB-RND", "PRO", "24", "20260529101100", "REMOVE", "L1"],
                ["ACT-NEAR", "SRC-NEAR", "ACCT-1", "SUB-RND", "ENT", "25", "20260529101200", "CORRECT", "L1"],
                ["ACT-WRONG", "SRC-WRONG", "ACCT-1", "SUB-RND", "BASIC", "24", "20260529101300", "DOWNGRADE", "L1"],
            ],
            [["SUB-RND", "20260529090000", "20260529235959", "OPEN"]],
            ledger_rows=[["SUB-RND", "20260529", "-4"]],
            contract_rows=[
                ["SUB-RND", "20260501", "20260531", "BASIC", "20260501", "238", "FLOOR", "Y"],
                ["SUB-RND", "20260501", "20260531", "PRO", "20260501", "238", "CEIL", "Y"],
                ["SUB-RND", "20260501", "20260531", "ENT", "20260501", "258", "NEAREST", "Y"],
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
        assert summary == {"matched_count": 3, "matched_amount": 72, "unmatched_count": 1, "unmatched_amount": 24}

    def test_latest_cutover_contract_row_overrides_older_rate(self):
        """When several contract rows match, the latest cutover date controls the amount."""
        build_program()
        write_inputs(
            [["SRC-CUTOVER", "ACCT-2", "SUB-CUT", "BASIC", "12", "20260529100000", "ACTIVE", "L2"]],
            [["ACT-CUTOVER", "SRC-CUTOVER", "ACCT-2", "SUB-CUT", "BASIC", "12", "20260529101000", "DOWNGRADE", "L2"]],
            [["SUB-CUT", "20260529090000", "20260529235959", "OPEN"]],
            contract_rows=[
                ["SUB-CUT", "20260501", "20260531", "BASIC", "20260501", "3100", "FLOOR", "Y"],
                ["SUB-CUT", "20260501", "20260531", "BASIC", "20260520", "124", "FLOOR", "Y"],
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["kind"] == "BASIC"
        assert summary["matched_amount"] == 12

    def test_any_selection_excludes_latest_candidate_when_proration_amount_is_wrong(self):
        """ANY ranking must happen after contract amount eligibility filters candidates."""
        build_program()
        write_inputs(
            [
                ["SRC-ANY-PRORATE", "ACCT-3", "SUB-ANY-P", "PRO", "99", "20260529120000", "ACTIVE", "L3"],
                ["SRC-ANY-PRORATE", "ACCT-3", "SUB-ANY-P", "ENT", "99", "20260529100000", "ACTIVE", "L3"],
            ],
            [["ACT-ANY-PRORATE", "SRC-ANY-PRORATE", "ACCT-3", "SUB-ANY-P", "ANY", "99", "20260529121000", "CORRECT", "L3"]],
            [["SUB-ANY-P", "20260529090000", "20260529235959", "OPEN"]],
            policy=[["PRO", "Y", "1"], ["ENT", "Y", "9"], ["BASIC", "Y", "2"]],
            ledger_rows=[["SUB-ANY-P", "20260529", "-2"]],
            contract_rows=[
                ["SUB-ANY-P", "20260501", "20260531", "PRO", "20260501", "3100", "NEAREST", "Y"],
                ["SUB-ANY-P", "20260501", "20260531", "ENT", "20260501", "1023", "NEAREST", "Y"],
            ],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["kind"] == "ENT"
        assert summary == {"matched_count": 1, "matched_amount": 99, "unmatched_count": 0, "unmatched_amount": 0}

    def test_disabled_malformed_and_out_of_period_contracts_do_not_create_eligibility(self):
        """Only enabled, well-formed contract rows covering the source date can match."""
        build_program()
        write_inputs(
            [
                ["SRC-NO-CONTRACT-A", "ACCT-4", "SUB-BAD-C", "BASIC", "25", "20260529100000", "ACTIVE", "L4"],
                ["SRC-NO-CONTRACT-B", "ACCT-4", "SUB-BAD-C", "PRO", "25", "20260529100100", "ACTIVE", "L4"],
                ["SRC-NO-CONTRACT-C", "ACCT-4", "SUB-BAD-C", "ENT", "25", "20260529100200", "ACTIVE", "L4"],
            ],
            [
                ["ACT-NO-CONTRACT-A", "SRC-NO-CONTRACT-A", "ACCT-4", "SUB-BAD-C", "BASIC", "25", "20260529101000", "DOWNGRADE", "L4"],
                ["ACT-NO-CONTRACT-B", "SRC-NO-CONTRACT-B", "ACCT-4", "SUB-BAD-C", "PRO", "25", "20260529101100", "REMOVE", "L4"],
                ["ACT-NO-CONTRACT-C", "SRC-NO-CONTRACT-C", "ACCT-4", "SUB-BAD-C", "ENT", "25", "20260529101200", "CORRECT", "L4"],
            ],
            [["SUB-BAD-C", "20260529090000", "20260529235959", "OPEN"]],
            ledger_rows=[["SUB-BAD-C", "20260529", "-3"]],
            contract_rows=[
                ["SUB-BAD-C", "20260501", "20260531", "BASIC", "20260501", "3100", "NEAREST", "N"],
                ["SUB-BAD-C", "20260501", "20260531", "PRO", "20260601", "3100", "NEAREST", "Y"],
                ["SUB-BAD-C", "20260501", "20260531", "ENT", "20260501", "3100", "ROUND", "Y"],
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 3, "unmatched_amount": 75}

    def test_contract_gate_does_not_consume_ledger_capacity_on_rejected_action(self):
        """A bad proration amount must not spend the only ledger unit needed by a later valid correction."""
        build_program()
        write_inputs(
            [["SRC-NO-SPEND-P", "ACCT-5", "SUB-NSP", "BASIC", "25", "20260529100000", "ACTIVE", "L5"]],
            [
                ["ACT-WRONG-PRORATE", "SRC-NO-SPEND-P", "ACCT-5", "SUB-NSP", "BASIC", "24", "20260529101000", "DOWNGRADE", "L5"],
                ["ACT-RIGHT-PRORATE", "SRC-NO-SPEND-P", "ACCT-5", "SUB-NSP", "BASIC", "25", "20260529101100", "DOWNGRADE", "L5"],
            ],
            [["SUB-NSP", "20260529090000", "20260529235959", "OPEN"]],
            ledger_rows=[["SUB-NSP", "20260529", "-1"]],
            contract_rows=[["SUB-NSP", "20260501", "20260531", "BASIC", "20260501", "258", "NEAREST", "Y"]],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert [row["kind"] for row in rows] == ["", "BASIC"]
        assert summary == {"matched_count": 1, "matched_amount": 25, "unmatched_count": 1, "unmatched_amount": 24}
