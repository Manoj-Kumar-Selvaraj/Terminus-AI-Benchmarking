"""Milestone 2 tests — duplicate composite keys spanning sort runs."""
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


class TestMilestone1Regression:
    def test_stmt_date_control_break_splits_same_account_groups(self):
        """Regression: M1 date-break logic must still split non-monotonic groups."""
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


class TestMilestone2:
    def test_duplicate_composite_key_at_run_boundary_merges(self):
        """The same composite key split across runs must stay one accumulator."""
        run1 = APP / "data" / "run01.stm"
        run2 = APP / "data" / "run02.stm"
        write_manifest(["/app/data/run01.stm", "/app/data/run02.stm"])
        write_stream(run1, [fmt_stmt("ACCT1001", "20260401", "00001", "DR", 1000, "RUN01")])
        write_stream(
            run2,
            [
                fmt_stmt("ACCT1001", "20260401", "00001", "CR", 200, "RUN02"),
                fmt_stmt("ACCT1002", "20260401", "00001", "DR", 300, "RUN02"),
            ],
        )
        rows, summary = run_full()

        assert summary["committed_groups"] == 2
        assert summary["total_debit_cents"] == 1300
        assert summary["total_credit_cents"] == 200
        assert rows[0] == {
            "account_id": "ACCT1001",
            "stmt_date": "20260401",
            "debit_cents": 1000,
            "credit_cents": 200,
            "stmt_count": 2,
            "status": "C",
        }
        assert rows[1]["account_id"] == "ACCT1002"

    def test_run_boundary_without_duplicate_key_still_commits(self):
        """Distinct keys at the boundary must still produce separate groups."""
        run1 = APP / "data" / "run01.stm"
        run2 = APP / "data" / "run02.stm"
        write_manifest(["/app/data/run01.stm", "/app/data/run02.stm"])
        write_stream(run1, [fmt_stmt("ACCT5001", "20260403", "00001", "DR", 500, "RUN01")])
        write_stream(run2, [fmt_stmt("ACCT5002", "20260403", "00001", "DR", 700, "RUN02")])
        rows, summary = run_full()

        assert summary["committed_groups"] == 2
        assert summary["total_debit_cents"] == 1200
        assert [r["account_id"] for r in rows] == ["ACCT5001", "ACCT5002"]
