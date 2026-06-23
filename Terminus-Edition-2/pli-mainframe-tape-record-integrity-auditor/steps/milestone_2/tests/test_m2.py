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


def write_rules(state="LIVE", reasons=("GO", "CHK", "WAIT"), aliases=("f=>FED", "a=>ACH", "s=>SWIFT")):
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


class TestMilestone2:
    """Milestone 2 alias normalization with milestone 1 regression."""

    def test_catalog_alias_normalizes_to_match_audit_block_no(self):
        write_rules()
        write_inputs(
            [["R-9", "991100", "99", "f", "NYC", "20260612120000", "LIVE", "tm"]],
            [["C9", "R-9", "991100", "99", "FED", "20260612120500", "go", "NYC"]],
            [["991100", "20260612115900", "20260612123000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "VERIFIED"
        assert rows[0]["block_no"] == "FED"
        assert summary["verified_count"] == 1

    def test_audit_alias_normalizes_to_match_catalog_block_no(self):
        write_rules()
        write_inputs(
            [["R-10", "991100", "88", "ACH", "NYC", "20260612120000", "LIVE", "tm"]],
            [["C10", "R-10", "991100", "88", "a", "20260612120500", "go", "NYC"]],
            [["991100", "20260612115900", "20260612123000", "OPEN"]],
        )
        rows, _summary = run_program()
        assert rows[0]["status"] == "VERIFIED"
        assert rows[0]["block_no"] == "ACH"

    def test_whitespace_padded_alias_key_still_matches(self):
        write_rules()
        write_inputs(
            [["R-11", "991100", "77", "FED", "NYC", "20260612120000", "LIVE", "tm"]],
            [["C11", "R-11", "991100", "77", "  f  ", "20260612120500", "go", "NYC"]],
            [["991100", "20260612115900", "20260612123000", "OPEN"]],
        )
        rows, _summary = run_program()
        assert rows[0]["status"] == "VERIFIED"
        assert rows[0]["block_no"] == "FED"

    def test_unknown_alias_channel_stays_corrupt(self):
        write_rules()
        write_inputs(
            [["R-12", "991100", "66", "FED", "NYC", "20260612120000", "LIVE", "tm"]],
            [["C12", "R-12", "991100", "66", "ZZZ", "20260612120500", "go", "NYC"]],
            [["991100", "20260612115900", "20260612123000", "OPEN"]],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "CORRUPT"
        assert rows[0]["block_no"] == ""
        assert summary["verified_count"] == 0

    def test_reel_id_alias_normalizes_on_both_sides(self):
        """Require configured aliases during reel-id comparison as well as block comparison."""
        write_rules(aliases=("f=>FED", "n=>NYC", "s=>SWIFT"))
        write_inputs(
            [
                ["R-20", "991100", "50", "FED", " n ", "20260612120000", "LIVE", "tm"],
                ["R-21", "991100", "51", "FED", "NYC", "20260612120100", "LIVE", "tm"],
            ],
            [
                ["C20", "R-20", "991100", "50", "FED", "20260612120500", "go", "nyc"],
                ["C21", "R-21", "991100", "51", "FED", "20260612120600", "GO", " N "],
            ],
            [],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["VERIFIED", "VERIFIED"]
        assert [row["block_no"] for row in rows] == ["FED", "FED"]
        assert summary == {
            "verified_count": 2,
            "verified_blocks": 101,
            "corrupt_count": 0,
            "corrupt_blocks": 0,
        }
