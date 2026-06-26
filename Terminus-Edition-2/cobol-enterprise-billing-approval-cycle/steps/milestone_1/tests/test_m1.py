"""Milestone 1 — approval tier must use account billing total."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from billing_test_helpers import APP, fmt_usage, run_full, write_manifest, write_prior, write_usage


class TestMilestone1:
    def test_dual_tier_requires_aggregate_not_last_line(self):
        """Small lines summing above dual threshold must route to DUAL approval."""
        run1 = APP / "data" / "run01.usg"
        write_prior([])
        write_manifest(["/app/data/run01.usg"])
        write_usage(
            run1,
            [
                fmt_usage("ACCT1001", "BATCH1", "0001", 800000),
                fmt_usage("ACCT1001", "BATCH1", "0002", 800000),
                fmt_usage("ACCT1001", "BATCH1", "0003", 800000),
            ],
        )
        invoices, trace, summary = run_full()
        assert summary["invoices_posted"] == 1
        assert invoices[0]["total_cents"] == 2400000
        assert invoices[0]["approval_tier"] == "DUAL"
        assert invoices[0]["stages"] == "REGIONAL"
        assert trace == [{"account_id": "ACCT1001", "stage": "REGIONAL", "result": "PASS"}]
        assert summary["usage_rows"] == 3

    def test_regional_tier_from_account_total(self):
        """Regional totals produce one approved regional trace."""
        run1 = APP / "data" / "run01.usg"
        write_prior([])
        write_manifest(["/app/data/run01.usg"])
        write_usage(
            run1,
            [
                fmt_usage("ACCT2001", "BATCH2", "0001", 100000),
                fmt_usage("ACCT2001", "BATCH2", "0002", 450000),
            ],
        )
        invoices, trace, summary = run_full()
        assert invoices[0]["approval_tier"] == "REGIONAL"
        assert invoices[0]["total_cents"] == 550000
        assert trace == [{"account_id": "ACCT2001", "stage": "REGIONAL", "result": "PASS"}]
        assert summary["invoices_posted"] == 1

    def test_auto_tier_when_aggregate_below_regional(self):
        """AUTO accounts retain an automatic stage without approval trace rows."""
        run1 = APP / "data" / "run01.usg"
        write_prior([])
        write_manifest(["/app/data/run01.usg"])
        write_usage(
            run1,
            [
                fmt_usage("ACCT3001", "BATCH3", "0001", 200000),
                fmt_usage("ACCT3001", "BATCH3", "0002", 200000),
            ],
        )
        invoices, trace, _ = run_full()
        assert invoices[0]["approval_tier"] == "AUTO"
        assert invoices[0]["stages"] == "AUTO"
        assert trace == []

    def test_summary_keys_present(self):
        """Milestone 1 emits the complete stable summary schema."""
        run1 = APP / "data" / "run01.usg"
        write_prior([])
        write_manifest(["/app/data/run01.usg"])
        write_usage(run1, [fmt_usage("ACCT4001", "BATCH4", "0001", 10000)])
        _, _, summary = run_full()
        assert set(summary.keys()) == {
            "invoices_posted",
            "total_billed_cents",
            "usage_rows",
            "duplicate_batches_blocked",
            "checkpoint_commits",
        }
        assert summary["duplicate_batches_blocked"] == 0
        assert summary["checkpoint_commits"] == 0

    def test_account_break_resets_aggregate_state(self):
        """A second account starts a fresh aggregate and invoice sequence."""
        run1 = APP / "data" / "run01.usg"
        write_prior([])
        write_manifest(["/app/data/run01.usg"])
        write_usage(
            run1,
            [
                fmt_usage("ACCT5001", "BATCH5", "0001", 300000),
                fmt_usage("ACCT5002", "BATCH6", "0001", 600000),
            ],
        )
        invoices, trace, summary = run_full()
        assert [row["account_id"] for row in invoices] == ["ACCT5001", "ACCT5002"]
        assert [row["approval_tier"] for row in invoices] == ["AUTO", "REGIONAL"]
        assert [row["total_cents"] for row in invoices] == [300000, 600000]
        assert [row["invoice_no"] for row in invoices] == [1, 2]
        assert trace == [{"account_id": "ACCT5002", "stage": "REGIONAL", "result": "PASS"}]
        assert summary["total_billed_cents"] == 900000

    def test_negative_amount_excluded_from_aggregate(self):
        """Negative usage rows must not reduce the account aggregate total."""
        run1 = APP / "data" / "run01.usg"
        write_prior([])
        write_manifest(["/app/data/run01.usg"])
        write_usage(
            run1,
            [
                fmt_usage("ACCT2001", "BATCH9", "0001", 600000),
                fmt_usage("ACCT2001", "BATCH9", "0002", -100000),
            ],
        )
        invoices, trace, _ = run_full()
        assert invoices[0]["total_cents"] == 600000
        assert invoices[0]["approval_tier"] == "REGIONAL"
        assert trace == [{"account_id": "ACCT2001", "stage": "REGIONAL", "result": "PASS"}]
