"""Milestone 4 tests — checkpoint restart after ABEND."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from merge_test_helpers import (  # noqa: E402
    APP,
    CHECKPOINT,
    CTL,
    SUMMARY,
    compile_program,
    fmt_stmt,
    parse_control_rows,
    parse_summary,
    run_batch,
    run_full,
    write_manifest,
    write_stream,
)


def run_abend_restart(rows: list[str], abend_after: int) -> tuple[list[dict], dict[str, int]]:
    """Run a clean merge, then ABEND+restart, asserting outputs match."""
    run1 = APP / "data" / "run01.stm"
    write_manifest(["/app/data/run01.stm"])
    write_stream(run1, rows)

    clean = run_full()
    rows_clean, summary_clean = clean

    from merge_test_helpers import clean_outputs

    clean_outputs()
    compile_program()
    abend = run_batch({"STMT_MERGE_ABEND_AFTER": str(abend_after)})
    assert abend.returncode == 99, abend.stderr or abend.stdout
    assert CHECKPOINT.exists() and CHECKPOINT.read_text().strip()

    compile_program()
    resumed = run_batch({"STMT_MERGE_RESTART": "1"})
    assert resumed.returncode == 0, resumed.stderr or resumed.stdout

    rows_final = parse_control_rows(CTL.read_text())
    summary_final = parse_summary(SUMMARY.read_text())
    assert summary_final == summary_clean
    assert rows_final == rows_clean
    return rows_clean, summary_clean


def run_abend_restart_multi(
    manifest_paths: list[str],
    streams: dict[Path, list[str]],
    abend_after: int,
) -> tuple[list[dict], dict[str, int]]:
    """Run a clean multi-file merge, then ABEND+restart, asserting outputs match."""
    write_manifest(manifest_paths)
    for path, rows in streams.items():
        write_stream(path, rows)

    clean = run_full()
    rows_clean, summary_clean = clean

    from merge_test_helpers import clean_outputs

    clean_outputs()
    compile_program()
    abend = run_batch({"STMT_MERGE_ABEND_AFTER": str(abend_after)})
    assert abend.returncode == 99, abend.stderr or abend.stdout
    assert CHECKPOINT.exists() and CHECKPOINT.read_text().strip()

    compile_program()
    resumed = run_batch({"STMT_MERGE_RESTART": "1"})
    assert resumed.returncode == 0, resumed.stderr or resumed.stdout

    rows_final = parse_control_rows(CTL.read_text())
    summary_final = parse_summary(SUMMARY.read_text())
    assert summary_final == summary_clean
    assert rows_final == rows_clean
    return rows_clean, summary_clean


class TestMilestone4:
    def test_restart_after_abend_matches_uninterrupted_run(self):
        """ABEND then restart must equal a single clean merge."""
        rows = [
            fmt_stmt("ACCT1001", "20260401", "00001", "DR", 1000),
            fmt_stmt("ACCT1001", "20260402", "00001", "DR", 2000),
            fmt_stmt("ACCT1001", "20260403", "00001", "DR", 300),
        ]
        _, summary = run_abend_restart(rows, abend_after=2)
        assert summary["committed_groups"] == 3
        assert summary["total_debit_cents"] == 3300
        assert summary["statement_rows"] == 3

    def test_restart_preserves_pending_group_state(self):
        """Restart must finish a partially accumulated group without duplicating committed rows."""
        rows = [
            fmt_stmt("ACCT1001", "20260401", "00001", "DR", 500),
            fmt_stmt("ACCT2001", "20260401", "00001", "DR", 700),
            fmt_stmt("ACCT2001", "20260401", "00002", "CR", 100),
        ]
        run_abend_restart(rows, abend_after=2)
        final_rows = parse_control_rows(CTL.read_text())
        assert len(final_rows) == 2
        assert final_rows[0] == {
            "account_id": "ACCT1001",
            "stmt_date": "20260401",
            "debit_cents": 500,
            "credit_cents": 0,
            "stmt_count": 1,
            "status": "C",
        }
        assert final_rows[1]["account_id"] == "ACCT2001"
        assert final_rows[1]["debit_cents"] == 700
        assert final_rows[1]["credit_cents"] == 100
        assert final_rows[1]["stmt_count"] == 2

    def test_restart_requires_checkpoint_file(self):
        """Restart with STMT_MERGE_RESTART=1 must fail when checkpoint.dat is missing."""
        run1 = APP / "data" / "run01.stm"
        write_manifest(["/app/data/run01.stm"])
        write_stream(
            run1,
            [
                fmt_stmt("ACCT1001", "20260401", "00001", "DR", 500),
                fmt_stmt("ACCT2001", "20260401", "00001", "DR", 700),
            ],
        )

        from merge_test_helpers import clean_outputs

        clean_outputs()
        compile_program()
        abend = run_batch({"STMT_MERGE_ABEND_AFTER": "1"})
        assert abend.returncode == 99
        assert CHECKPOINT.exists()

        CHECKPOINT.unlink()
        compile_program()
        resumed = run_batch({"STMT_MERGE_RESTART": "1"})
        assert resumed.returncode != 0

    def test_restart_rejects_unreadable_checkpoint(self):
        """Restart with STMT_MERGE_RESTART=1 must fail when checkpoint.dat is unreadable."""
        run1 = APP / "data" / "run01.stm"
        write_manifest(["/app/data/run01.stm"])
        write_stream(
            run1,
            [
                fmt_stmt("ACCT1001", "20260401", "00001", "DR", 500),
                fmt_stmt("ACCT2001", "20260401", "00001", "DR", 700),
            ],
        )

        from merge_test_helpers import clean_outputs

        clean_outputs()
        compile_program()
        abend = run_batch({"STMT_MERGE_ABEND_AFTER": "1"})
        assert abend.returncode == 99
        assert CHECKPOINT.exists()

        CHECKPOINT.write_text("")
        compile_program()
        resumed = run_batch({"STMT_MERGE_RESTART": "1"})
        assert resumed.returncode != 0

    def test_restart_multi_file_resumes_second_stream(self):
        """Checkpoint resume must continue into the next manifest stream after ABEND."""
        run1 = APP / "data" / "run01.stm"
        run2 = APP / "data" / "run02.stm"
        _, summary = run_abend_restart_multi(
            ["/app/data/run01.stm", "/app/data/run02.stm"],
            {
                run1: [fmt_stmt("ACCT1001", "20260401", "00001", "DR", 100, "RUN01")],
                run2: [fmt_stmt("ACCT2001", "20260401", "00001", "DR", 200, "RUN02")],
            },
            abend_after=1,
        )
        assert summary["committed_groups"] == 2
        assert summary["total_debit_cents"] == 300

    def test_checkpoint_written_on_abend(self):
        """Simulated ABEND must leave a checkpoint file for operators."""
        run1 = APP / "data" / "run01.stm"
        write_manifest(["/app/data/run01.stm"])
        write_stream(run1, [fmt_stmt("ACCT3001", "20260401", "00001", "DR", 900)])
        from merge_test_helpers import clean_outputs

        clean_outputs()
        compile_program()
        proc = run_batch({"STMT_MERGE_ABEND_AFTER": "1"})
        assert proc.returncode == 99
        assert CHECKPOINT.stat().st_size > 0
