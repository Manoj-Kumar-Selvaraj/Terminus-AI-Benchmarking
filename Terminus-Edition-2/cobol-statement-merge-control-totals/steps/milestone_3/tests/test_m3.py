"""Milestone 3 tests — file-transition control breaks."""
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


class TestMilestone3:
    def test_file_transition_commits_closing_group_not_next_account(self):
        """Pending totals at EOF must commit under the closing account/date."""
        run1 = APP / "data" / "run01.stm"
        run2 = APP / "data" / "run02.stm"
        write_manifest(["/app/data/run01.stm", "/app/data/run02.stm"])
        write_stream(run1, [fmt_stmt("ACCT1001", "20260402", "00001", "DR", 2000, "RUN01")])
        write_stream(run2, [fmt_stmt("ACCT1002", "20260401", "00001", "DR", 300, "RUN02")])
        rows, summary = run_full()

        assert summary["committed_groups"] == 2
        assert rows[0]["account_id"] == "ACCT1001"
        assert rows[0]["stmt_date"] == "20260402"
        assert rows[0]["debit_cents"] == 2000
        assert rows[1]["account_id"] == "ACCT1002"

    def test_multi_run_manifest_preserves_all_groups(self):
        """Three-group merge across two runs must reconcile summary totals."""
        run1 = APP / "data" / "run01.stm"
        run2 = APP / "data" / "run02.stm"
        write_manifest(["/app/data/run01.stm", "/app/data/run02.stm"])
        write_stream(
            run1,
            [
                fmt_stmt("ACCT1001", "20260401", "00001", "DR", 1000, "RUN01"),
                fmt_stmt("ACCT1001", "20260402", "00001", "DR", 2000, "RUN01"),
            ],
        )
        write_stream(
            run2,
            [
                fmt_stmt("ACCT1002", "20260401", "00001", "DR", 300, "RUN02"),
            ],
        )
        rows, summary = run_full()

        assert summary["committed_groups"] == 3
        assert summary["total_debit_cents"] == 3300
        assert summary["total_credit_cents"] == 0
        assert [(r["account_id"], r["stmt_date"]) for r in rows] == [
            ("ACCT1001", "20260401"),
            ("ACCT1001", "20260402"),
            ("ACCT1002", "20260401"),
        ]
