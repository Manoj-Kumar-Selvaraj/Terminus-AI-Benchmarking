"""Verifier tests for milestone 2 pass-window behavior."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
CATALOG = APP / "data/catalog.psv"
AUDITS = APP / "data/audits.psv"
WINDOWS = APP / "config/pass_windows.psv"
RULES = APP / "src/audit_rules.pli"
REPORT = APP / "out/audit_report.csv"
SUMMARY = APP / "out/audit_summary.txt"
CONSUMPTION = APP / "out/catalog_consumption.psv"

CAT_HDR = ["frame_id", "craft_id", "channel", "payload_hash", "recv_ts", "state", "service_class"]
AUD_HDR = ["audit_id", "frame_id", "craft_id", "channel", "payload_hash", "audit_ts", "verdict_code", "service_class"]


def write_psv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("|".join(header) + "\n" + "\n".join("|".join(row) for row in rows) + ("\n" if rows else ""))


def write_rules(state="OPEN", open_state="OPEN", verdicts=("OK", "WATCH", "DONE"), aliases=("a=>ALPHA", "tm=>TM", "x=>XLINK")):
    RULES.write_text(
        "\n".join(
            [
                f"DCL ELIGIBLE_STATE CHAR(12) INIT('{state}');",
                f"DCL OPEN_PASS_STATE CHAR(8) INIT('{open_state}');",
                f"DCL VERDICT_A CHAR(12) INIT('{verdicts[0]}');",
                f"DCL VERDICT_B CHAR(12) INIT('{verdicts[1]}');",
                f"DCL VERDICT_C CHAR(12) INIT('{verdicts[2]}');",
                *[f"DCL ALIAS_{i + 1} CHAR(20) INIT('{alias}');" for i, alias in enumerate(aliases)],
            ]
        )
        + "\n"
    )


def write_inputs(catalog, audits, windows, window_header=("craft_id", "open_ts", "close_ts", "state")):
    write_psv(CATALOG, CAT_HDR, catalog)
    write_psv(AUDITS, AUD_HDR, audits)
    write_psv(WINDOWS, list(window_header), windows)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)
    CONSUMPTION.unlink(missing_ok=True)


def run_program():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="|"))
    summary = {key: int(value) for key, value in (line.split("=", 1) for line in SUMMARY.read_text().splitlines())}
    with CONSUMPTION.open(newline="") as handle:
        consumption = list(csv.DictReader(handle, delimiter="|"))
    return rows, summary, consumption


class TestMilestone2:
    """Pass-window eligibility and cumulative milestone 1 regression."""

    def test_audit_inside_pass_window_accepts_with_report_columns(self):
        """An audit inside an open pass window is accepted."""
        write_rules()
        write_inputs(
            [["FRM-A", "ALPHA", "D1", "h1", "20260612120000", "OPEN", "TM"]],
            [["AUD-W", "FRM-A", "ALPHA", "D1", "h1", "20260612120500", "OK", "TM"]],
            [["ALPHA", "20260612115900", "20260612123000", "OPEN"]],
        )
        rows, summary, _consumption = run_program()
        assert rows[0]["status"] == "ACCEPTED"
        assert rows[0]["audit_id"] == "AUD-W"
        assert rows[0]["service_class"] == "TM"
        assert summary["matched_count"] == 1

    def test_recv_before_or_after_window_rejects(self):
        """Catalog receive times outside the pass window are rejected."""
        write_rules()
        write_inputs(
            [
                ["FRM-BEFORE", "ALPHA", "D1", "h2", "20260612115859", "OPEN", "TM"],
                ["FRM-AFTER", "ALPHA", "D1", "h3", "20260612123001", "OPEN", "TM"],
            ],
            [
                ["AUD-BEFORE", "FRM-BEFORE", "ALPHA", "D1", "h2", "20260612120000", "OK", "TM"],
                ["AUD-AFTER", "FRM-AFTER", "ALPHA", "D1", "h3", "20260612123001", "OK", "TM"],
            ],
            [["ALPHA", "20260612115900", "20260612123000", "OPEN"]],
        )
        assert [row["status"] for row in run_program()[0]] == ["REJECTED", "REJECTED"]

    def test_audit_before_recv_or_after_close_rejects(self):
        """Audit timestamps must follow receive time and not exceed close time."""
        write_rules()
        write_inputs(
            [
                ["FRM-EARLYAUD", "ALPHA", "D1", "h2", "20260612120010", "OPEN", "TM"],
                ["FRM-LATEAUD", "ALPHA", "D1", "h3", "20260612120000", "OPEN", "TM"],
            ],
            [
                ["AUD-EARLY", "FRM-EARLYAUD", "ALPHA", "D1", "h2", "20260612120009", "OK", "TM"],
                ["AUD-LATE", "FRM-LATEAUD", "ALPHA", "D1", "h3", "20260612123001", "OK", "TM"],
            ],
            [["ALPHA", "20260612115900", "20260612123000", "OPEN"]],
        )
        assert [row["status"] for row in run_program()[0]] == ["REJECTED", "REJECTED"]

    def test_closed_missing_and_unlisted_windows_reject(self):
        """Closed or unavailable pass windows fail closed."""
        write_rules()
        write_inputs(
            [
                ["FRM-CLOSED", "ALPHA", "D1", "h1", "20260612120000", "OPEN", "TM"],
                ["FRM-MISSING", "BETA", "D1", "h2", "20260612120000", "OPEN", "TM"],
            ],
            [
                ["AUD-CLOSED", "FRM-CLOSED", "ALPHA", "D1", "h1", "20260612120500", "OK", "TM"],
                ["AUD-MISSING", "FRM-MISSING", "BETA", "D1", "h2", "20260612120500", "OK", "TM"],
            ],
            [["ALPHA", "20260612115900", "20260612123000", "CLOSED"]],
        )
        assert [row["status"] for row in run_program()[0]] == ["REJECTED", "REJECTED"]

    def test_malformed_window_and_malformed_timestamps_reject_without_crash(self):
        """Malformed windows and timestamps reject safely."""
        write_rules()
        write_inputs(
            [
                ["FRM-BADRECV", "ALPHA", "D1", "h1", "badrecv", "OPEN", "TM"],
                ["FRM-BADAUD", "ALPHA", "D1", "h2", "20260612120000", "OPEN", "TM"],
                ["FRM-BADWIN", "BETA", "D1", "h3", "20260612120000", "OPEN", "TM"],
            ],
            [
                ["AUD-BADRECV", "FRM-BADRECV", "ALPHA", "D1", "h1", "20260612120500", "OK", "TM"],
                ["AUD-BADAUD", "FRM-BADAUD", "ALPHA", "D1", "h2", "badaudit", "OK", "TM"],
                ["AUD-BADWIN", "FRM-BADWIN", "BETA", "D1", "h3", "20260612120500", "OK", "TM"],
            ],
            [
                ["ALPHA", "20260612115900", "20260612123000", "OPEN"],
                ["BETA", "notatime", "20260612123000", "OPEN"],
            ],
        )
        rows, summary, _consumption = run_program()
        assert [row["status"] for row in rows] == ["REJECTED", "REJECTED", "REJECTED"]
        assert summary["rejected_count"] == 3

    def test_alias_normalization_before_pass_window_lookup_with_channel_column(self):
        """Canonical craft and channel values drive window lookup."""
        write_rules(aliases=("a=>ALPHA", "tm=>TM", "sci=>SCIENCE"))
        write_inputs(
            [["FRM-A", "a", "tm", "h1", "20260612120000", "OPEN", "sci"]],
            [["AUD-A", "FRM-A", "ALPHA", "TM", "h1", "20260612120500", "OK", "SCIENCE"]],
            [["ALPHA", "TM", "20260612115900", "20260612123000", "OPEN"]],
            window_header=("craft_id", "channel", "open_ts", "close_ts", "state"),
        )
        rows, _summary, _consumption = run_program()
        assert rows[0]["status"] == "ACCEPTED"
        assert rows[0]["service_class"] == "SCIENCE"

    def test_consumption_and_candidate_ordering_still_apply_under_windows(self):
        """Windowed selection preserves latest-time and physical-row ordering."""
        write_rules()
        write_inputs(
            [
                ["FRM-A", "ALPHA", "D1", "h1", "20260612120000", "OPEN", "TM"],
                ["FRM-A", "ALPHA", "D1", "h1", "20260612120100", "OPEN", "TM"],
                ["FRM-T", "ALPHA", "D1", "h2", "20260612120200", "OPEN", "TM"],
                ["FRM-T", "ALPHA", "D1", "h2", "20260612120200", "OPEN", "TM"],
            ],
            [
                ["AUD-1", "FRM-A", "ALPHA", "D1", "h1", "20260612120500", "OK", "TM"],
                ["AUD-2", "FRM-A", "ALPHA", "D1", "h1", "20260612120600", "OK", "TM"],
                ["AUD-3", "FRM-T", "ALPHA", "D1", "h2", "20260612120700", "OK", "TM"],
                ["AUD-4", "FRM-T", "ALPHA", "D1", "h2", "20260612120800", "OK", "TM"],
            ],
            [["ALPHA", "20260612115900", "20260612123000", "OPEN"]],
        )
        rows, summary, consumption = run_program()
        assert [row["status"] for row in rows] == ["ACCEPTED", "ACCEPTED", "ACCEPTED", "ACCEPTED"]
        assert summary["matched_count"] == 4
        assert [(row["audit_id"], row["catalog_row"]) for row in consumption] == [
            ("AUD-1", "1"),
            ("AUD-2", "0"),
            ("AUD-3", "2"),
            ("AUD-4", "3"),
        ]

    def test_invalid_verdict_and_payload_mismatch_still_reject_inside_valid_pass(self):
        """Pass windows do not bypass verdict or payload matching gates."""
        write_rules()
        write_inputs(
            [
                ["FRM-V", "ALPHA", "D1", "h1", "20260612120000", "OPEN", "TM"],
                ["FRM-P", "ALPHA", "D1", "h2", "20260612120010", "OPEN", "TM"],
            ],
            [
                ["AUD-V", "FRM-V", "ALPHA", "D1", "h1", "20260612120500", "NOPE", "TM"],
                ["AUD-P", "FRM-P", "ALPHA", "D1", "wrong", "20260612120500", "OK", "TM"],
            ],
            [["ALPHA", "20260612115900", "20260612123000", "OPEN"]],
        )
        rows, summary, _consumption = run_program()
        assert [row["status"] for row in rows] == ["REJECTED", "REJECTED"]
        assert summary == {"matched_count": 0, "matched_frames": 0, "rejected_count": 2, "rejected_frames": 2}
