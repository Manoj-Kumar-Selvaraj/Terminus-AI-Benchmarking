"""Milestone 4 — checkpoint restart without partial invoices."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from billing_test_helpers import (  # noqa: E402
    APP,
    CHECKPOINT,
    INV,
    SUMMARY,
    TRACE,
    assert_checkpoint_layout,
    compile_program,
    fmt_usage,
    parse_invoices,
    parse_summary,
    parse_trace,
    run_batch,
    run_full,
    write_manifest,
    write_prior,
    write_usage,
    assert_output_record_widths,
)


def run_abend_restart(
    rows: list[str],
    abend_after: int,
    *,
    extra_file: tuple[Path, list[str]] | None = None,
) -> tuple[list[dict], list[dict], dict[str, int]]:
    """Compare true checkpoint resume outputs with an uninterrupted run."""
    from billing_test_helpers import clean_outputs

    run1 = APP / "data" / "run01.usg"
    write_prior([])
    manifest_paths = ["/app/data/run01.usg"]
    write_usage(run1, rows)
    if extra_file is not None:
        extra_path, extra_rows = extra_file
        manifest_paths.append(f"/app/data/{extra_path.name}")
        write_usage(extra_path, extra_rows)
    write_manifest(manifest_paths)
    _, trace_clean, summary_clean = run_full()
    invoices_clean = parse_invoices(INV.read_text())
    inv_bytes_clean = INV.read_bytes()
    trace_bytes_clean = TRACE.read_bytes()
    sum_bytes_clean = SUMMARY.read_bytes()

    clean_outputs()
    compile_program()
    abend = run_batch({"BILLING_ABEND_AFTER": str(abend_after)})
    assert abend.returncode == 99, abend.stderr or abend.stdout
    assert CHECKPOINT.exists()
    assert_checkpoint_layout()

    SUMMARY.unlink(missing_ok=True)
    compile_program()
    resumed = run_batch({"BILLING_RESTART": "1"})
    assert resumed.returncode == 0, resumed.stderr or resumed.stdout
    invoices_final = parse_invoices(INV.read_text())
    trace_final = parse_trace(TRACE.read_text())
    summary_final = parse_summary(SUMMARY.read_text())
    assert INV.read_bytes() == inv_bytes_clean, "invoice file not identical"
    assert TRACE.read_bytes() == trace_bytes_clean, "trace file not identical"
    assert SUMMARY.read_bytes() == sum_bytes_clean, "summary not identical"
    assert invoices_final == invoices_clean
    assert trace_final == trace_clean
    assert summary_final == summary_clean
    assert_output_record_widths()
    return invoices_clean, trace_clean, summary_clean


class TestMilestone4:
    def test_restart_matches_clean_run(self):
        """A mid-account restart preserves invoice, trace, and summary output."""
        rows = [
            fmt_usage("ACCT1001", "BATCH1", "0001", 100000),
            fmt_usage("ACCT1001", "BATCH1", "0002", 200000),
            fmt_usage("ACCT1001", "BATCH1", "0003", 300000),
        ]
        invoices, trace, summary = run_abend_restart(rows, abend_after=2)
        assert summary["invoices_posted"] == 1
        assert invoices[0]["total_cents"] == 600000
        assert trace == [{"account_id": "ACCT1001", "stage": "REGIONAL", "result": "PASS"}]

    def test_restart_mid_account_no_partial_invoice(self):
        """The pending account is emitted once with its complete aggregate."""
        rows = [
            fmt_usage("ACCT2001", "BATCH2", "0001", 400000),
            fmt_usage("ACCT2001", "BATCH2", "0002", 100000),
            fmt_usage("ACCT2001", "BATCH2", "0003", 50000),
        ]
        run_abend_restart(rows, abend_after=2)
        invoices = parse_invoices(INV.read_text())
        assert len(invoices) == 1
        assert invoices[0]["total_cents"] == 550000

    def test_restart_after_committed_account_preserves_order_and_numbers(self):
        """Restart appends a pending second account without replaying the first."""
        rows = [
            fmt_usage("ACCT3001", "BATCH3", "0001", 250000),
            fmt_usage("ACCT3001", "BATCH3", "0002", 350000),
            fmt_usage("ACCT4001", "BATCH4", "0001", 1000000),
            fmt_usage("ACCT4001", "BATCH4", "0002", 1100000),
        ]
        invoices, trace, summary = run_abend_restart(rows, abend_after=3)
        assert [row["account_id"] for row in invoices] == ["ACCT3001", "ACCT4001"]
        assert [row["invoice_no"] for row in invoices] == [1, 2]
        assert [row["total_cents"] for row in invoices] == [600000, 2100000]
        assert [row["stages"] for row in invoices] == ["REGIONAL", "REGIONAL+FINANCE"]
        assert [(row["account_id"], row["stage"]) for row in trace] == [
            ("ACCT3001", "REGIONAL"),
            ("ACCT4001", "REGIONAL"),
            ("ACCT4001", "FINANCE"),
        ]
        assert summary["invoices_posted"] == 2
        assert summary["usage_rows"] == 4

    def test_restart_abend_across_manifest_files(self):
        """An ABEND inside file two must not replay the completed first file."""
        run2 = APP / "data" / "run02.usg"
        rows1 = [fmt_usage("ACCT5001", "BATCH5", "0001", 300000)]
        rows2 = [
            fmt_usage("ACCT6001", "BATCH6", "0001", 400000),
            fmt_usage("ACCT6001", "BATCH6", "0002", 100000),
        ]
        invoices, trace, summary = run_abend_restart(
            rows1,
            abend_after=2,
            extra_file=(run2, rows2),
        )
        assert [row["account_id"] for row in invoices] == ["ACCT5001", "ACCT6001"]
        assert [row["approval_tier"] for row in invoices] == ["AUTO", "REGIONAL"]
        assert summary["usage_rows"] == 3
        assert trace == [{"account_id": "ACCT6001", "stage": "REGIONAL", "result": "PASS"}]

    def test_abend_after_first_row_writes_checkpoint(self):
        """ABEND on the first processed row still emits a valid checkpoint."""
        run1 = APP / "data" / "run01.usg"
        write_prior([])
        write_manifest(["/app/data/run01.usg"])
        write_usage(
            run1,
            [
                fmt_usage("ACCT7001", "BATCH7", "0001", 120000),
                fmt_usage("ACCT7001", "BATCH7", "0002", 130000),
            ],
        )
        from billing_test_helpers import clean_outputs

        clean_outputs()
        compile_program()
        abend = run_batch({"BILLING_ABEND_AFTER": "1"})
        assert abend.returncode == 99
        assert_checkpoint_layout()
        assert CHECKPOINT.read_text()[8:16].strip() == "ACCT7001"

    def test_restart_without_checkpoint_fails_closed(self):
        """Restart must not succeed when checkpoint evidence is missing."""
        run1 = APP / "data" / "run01.usg"
        write_prior([])
        write_manifest(["/app/data/run01.usg"])
        write_usage(run1, [fmt_usage("ACCT8001", "BATCH8", "0001", 150000)])
        from billing_test_helpers import clean_outputs

        clean_outputs()
        compile_program()
        resumed = run_batch({"BILLING_RESTART": "1"})
        assert resumed.returncode != 0
