"""Verifier tests for realtime telemetry incident credit reconciliation — milestone 4."""

import csv
import subprocess
from pathlib import Path


APP = Path("/app")
GO = Path("/usr/local/go/bin/go")
BIN = APP / "build" / "stream-incident-reconcile"
PLAYBACKS = APP / "data" / "playbacks.csv"
CREDITS = APP / "data" / "credits.csv"
CUTOFFS = APP / "config" / "region_windows.csv"
REASONS = APP / "config" / "reasons.csv"
REPORT = APP / "out" / "incident_credit_report.csv"
SUMMARY = APP / "out" / "incident_credit_summary.txt"


def build_program():
    """Compile the Go reconciler for one verifier scenario."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile/main.go"], check=True, cwd=APP, timeout=60)


def write_csv(path, header, rows):
    """Write one CSV fixture."""
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(playbacks, credits, windows, reasons=None):
    """Overwrite all input CSVs at runtime."""
    write_csv(PLAYBACKS, ["incident_id", "severity_id", "severity", "minutes", "start_utc", "end_utc", "status", "region"], playbacks)
    write_csv(CREDITS, ["credit_id", "incident_id", "severity_id", "severity", "minutes", "event_utc", "reason", "region"], credits)
    write_csv(CUTOFFS, ["region", "window_utc", "state"], windows)
    if reasons is not None:
        write_csv(REASONS, ["reason", "eligible", "priority"], reasons)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the reconciler and parse report and summary outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        summary[key] = int(value)
    return rows, summary


# --- Milestone 3 regression tests ---

class TestMilestone3Regression:
    def test_all_gates_still_enforced(self):
        """All M1-M3 gates remain in effect under M4 policy loading."""
        build_program()
        write_inputs(
            [
                ["STREAM-REG-1", "ACCT-1", "CMEDIUM", "10", "20260528100000", "20260528101000", "POSTED", "NA"],
                ["STREAM-REG-2", "ACCT-2", "LOW", "20", "20260528100000", "20260528102000", "DRAFT", "NA"],
            ],
            [
                ["CR-REG-1", "STREAM-REG-1", "ACCT-1", "CMEDIUM", "10", "20260528101100", "BUFFER", "NA"],
                ["CR-REG-2", "STREAM-REG-2", "ACCT-2", "LOW", "20", "20260528102100", "BUFFER", "NA"],
            ],
            [["NA", "20260528235959", "OPEN"]],
            [["BUFFER", "Y", "2"], ["DUPLICATELICATE", "Y", "3"], ["CREDIT", "Y", "1"], ["INFO", "N", "9"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[1]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 1
        assert summary["matched_minutes"] == 10

    def test_aliases_and_window_state_regression(self):
        """Alias normalization and OPEN-only window state must still be enforced."""
        build_program()
        write_inputs(
            [
                ["STREAM-ALIAS-REG", "ACCT-1", "CMEDIUM", "30", "20260528100000", "20260528103000", "POSTED", "NA"],
                ["STREAM-CLOS-REG", "ACCT-2", "LOW", "15", "20260528100000", "20260528101500", "POSTED", "EU"],
            ],
            [
                ["CR-ALIAS-REG", "STREAM-ALIAS-REG", "ACCT-1", "MEDIUM", "30", "20260528103100", "CREDIT", "NA"],
                ["CR-CLOS-REG", "STREAM-CLOS-REG", "ACCT-2", "PHONE", "15", "20260528101600", "CREDIT", "EU"],
            ],
            [["NA", "20260528235959", "OPEN"], ["EU", "20260528235959", "CLOS"]],
            [["BUFFER", "Y", "2"], ["DUPLICATELICATE", "Y", "3"], ["CREDIT", "Y", "1"], ["INFO", "N", "9"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[1]["status"] == "UNMATCHED"
        assert summary["matched_minutes"] == 30

    def test_latest_end_utc_tie_break_regression(self):
        """Latest selection must preserve an earlier playback for an earlier follow-up credit."""
        build_program()
        write_inputs(
            [
                ["STREAM-LATE-1", "ACCT-1", "CMEDIUM", "25", "20260528100000", "20260528102500", "POSTED", "NA"],
                ["STREAM-LATE-1", "ACCT-1", "CMEDIUM", "25", "20260528100000", "20260528104000", "POSTED", "NA"],
            ],
            [
                ["CR-LATE-FIRST", "STREAM-LATE-1", "ACCT-1", "CMEDIUM", "25", "20260528104100", "BUFFER", "NA"],
                ["CR-LATE-FOLLOWUP", "STREAM-LATE-1", "ACCT-1", "CMEDIUM", "25", "20260528103000", "BUFFER", "NA"],
            ],
            [["NA", "20260528235959", "OPEN"]],
            [["BUFFER", "Y", "2"], ["CREDIT", "Y", "1"]],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert summary["matched_count"] == 2
        assert summary["matched_minutes"] == 50


# --- Milestone 4 tests ---

class TestMilestone4:
    def test_disabled_reason_blocks_credit(self):
        """A reason with eligible=N in reasons.csv must block the credit even when other gates pass."""
        build_program()
        write_inputs(
            [["STREAM-DIS-1", "ACCT-1", "CMEDIUM", "10", "20260528100000", "20260528101000", "POSTED", "NA"]],
            [["CR-DIS", "STREAM-DIS-1", "ACCT-1", "CMEDIUM", "10", "20260528101100", "INFO", "NA"]],
            [["NA", "20260528235959", "OPEN"]],
            [["BUFFER", "Y", "2"], ["INFO", "N", "9"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_absent_reason_blocks_credit(self):
        """A reason not present in reasons.csv at all must block the credit."""
        build_program()
        write_inputs(
            [["STREAM-ABS-1", "ACCT-1", "LOW", "15", "20260528100000", "20260528101500", "POSTED", "NA"]],
            [["CR-ABS", "STREAM-ABS-1", "ACCT-1", "LOW", "15", "20260528101600", "NEWREASON", "NA"]],
            [["NA", "20260528235959", "OPEN"]],
            [["BUFFER", "Y", "2"], ["CREDIT", "Y", "1"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_any_reason_matches_any_eligible_playback(self):
        """Credit with reason ANY should match a playback that all other gates pass."""
        build_program()
        write_inputs(
            [["STREAM-ANY-1", "ACCT-1", "BROWSER", "40", "20260528100000", "20260528104000", "POSTED", "NA"]],
            [["CR-ANY", "STREAM-ANY-1", "ACCT-1", "WEBAPP", "40", "20260528104100", "ANY", "NA"]],
            [["NA", "20260528235959", "OPEN"]],
            [["BUFFER", "Y", "2"], ["CREDIT", "Y", "1"], ["INFO", "N", "9"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["severity"] == "BROWSER"
        assert rows[0]["reason"] == "ANY"
        assert summary["matched_count"] == 1
        assert summary["matched_minutes"] == 40

    def test_any_reason_emits_any_in_report(self):
        """Report must emit 'ANY' as the reason field for a matched ANY credit."""
        build_program()
        write_inputs(
            [["STREAM-ANYOUT-1", "ACCT-1", "LOW", "20", "20260528100000", "20260528102000", "POSTED", "NA"]],
            [["CR-ANYOUT", "STREAM-ANYOUT-1", "ACCT-1", "PHONE", "20", "20260528102100", "ANY", "NA"]],
            [["NA", "20260528235959", "OPEN"]],
            [["BUFFER", "Y", "2"], ["CREDIT", "Y", "1"]],
        )
        rows, summary = run_program()

        assert rows[0]["reason"] == "ANY"
        assert rows[0]["status"] == "MATCHED"

    def test_any_reason_with_latest_end_utc_tie_break(self):
        """ANY must consume the latest playback and leave the earlier row for a timed follow-up."""
        build_program()
        write_inputs(
            [
                ["STREAM-ANYTIE-1", "ACCT-1", "CMEDIUM", "30", "20260528100000", "20260528102000", "POSTED", "NA"],
                ["STREAM-ANYTIE-1", "ACCT-1", "CMEDIUM", "30", "20260528100000", "20260528105000", "POSTED", "NA"],
            ],
            [
                ["CR-ANYTIE-LATEST", "STREAM-ANYTIE-1", "ACCT-1", "CMEDIUM", "30", "20260528105100", "ANY", "NA"],
                ["CR-ANYTIE-EARLIER", "STREAM-ANYTIE-1", "ACCT-1", "CMEDIUM", "30", "20260528103000", "ANY", "NA"],
            ],
            [["NA", "20260528235959", "OPEN"]],
            [["BUFFER", "Y", "2"], ["CREDIT", "Y", "1"]],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["reason"] for row in rows] == ["ANY", "ANY"]
        assert summary["matched_count"] == 2
        assert summary["matched_minutes"] == 60

    def test_any_consumes_one_playback_per_credit(self):
        """Each ANY credit must consume exactly one playback; the same playback cannot match two credits."""
        build_program()
        write_inputs(
            [["STREAM-ANYCONSUME-1", "ACCT-1", "CMEDIUM", "10", "20260528100000", "20260528101000", "POSTED", "NA"]],
            [
                ["CR-ANY-A", "STREAM-ANYCONSUME-1", "ACCT-1", "CMEDIUM", "10", "20260528101100", "ANY", "NA"],
                ["CR-ANY-B", "STREAM-ANYCONSUME-1", "ACCT-1", "CMEDIUM", "10", "20260528101200", "ANY", "NA"],
            ],
            [["NA", "20260528235959", "OPEN"]],
            [["BUFFER", "Y", "2"], ["CREDIT", "Y", "1"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[1]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 1
        assert summary["unmatched_count"] == 1

    def test_dynamic_reason_eligibility_can_be_changed(self):
        """Enabling a previously disabled reason in reasons.csv must allow it to match."""
        build_program()
        write_inputs(
            [["STREAM-DYN-1", "ACCT-1", "BROWSER", "50", "20260528100000", "20260528105000", "POSTED", "NA"]],
            [["CR-DYN", "STREAM-DYN-1", "ACCT-1", "WEBAPP", "50", "20260528105100", "INFO", "NA"]],
            [["NA", "20260528235959", "OPEN"]],
            [["INFO", "Y", "1"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert summary["matched_minutes"] == 50

    def test_any_with_closed_window_remains_unmatched(self):
        """ANY credit in a CLOSED window region must still be blocked by the window gate."""
        build_program()
        write_inputs(
            [["STREAM-ANYCLOS-1", "ACCT-1", "LOW", "25", "20260528100000", "20260528102500", "POSTED", "EU"]],
            [["CR-ANYCLOS", "STREAM-ANYCLOS-1", "ACCT-1", "PHONE", "25", "20260528102600", "ANY", "EU"]],
            [["EU", "20260528235959", "CLOS"]],
            [["BUFFER", "Y", "2"], ["CREDIT", "Y", "1"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_specific_reason_still_exact_match_required(self):
        """Non-ANY reason with partial or alias match must not succeed; exact string is required."""
        build_program()
        write_inputs(
            [["STREAM-EXACT-1", "ACCT-1", "CMEDIUM", "20", "20260528100000", "20260528102000", "POSTED", "NA"]],
            [
                ["CR-EXACT-OK", "STREAM-EXACT-1", "ACCT-1", "CMEDIUM", "20", "20260528102100", "BUFFER", "NA"],
                ["CR-EXACT-BAD", "STREAM-EXACT-1", "ACCT-1", "CMEDIUM", "20", "20260528102200", "buffer", "NA"],
            ],
            [["NA", "20260528235959", "OPEN"]],
            [["BUFFER", "Y", "2"], ["CREDIT", "Y", "1"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[1]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 1

    def test_mixed_any_and_specific_credits_same_batch(self):
        """ANY and specific reason credits should reconcile correctly in the same batch."""
        build_program()
        write_inputs(
            [
                ["STREAM-MIX-1", "ACCT-1", "CMEDIUM", "10", "20260528100000", "20260528101000", "POSTED", "NA"],
                ["STREAM-MIX-2", "ACCT-2", "LOW", "20", "20260528100000", "20260528102000", "POSTED", "NA"],
                ["STREAM-MIX-3", "ACCT-3", "BROWSER", "30", "20260528100000", "20260528103000", "POSTED", "NA"],
            ],
            [
                ["CR-MIX-A", "STREAM-MIX-1", "ACCT-1", "CMEDIUM", "10", "20260528101100", "BUFFER", "NA"],
                ["CR-MIX-B", "STREAM-MIX-2", "ACCT-2", "LOW", "20", "20260528102100", "ANY", "NA"],
                ["CR-MIX-C", "STREAM-MIX-3", "ACCT-3", "WEBAPP", "30", "20260528103100", "INFO", "NA"],
            ],
            [["NA", "20260528235959", "OPEN"]],
            [["BUFFER", "Y", "2"], ["CREDIT", "Y", "1"], ["INFO", "N", "9"]],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 2
        assert summary["matched_minutes"] == 30
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_minutes"] == 30

    def test_case_insensitive_eligible_y_enables_reason(self):
        """Reason rows with lowercase eligible=y must enable matching case-insensitively."""
        build_program()
        write_inputs(
            [["STREAM-CI-1", "ACCT-1", "BROWSER", "35", "20260528100000", "20260528103500", "POSTED", "NA"]],
            [["CR-CI", "STREAM-CI-1", "ACCT-1", "WEBAPP", "35", "20260528103600", "BUFFER", "NA"]],
            [["NA", "20260528235959", "OPEN"]],
            [["BUFFER", " y ", "1"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["reason"] == "BUFFER"
        assert summary["matched_count"] == 1

    def test_any_equal_end_utc_tie_uses_earliest_playback_row(self):
        """ANY credits must consume earliest playback rows when end_utc values tie."""
        build_program()
        write_inputs(
            [
                ["STREAM-ANYEQ-1", "ACCT-1", "CMEDIUM", "22", "20260528100000", "20260528102200", "POSTED", "NA"],
                ["STREAM-ANYEQ-1", "ACCT-1", "CMEDIUM", "22", "20260528100000", "20260528102200", "POSTED", "NA"],
            ],
            [
                ["CR-ANYEQ-A", "STREAM-ANYEQ-1", "ACCT-1", "MEDIUM", "22", "20260528102300", "ANY", "NA"],
                ["CR-ANYEQ-B", "STREAM-ANYEQ-1", "ACCT-1", "MEDIUM", "22", "20260528102400", "ANY", "NA"],
            ],
            [["NA", "20260528235959", "OPEN"]],
            [["BUFFER", "Y", "2"], ["CREDIT", "Y", "1"]],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["reason"] for row in rows] == ["ANY", "ANY"]
        assert summary["matched_count"] == 2
