"""Milestone 3 — dual approval requires regional and finance stages."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from billing_test_helpers import APP, fmt_usage, run_full, write_manifest, write_prior, write_usage


class TestMilestone3:
    def test_dual_posts_finance_trace(self):
        """DUAL approval writes ordered REGIONAL and FINANCE PASS rows."""
        run1 = APP / "data" / "run01.usg"
        write_prior([])
        write_manifest(["/app/data/run01.usg"])
        write_usage(
            run1,
            [
                fmt_usage("ACCT1001", "BATCH1", "0001", 1000000),
                fmt_usage("ACCT1001", "BATCH1", "0002", 1100000),
            ],
        )
        invoices, trace, summary = run_full()
        assert invoices[0]["approval_tier"] == "DUAL"
        account_trace = [t for t in trace if t["account_id"] == "ACCT1001"]
        assert [t["stage"] for t in account_trace] == ["REGIONAL", "FINANCE"]
        assert [t["result"] for t in account_trace] == ["PASS", "PASS"]
        assert invoices[0]["stages"] == "REGIONAL+FINANCE"
        assert summary["invoices_posted"] == 1

    def test_regional_single_stage_only(self):
        """REGIONAL approval remains a single approved trace stage."""
        run1 = APP / "data" / "run01.usg"
        write_prior([])
        write_manifest(["/app/data/run01.usg"])
        write_usage(run1, [fmt_usage("ACCT2001", "BATCH2", "0001", 600000)])
        invoices, trace, _ = run_full()
        assert invoices[0]["approval_tier"] == "REGIONAL"
        assert invoices[0]["stages"] == "REGIONAL"
        assert [t["stage"] for t in trace] == ["REGIONAL"]
        assert [t["result"] for t in trace] == ["PASS"]

    def test_auto_keeps_stage_without_trace(self):
        """AUTO invoices retain AUTO and do not emit approval trace rows."""
        run1 = APP / "data" / "run01.usg"
        write_prior([])
        write_manifest(["/app/data/run01.usg"])
        write_usage(run1, [fmt_usage("ACCT3001", "BATCH3", "0001", 250000)])
        invoices, trace, _ = run_full()
        assert invoices[0]["approval_tier"] == "AUTO"
        assert invoices[0]["stages"] == "AUTO"
        assert trace == []

    def test_duplicate_protection_precedes_approval_trace(self):
        """A prior-ledger duplicate remains blocked before trace generation."""
        run1 = APP / "data" / "run01.usg"
        write_prior(["PACCT4001BATCH4INV000000010000060000"])
        write_manifest(["/app/data/run01.usg"])
        write_usage(run1, [fmt_usage("ACCT4001", "BATCH4", "0001", 600000)])
        invoices, trace, summary = run_full()
        assert invoices == []
        assert trace == []
        assert summary["duplicate_batches_blocked"] == 1
