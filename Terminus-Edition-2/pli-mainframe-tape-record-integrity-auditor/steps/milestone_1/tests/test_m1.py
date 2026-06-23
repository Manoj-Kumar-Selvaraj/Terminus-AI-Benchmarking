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


def write_rules(state="POSTED", reasons=("SCAN", "CHK", "DONE")):
    RULES.write_text(
        "\n".join(
            [
                f"DCL ELIGIBLE_STATE CHAR(12) INIT('{state}');",
                "DCL OPEN_MOUNT_STATE CHAR(8) INIT('OPEN');",
                f"DCL REASON_1 CHAR(12) INIT('{reasons[0]}');",
                f"DCL REASON_2 CHAR(12) INIT('{reasons[1]}');",
                f"DCL REASON_3 CHAR(12) INIT('{reasons[2]}');",
                "DCL ALIAS_1 CHAR(20) INIT('V1=>VOL1');",
                "DCL ALIAS_2 CHAR(20) INIT('B=>BETA');",
                "DCL ALIAS_3 CHAR(20) INIT('X=>XLINK');",
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


class TestMilestone1:
    """Milestone 1 full-key matching, gates, consumption, and summary totals."""

    @classmethod
    def setup_class(cls):
        write_rules(state="LIVE", reasons=("OK", "WATCH", "DONE"))
        write_inputs(
            [
                ["R-1", "991100", "10", "FED", "NYC", "20260612120000", "LIVE", "TM"],
                ["R-2", "991200", "20", "ACH", "NYC", "20260612120100", "BAD", "TM"],
                ["R-3", "991300", "30", "SWIFT", "BOS", "20260612120200", "LIVE", "TM"],
            ],
            [
                ["C1", "R-1", "991100", "10", "FED", "20260612120500", "ok", "NYC"],
                ["C2", "R-1", "991100", "10", "FED", "20260612120600", "OK", "NYC"],
                ["C3", "R-2", "991200", "20", "ACH", "20260612120700", "OK", "NYC"],
                ["C4", "R-3", "991300", "30", "SWIFT", "20260612120700", "WATCH", "BOS"],
                ["C5", "R-3", "991300", "31", "SWIFT", "20260612120700", "WATCH", "BOS"],
                ["C6", "R-3", "991300", "30", "SWIFT", "20260612120700", "NOPE", "BOS"],
            ],
            [["991100", "20260612115900", "20260612123000", "OPEN"]],
        )
        cls.rows, cls.summary = run_program()

    def test_report_header_and_verified_block_no(self):
        assert REPORT.read_text().splitlines()[0] == (
            "claim_id|record_id|volume_id|reel_id|block_no|length_hash|verdict_code|status"
        )
        assert self.rows[0]["status"] == "VERIFIED"
        assert self.rows[0]["block_no"] == "FED"

    def test_consumed_catalog_row_blocks_second_audit(self):
        assert self.rows[1]["status"] == "CORRUPT"
        assert self.rows[1]["block_no"] == ""

    def test_ineligible_catalog_state_rejects_match(self):
        assert self.rows[2]["status"] == "CORRUPT"

    def test_partial_key_mismatch_on_length_hash(self):
        assert self.rows[4]["status"] == "CORRUPT"

    def test_unknown_verdict_code_rejects_match(self):
        assert self.rows[5]["status"] == "CORRUPT"

    def test_verdict_code_matches_reason_declarations_case_insensitively(self):
        """Require runtime REASON_* lookup with case-insensitive verdict matching."""
        write_rules(state="LIVE", reasons=("SCAN", "WATCH", "DONE"))
        write_inputs(
            [
                ["R-7A", "991100", "10", "FED", "NYC", "20260612120000", "LIVE", "TM"],
                ["R-7B", "991100", "11", "FED", "NYC", "20260612120100", "LIVE", "TM"],
            ],
            [
                ["C7A", "R-7A", "991100", "10", "FED", "20260612120500", "scan", "NYC"],
                ["C7B", "R-7B", "991100", "11", "FED", "20260612120600", "watch", "NYC"],
            ],
            [["991100", "20260612115900", "20260612123000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["VERIFIED", "VERIFIED"]
        assert summary["verified_count"] == 2

    def test_summary_totals_use_key_value_lines(self):
        assert self.summary == {
            "verified_count": 2,
            "verified_blocks": 40,
            "corrupt_count": 4,
            "corrupt_blocks": 91,
        }

    def test_block_no_mismatch_rejects_otherwise_qualifying_row(self):
        write_rules(state="LIVE", reasons=("OK", "WATCH", "DONE"))
        write_inputs(
            [["R-9", "991100", "10", "FED", "NYC", "20260612120000", "LIVE", "TM"]],
            [["C9", "R-9", "991100", "10", "ACH", "20260612120500", "OK", "NYC"]],
            [["991100", "20260612115900", "20260612123000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "CORRUPT"
        assert rows[0]["block_no"] == ""
        assert summary["verified_count"] == 0

    def test_reel_id_mismatch_rejects_otherwise_qualifying_row(self):
        write_rules(state="LIVE", reasons=("OK", "WATCH", "DONE"))
        write_inputs(
            [["R-8", "991100", "10", "FED", "NYC", "20260612120000", "LIVE", "TM"]],
            [["C8", "R-8", "991100", "10", "FED", "20260612120500", "OK", "BOS"]],
            [["991100", "20260612115900", "20260612123000", "OPEN"]],
        )
        rows, _summary = run_program()
        assert rows[0]["status"] == "CORRUPT"

    def test_invalid_recv_ts_rejects_otherwise_qualifying_catalog_row(self):
        """Catalog recv_ts must be a numeric 14-digit timestamp."""
        write_rules(state="LIVE", reasons=("OK", "WATCH", "DONE"))
        write_inputs(
            [["R-X", "991100", "10", "FED", "NYC", "ABCDE", "LIVE", "TM"]],
            [["CX", "R-X", "991100", "10", "FED", "20260612120500", "OK", "NYC"]],
            [["991100", "20260612115900", "20260612123000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "CORRUPT"
        assert rows[0]["block_no"] == ""
        assert summary["corrupt_blocks"] == 10

    def test_key_fields_are_trimmed_and_case_folded_before_matching(self):
        """Record, volume, block, and reel keys match after trimming and case folding."""
        write_rules(state="LIVE", reasons=("OK", "WATCH", "DONE"))
        write_inputs(
            [["Rec-1", "vol01", "10", "fed", "nyc", "20260612120000", "LIVE", "TM"]],
            [["CT", " REC-1 ", " VOL01 ", "10", " FED ", "20260612120500", "OK", " NYC "]],
            [["VOL01", "20260612115900", "20260612123000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "VERIFIED"
        assert rows[0]["block_no"] == "FED"
        assert summary["verified_blocks"] == 10
