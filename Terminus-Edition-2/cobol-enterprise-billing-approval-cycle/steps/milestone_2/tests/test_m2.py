"""Milestone 2 — prior-run ledger duplicate batch protection."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from billing_test_helpers import APP, fmt_usage, run_full, write_manifest, write_prior, write_usage


class TestMilestone2:
    def test_prior_ledger_blocks_duplicate_batch(self):
        """A matching account and batch suppresses both invoice and trace output."""
        run1 = APP / "data" / "run01.usg"
        write_prior(["PACCT1001BATCH1INV000000010000050000"])
        write_manifest(["/app/data/run01.usg"])
        write_usage(run1, [fmt_usage("ACCT1001", "BATCH1", "0001", 50000)])
        invoices, trace, summary = run_full()
        assert summary["invoices_posted"] == 0
        assert summary["duplicate_batches_blocked"] == 1
        assert invoices == []
        assert trace == []

    def test_new_batch_still_posts(self):
        """A new batch for an existing account remains billable."""
        run1 = APP / "data" / "run01.usg"
        write_prior(["PACCT1001BATCH1INV000000010000050000"])
        write_manifest(["/app/data/run01.usg"])
        write_usage(run1, [fmt_usage("ACCT1001", "BATCH2", "0001", 120000)])
        invoices, _, summary = run_full()
        assert summary["invoices_posted"] == 1
        assert summary["duplicate_batches_blocked"] == 0
        assert invoices[0]["total_cents"] == 120000

    def test_duplicate_only_when_account_and_batch_match(self):
        """The same batch id on another account is not a duplicate."""
        run1 = APP / "data" / "run01.usg"
        write_prior(["PACCT1001BATCH1INV000000010000050000"])
        write_manifest(["/app/data/run01.usg"])
        write_usage(run1, [fmt_usage("ACCT2001", "BATCH1", "0001", 90000)])
        invoices, _, summary = run_full()
        assert summary["invoices_posted"] == 1
        assert summary["duplicate_batches_blocked"] == 0
