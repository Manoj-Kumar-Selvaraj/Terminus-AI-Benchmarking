"""Verifier tests for mainframe tape record integrity PL/I auditor."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
CATALOG = APP / "data/tape_catalog.psv"
AUDITS = APP / "data/tape_audits.psv"
WINDOWS = APP / "config/mount_windows.psv"
RULES = APP / "src/tape_rules.pli"
REPORT = APP / "out/tape_report.csv"
SUMMARY = APP / "out/tape_summary.txt"


def write_psv(path, header, rows):
    path.write_text("|".join(header) + "\n" + "\n".join("|".join(row) for row in rows) + "\n")


def write_rules(state="LIVE", reasons=("OK", "WATCH", "DONE"), aliases=("V1=>VOL1", "A=>ACH", "S=>SWIFT")):
    RULES.write_text(
        "\n".join(
            [
                f"DCL ELIGIBLE_STATE CHAR(12) INIT('{state}');",
                "DCL OPEN_MOUNT_STATE CHAR(8) INIT('OPEN');",
                f"DCL REASON_1 CHAR(12) INIT('{reasons[0]}');",
                f"DCL REASON_2 CHAR(12) INIT('{reasons[1]}');",
                f"DCL REASON_3 CHAR(12) INIT('{reasons[2]}');",
                f"DCL ALIAS_1 CHAR(20) INIT('{aliases[0]}');",
                f"DCL ALIAS_2 CHAR(20) INIT('{aliases[1]}');",
                f"DCL ALIAS_3 CHAR(20) INIT('{aliases[2]}');",
            ]
        )
        + "\n"
    )


def write_inputs(catalog, audits, windows):
    write_psv(
        CATALOG,
        [
            "record_id",
            "volume_id",
            "length_hash",
            "block_no",
            "reel_id",
            "recv_ts",
            "state",
            "kind_code",
        ],
        catalog,
    )
    write_psv(
        AUDITS,
        [
            "claim_id",
            "record_id",
            "volume_id",
            "length_hash",
            "block_no",
            "audit_ts",
            "verdict_code",
            "reel_id",
        ],
        audits,
    )
    write_psv(WINDOWS, ["volume_id", "open_ts", "close_ts", "state"], windows)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="|"))
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        summary[key] = int(value)
    return rows, summary


class TestMilestone3:
    """Milestone 3 mount windows, timestamp bounds, and tie-breaking."""

    def test_audit_inside_mount_window_verifies(self):
        write_rules()
        write_inputs(
            [["R-A", "991100", "10", "FED", "NYC", "20260612120000", "LIVE", "TM"]],
            [["C-W", "R-A", "991100", "10", "FED", "20260612120500", "OK", "NYC"]],
            [["991100", "20260612115900", "20260612123000", "OPEN"]],
        )
        rows, _summary = run_program()
        assert rows[0]["status"] == "VERIFIED"

    def test_audit_after_window_close_is_corrupt(self):
        write_rules()
        write_inputs(
            [["R-A", "991100", "10", "FED", "NYC", "20260612120000", "LIVE", "TM"]],
            [["C-LATE", "R-A", "991100", "10", "FED", "20260612130000", "OK", "NYC"]],
            [["991100", "20260612115900", "20260612123000", "OPEN"]],
        )
        rows, _summary = run_program()
        assert rows[0]["status"] == "CORRUPT"

    def test_unlisted_volume_window_rejects_audit(self):
        write_rules()
        write_inputs(
            [["R-U", "991999", "10", "FED", "NYC", "20260612120000", "LIVE", "TM"]],
            [["C-U", "R-U", "991999", "10", "FED", "20260612120500", "OK", "NYC"]],
            [["991100", "20260612115900", "20260612123000", "OPEN"]],
        )
        rows, _summary = run_program()
        assert rows[0]["status"] == "CORRUPT"

    def test_latest_recv_ts_selection_preserves_the_earlier_row_for_next_audit(self):
        """Distinguish latest selection from first-fit through later consumption behavior."""
        write_rules()
        write_inputs(
            [
                ["R-A", "991100", "10", "EARLY", "NYC", "20260612120000", "LIVE", "TM"],
                ["R-A", "991100", "10", "LATE", "NYC", "20260612120100", "LIVE", "TM"],
            ],
            [
                ["C-T1", "R-A", "991100", "10", "LATE", "20260612120500", "OK", "NYC"],
                ["C-T2", "R-A", "991100", "10", "EARLY", "20260612120030", "OK", "NYC"],
            ],
            [["991100", "20260612115900", "20260612123000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["VERIFIED", "VERIFIED"]
        assert [row["block_no"] for row in rows] == ["LATE", "EARLY"]
        assert summary["verified_count"] == 2

    def test_equal_recv_ts_uses_earliest_catalog_row(self):
        """Equal recv_ts candidates are consumed in catalog input order."""
        write_rules(aliases=("f=>FIRST", "s=>SECOND", "x=>EXTRA"))
        write_inputs(
            [
                ["R-T", "991100", "10", "FIRST", "NYC", "20260612120100", "LIVE", "TM"],
                ["R-T", "991100", "10", "SECOND", "NYC", "20260612120100", "LIVE", "TM"],
            ],
            [
                ["C-T1", "R-T", "991100", "10", "f", "20260612120500", "OK", "NYC"],
                ["C-T2", "R-T", "991100", "10", "s", "20260612120600", "OK", "NYC"],
            ],
            [["991100", "20260612115900", "20260612123000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["VERIFIED", "VERIFIED"]
        assert [row["block_no"] for row in rows] == ["FIRST", "SECOND"]
        assert summary["verified_count"] == 2

    def test_consumption_makes_duplicate_audit_corrupt(self):
        """A single eligible catalog row cannot verify two audit rows."""
        write_rules()
        write_inputs(
            [["R-ONE", "991100", "10", "FED", "NYC", "20260612120000", "LIVE", "TM"]],
            [
                ["C-ONE", "R-ONE", "991100", "10", "FED", "20260612120500", "OK", "NYC"],
                ["C-TWO", "R-ONE", "991100", "10", "FED", "20260612120600", "OK", "NYC"],
            ],
            [["991100", "20260612115900", "20260612123000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["VERIFIED", "CORRUPT"]
        assert [row["block_no"] for row in rows] == ["FED", ""]
        assert summary == {
            "verified_count": 1,
            "verified_blocks": 10,
            "corrupt_count": 1,
            "corrupt_blocks": 10,
        }

    def test_before_open_closed_malformed_and_reversed_windows_are_corrupt(self):
        """Reject each documented invalid mount-window condition."""
        scenarios = [
            ("20260612115800", "20260612120500", [["991100", "20260612115900", "20260612123000", "OPEN"]]),
            ("20260612120000", "20260612120500", [["991100", "20260612115900", "20260612123000", "CLOSED"]]),
            ("20260612120000", "20260612120500", [["991100", "BAD", "20260612123000", "OPEN"]]),
            ("20260612120000", "20260612120500", [["991100", "20260612123000", "20260612115900", "OPEN"]]),
        ]
        for recv_ts, audit_ts, windows in scenarios:
            write_rules()
            write_inputs(
                [["R-E", "991100", "10", "FED", "NYC", recv_ts, "LIVE", "TM"]],
                [["C-E", "R-E", "991100", "10", "FED", audit_ts, "ok", "NYC"]],
                windows,
            )
            rows, summary = run_program()
            assert rows[0]["status"] == "CORRUPT"
            assert rows[0]["block_no"] == ""
            assert summary["verified_count"] == 0

    def test_catalog_and_window_states_are_independent(self):
        """Reject an ineligible catalog row even when its mount window is open."""
        write_rules(state="LIVE")
        write_inputs(
            [["R-S", "991100", "10", "FED", "NYC", "20260612120000", "OPEN", "TM"]],
            [["C-S", "R-S", "991100", "10", "FED", "20260612120500", "OK", "NYC"]],
            [["991100", "20260612115900", "20260612123000", "OPEN"]],
        )
        rows, _summary = run_program()
        assert rows[0]["status"] == "CORRUPT"

    def test_recv_after_audit_ts_is_corrupt_inside_otherwise_valid_window(self):
        """A catalog receive timestamp after the audit timestamp is not eligible."""
        write_rules()
        write_inputs(
            [["R-ORDER", "991100", "10", "FED", "NYC", "20260612121000", "LIVE", "TM"]],
            [["C-ORDER", "R-ORDER", "991100", "10", "FED", "20260612120500", "OK", "NYC"]],
            [["991100", "20260612115900", "20260612123000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "CORRUPT"
        assert summary["corrupt_blocks"] == 10

    def test_case_insensitive_volume_id_and_window_state_match(self):
        """Volume and window state comparisons are trimmed and case-insensitive."""
        write_rules()
        write_inputs(
            [["R-CASE", "vol01", "10", "FED", "NYC", "20260612120000", "LIVE", "TM"]],
            [["C-CASE", "R-CASE", " VOL01 ", "10", "FED", "20260612120500", "OK", "NYC"]],
            [[" Vol01 ", "20260612115900", "20260612123000", " open "]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "VERIFIED"
        assert summary["verified_blocks"] == 10
