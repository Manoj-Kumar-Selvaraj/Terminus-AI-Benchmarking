"""Verifier tests for milestone 1 of the orbit downlink frame auditor."""

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


def write_rules(state="ARMED", open_state="ARMED", verdicts=("OK", "WATCH", "DONE"), aliases=("A=>ALPHA", "tm=>TM", "SCI=>SCIENCE")):
    RULES.write_text(
        "\n".join(
            [
                f"DCL ELIGIBLE_STATE CHAR(12) INIT('{state}');",
                f"DCL OPEN_PASS_STATE CHAR(8) INIT('{open_state}');",
                f"DCL VERDICT_A CHAR(12) INIT('{verdicts[0]}');",
                f"DCL VERDICT_B CHAR(12) INIT('{verdicts[1]}');",
                f"DCL VERDICT_C CHAR(12) INIT('{verdicts[2]}');",
                *[f"DCL ALIAS_{i + 1} CHAR(30) INIT('{alias}');" for i, alias in enumerate(aliases)],
            ]
        )
        + "\n"
    )


def write_inputs(catalog, audits):
    write_psv(CATALOG, CAT_HDR, catalog)
    write_psv(AUDITS, AUD_HDR, audits)
    write_psv(WINDOWS, ["craft_id", "open_ts", "close_ts", "state"], [["ALPHA", "20260612115900", "20260612123000", "ARMED"]])
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


class TestMilestone1:
    """Core full-key matching, rule loading, aliasing, consumption, and output contracts."""

    @classmethod
    def setup_class(cls):
        write_rules()
        write_inputs(
            [
                ["FRM-1", "ALPHA", "D1", "aa", "20260612120000", "ARMED", "TM"],
                ["FRM-2", "BETA", "D2", "bb", "20260612120100", "BAD", "TM"],
                ["FRM-3", "ALPHA", "D3", "cc", "20260612120200", "ARMED", "TM"],
            ],
            [
                ["AUD-1", "FRM-1", "ALPHA", "D1", "aa", "20260612120500", "ok", "TM"],
                ["AUD-2", "FRM-1", "ALPHA", "D1", "aa", "20260612120600", "OK", "TM"],
                ["AUD-3", "FRM-2", "BETA", "D2", "bb", "20260612120700", "OK", "TM"],
                ["AUD-4", "FRM-3", "WRONG", "D3", "cc", "20260612120700", "WATCH", "TM"],
                ["AUD-5", "FRM-3", "ALPHA", "D3", "dd", "20260612120700", "WATCH", "TM"],
                ["AUD-6", "FRM-3", "ALPHA", "D3", "cc", "20260612120700", "NOPE", "TM"],
            ],
        )
        cls.rows, cls.summary, cls.consumption = run_program()

    def test_report_header_and_case_insensitive_verdict_acceptance(self):
        """The report schema and case-insensitive verdict contract remain exact."""
        assert REPORT.read_text().splitlines()[0] == "audit_id|frame_id|craft_id|channel|service_class|payload_hash|verdict_code|status"
        assert self.rows[0]["status"] == "ACCEPTED"
        assert self.rows[0]["service_class"] == "TM"

    def test_consumed_catalog_row_blocks_second_audit(self):
        """A physical catalog row cannot satisfy more than one audit."""
        assert self.rows[1]["status"] == "REJECTED"
        assert self.rows[1]["service_class"] == ""

    def test_ineligible_catalog_state_rejects_match(self):
        """A matching row in an ineligible state is rejected."""
        assert self.rows[2]["status"] == "REJECTED"

    def test_craft_id_mismatch_rejects_match(self):
        """Craft identity remains part of the full matching key."""
        assert self.rows[3]["status"] == "REJECTED"

    def test_payload_hash_mismatch_rejects_match(self):
        """Payload hashes must match exactly."""
        assert self.rows[4]["status"] == "REJECTED"

    def test_unknown_verdict_code_rejects_match(self):
        """Verdicts absent from the runtime rule deck are rejected."""
        assert self.rows[5]["status"] == "REJECTED"

    def test_summary_totals_use_key_value_lines(self):
        """Summary counts derive from the generated report outcomes."""
        assert self.summary == {"matched_count": 1, "matched_frames": 1, "rejected_count": 5, "rejected_frames": 5}

    def test_channel_mismatch_rejects_otherwise_qualifying_row(self):
        """Channel identity is independently enforced."""
        write_rules()
        write_inputs(
            [["FRM-5", "ALPHA", "D1", "ff", "20260612120000", "ARMED", "TM"]],
            [["AUD-8", "FRM-5", "ALPHA", "D9", "ff", "20260612120500", "OK", "TM"]],
        )
        rows, summary, _consumption = run_program()
        assert rows[0]["status"] == "REJECTED"
        assert summary["matched_count"] == 0

    def test_service_class_mismatch_rejects_otherwise_qualifying_row(self):
        """Service class is independently enforced."""
        write_rules()
        write_inputs(
            [["FRM-4", "ALPHA", "D1", "ee", "20260612120000", "ARMED", "TM"]],
            [["AUD-7", "FRM-4", "ALPHA", "D1", "ee", "20260612120500", "OK", "TC"]],
        )
        assert run_program()[0][0]["status"] == "REJECTED"

    def test_frame_id_prefix_only_match_rejects_wrong_suffix(self):
        """Frame identifiers require full equality rather than prefix equality."""
        write_rules()
        write_inputs(
            [
                ["FRM-9A", "ALPHA", "D1", "ff", "20260612120000", "ARMED", "TM"],
                ["FRM-9B", "ALPHA", "D1", "ff", "20260612120100", "ARMED", "TM"],
            ],
            [["AUD-9", "FRM-9B", "ALPHA", "D1", "ff", "20260612120500", "OK", "TM"]],
        )
        rows, _summary, _consumption = run_program()
        assert rows[0]["status"] == "ACCEPTED"
        assert rows[0]["frame_id"] == "FRM-9B"

    def test_latest_recv_ts_wins_on_tied_frame_id(self):
        """The latest qualifying receive timestamp is consumed first."""
        write_rules()
        write_inputs(
            [
                ["FRM-A", "ALPHA", "D1", "h1", "20260612120000", "ARMED", "TM"],
                ["FRM-A", "ALPHA", "D1", "h1", "20260612120100", "ARMED", "TM"],
            ],
            [
                ["AUD-W", "FRM-A", "ALPHA", "D1", "h1", "20260612120500", "OK", "TM"],
                ["AUD-2", "FRM-A", "ALPHA", "D1", "h1", "20260612120600", "OK", "TM"],
            ],
        )
        rows, summary, consumption = run_program()
        assert [row["status"] for row in rows] == ["ACCEPTED", "ACCEPTED"]
        assert summary["matched_count"] == 2
        assert [(row["audit_id"], row["catalog_row"], row["recv_ts"]) for row in consumption] == [
            ("AUD-W", "1", "20260612120100"),
            ("AUD-2", "0", "20260612120000"),
        ]

    def test_equal_recv_ts_uses_earliest_catalog_row(self):
        """Equal receive timestamps consume catalog rows in physical input order."""
        write_rules()
        write_inputs(
            [
                ["FRM-T", "ALPHA", "D1", "h2", "20260612120100", "ARMED", "TM"],
                ["FRM-T", "ALPHA", "D1", "h2", "20260612120100", "ARMED", "TM"],
            ],
            [
                ["C-T1", "FRM-T", "ALPHA", "D1", "h2", "20260612120500", "OK", "TM"],
                ["C-T2", "FRM-T", "ALPHA", "D1", "h2", "20260612120600", "OK", "TM"],
            ],
        )
        rows, summary, consumption = run_program()
        assert [row["status"] for row in rows] == ["ACCEPTED", "ACCEPTED"]
        assert summary["matched_count"] == 2
        assert [(row["audit_id"], row["catalog_row"]) for row in consumption] == [("C-T1", "0"), ("C-T2", "1")]

    def test_catalog_audit_channel_and_service_aliases_normalize(self):
        """Aliases normalize on both sides after trimming and case folding."""
        write_rules(state="LIVE", verdicts=("GO", "CHK", "WAIT"), aliases=(" a => ALPHA ", "tm=>TM", "sci=>SCIENCE", "xl=>XLINK"))
        write_inputs(
            [["FRM-11", "a", "xl", "ff", "20260612120000", "LIVE", "sci"]],
            [["AUD-11", "FRM-11", "  ALPHA  ", "XLINK", "ff", "20260612120500", "go", "SCIENCE"]],
        )
        rows, summary, _consumption = run_program()
        assert rows[0]["status"] == "ACCEPTED"
        assert rows[0]["service_class"] == "SCIENCE"
        assert summary["matched_count"] == 1

    def test_ineligible_state_and_consume_once_still_apply_with_aliases(self):
        """Aliases do not bypass state or one-time-consumption gates."""
        write_rules(state="LIVE", verdicts=("GO", "CHK", "WAIT"), aliases=("a=>ALPHA", "tm=>TM"))
        write_inputs(
            [
                ["FRM-1", "a", "D1", "ff", "20260612120000", "STALE", "tm"],
                ["FRM-2", "a", "D1", "gg", "20260612120100", "LIVE", "tm"],
            ],
            [
                ["AUD-1", "FRM-1", "A", "D1", "ff", "20260612120500", "go", "TM"],
                ["AUD-2", "FRM-2", "A", "D1", "gg", "20260612120600", "go", "TM"],
                ["AUD-3", "FRM-2", "A", "D1", "gg", "20260612120700", "go", "TM"],
            ],
        )
        rows, summary, _consumption = run_program()
        assert [row["status"] for row in rows] == ["REJECTED", "ACCEPTED", "REJECTED"]
        assert summary == {"matched_count": 1, "matched_frames": 1, "rejected_count": 2, "rejected_frames": 2}
