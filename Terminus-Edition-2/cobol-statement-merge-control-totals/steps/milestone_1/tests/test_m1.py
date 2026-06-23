"""Milestone 1 tests — account/date control breaks on non-monotonic streams."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_test_helpers import (  # noqa: E402
    APP,
    fmt_stmt,
    run_full,
    write_manifest,
    write_stream,
)


class TestMilestone1:
    def test_stmt_date_control_break_splits_same_account_groups(self):
        """Same account with regressing stmt dates must not collapse into one total."""
        run1 = APP / "data" / "run01.stm"
        write_manifest(["/app/data/run01.stm"])
        write_stream(
            run1,
            [
                fmt_stmt("ACCT1001", "20260401", "00001", "DR", 1000),
                fmt_stmt("ACCT1001", "20260402", "00001", "DR", 2000),
                fmt_stmt("ACCT1001", "20260401", "00002", "CR", 50),
            ],
        )
        rows, summary = run_full()

        assert summary["committed_groups"] == 3
        assert summary["total_debit_cents"] == 3000
        assert summary["total_credit_cents"] == 50
        assert summary["statement_rows"] == 3
        assert [(r["account_id"], r["stmt_date"], r["debit_cents"], r["credit_cents"]) for r in rows] == [
            ("ACCT1001", "20260401", 1000, 0),
            ("ACCT1001", "20260402", 2000, 0),
            ("ACCT1001", "20260401", 0, 50),
        ]

    def test_monotonic_same_date_accumulates_debits_and_credits(self):
        """Rows sharing account and stmt date stay in one committed group."""
        run1 = APP / "data" / "run01.stm"
        write_manifest(["/app/data/run01.stm"])
        write_stream(
            run1,
            [
                fmt_stmt("ACCT2001", "20260405", "00001", "DR", 400),
                fmt_stmt("ACCT2001", "20260405", "00002", "DR", 600),
                fmt_stmt("ACCT2001", "20260405", "00003", "CR", 100),
            ],
        )
        rows, summary = run_full()

        assert summary["committed_groups"] == 1
        assert summary["total_debit_cents"] == 1000
        assert summary["total_credit_cents"] == 100
        assert rows[0]["stmt_count"] == 3

    def test_account_change_still_commits_distinct_groups(self):
        """Control breaks must fire when the account changes."""
        run1 = APP / "data" / "run01.stm"
        write_manifest(["/app/data/run01.stm"])
        write_stream(
            run1,
            [
                fmt_stmt("ACCT3001", "20260401", "00001", "DR", 150),
                fmt_stmt("ACCT3002", "20260401", "00001", "DR", 250),
            ],
        )
        rows, summary = run_full()

        assert summary["committed_groups"] == 2
        assert summary["total_debit_cents"] == 400
        assert [r["account_id"] for r in rows] == ["ACCT3001", "ACCT3002"]

    def test_summary_keys_present(self):
        """Merge summary must expose the documented key=value counters."""
        run1 = APP / "data" / "run01.stm"
        write_manifest(["/app/data/run01.stm"])
        write_stream(run1, [fmt_stmt("ACCT4001", "20260401", "00001", "DR", 900)])
        _, summary = run_full()

        assert set(summary.keys()) == {
            "committed_groups",
            "total_debit_cents",
            "total_credit_cents",
            "statement_rows",
            "checkpoint_commits",
        }

    def test_multi_file_same_key_produces_separate_commits(self):
        """Cross-file transitions must not collapse duplicate keys into one group."""
        run1 = APP / "data" / "run01.stm"
        run2 = APP / "data" / "run02.stm"
        write_manifest(["/app/data/run01.stm", "/app/data/run02.stm"])
        write_stream(run1, [fmt_stmt("ACCT1001", "20260401", "00001", "DR", 100, "RUN01")])
        write_stream(run2, [fmt_stmt("ACCT1001", "20260401", "00001", "DR", 200, "RUN02")])
        rows, summary = run_full()

        assert summary["committed_groups"] == 2
        assert summary["total_debit_cents"] == 300
        assert summary["statement_rows"] == 2
        assert rows[0]["account_id"] == "ACCT1001"
        assert rows[0]["stmt_date"] == "20260401"
        assert rows[0]["debit_cents"] == 100
        assert rows[1]["account_id"] == "ACCT1001"
        assert rows[1]["stmt_date"] == "20260401"
        assert rows[1]["debit_cents"] == 200
