"""Verifier tests for milestone 4 sequence continuity."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
RULES = APP / "src/audit_rules.pli"
CATALOG = APP / "data/catalog.psv"
AUDITS = APP / "data/audits.psv"
WINDOWS = APP / "config/pass_windows.psv"
SEQCFG = APP / "config/sequence_contract.psv"
SPOOL = APP / "spool/downlink_segments"
STATE = APP / "state"
LEDGER = STATE / "audit_ledger.psv"
CHECKPOINT = STATE / "downlink_checkpoint.psv"
ANOMALIES = APP / "out/downlink_anomalies.psv"
RECOVERY = APP / "out/replay_recovery_report.txt"
REPORT = APP / "out/audit_report.csv"

CAT_HDR = ["frame_id", "craft_id", "channel", "payload_hash", "recv_ts", "state", "service_class"]
AUD_HDR = ["audit_id", "frame_id", "craft_id", "channel", "payload_hash", "audit_ts", "verdict_code", "service_class"]
LEDGER_HDR = ["pass_id", "craft_id", "channel", "vcid", "seq", "frame_id", "recv_ts", "payload_hash", "status"]


def write_psv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("|".join(header) + "\n" + "\n".join("|".join(row) for row in rows) + ("\n" if rows else ""))


def write_rules():
    RULES.write_text(
        "\n".join(
            [
                "DCL ELIGIBLE_STATE CHAR(12) INIT('OPEN');",
                "DCL OPEN_PASS_STATE CHAR(8) INIT('OPEN');",
                "DCL VERDICT_A CHAR(12) INIT('OK');",
                "DCL VERDICT_B CHAR(12) INIT('WATCH');",
                "DCL VERDICT_C CHAR(12) INIT('DONE');",
                "DCL ALIAS_1 CHAR(20) INIT('a=>ALPHA');",
                "DCL ALIAS_2 CHAR(20) INIT('tm=>TM');",
            ]
        )
        + "\n"
    )


def reset_base(ledger_rows, seq_rows=None):
    write_rules()
    write_psv(CATALOG, CAT_HDR, [["FRM-A", "ALPHA", "D1", "h1", "20260612120000", "OPEN", "TM"]])
    write_psv(AUDITS, AUD_HDR, [["AUD-A", "FRM-A", "ALPHA", "D1", "h1", "20260612120500", "OK", "TM"]])
    write_psv(WINDOWS, ["craft_id", "channel", "open_ts", "close_ts", "state"], [["ALPHA", "TM", "20260613173000", "20260613173959", "OPEN"], ["BETA", "TM", "20260613173000", "20260613173959", "OPEN"], ["ALPHA", "D1", "20260612115900", "20260612123000", "OPEN"]])
    write_psv(SEQCFG, ["craft_id", "channel", "vcid", "min_seq", "max_seq", "wrap_enabled"], seq_rows or [["ALPHA", "TM", "VC0", "000000", "999999", "Y"], ["BETA", "TM", "VC0", "000000", "999999", "N"]])
    STATE.mkdir(parents=True, exist_ok=True)
    write_psv(LEDGER, LEDGER_HDR, ledger_rows)
    write_psv(CHECKPOINT, ["pass_id", "craft_id", "channel", "vcid", "last_seq", "last_frame_id", "checkpoint_ts"], [])
    SPOOL.mkdir(parents=True, exist_ok=True)
    for path in SPOOL.iterdir():
        path.unlink()
    for path in [ANOMALIES, RECOVERY, REPORT, APP / "out/quarantine.psv"]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.unlink(missing_ok=True)


def run_program():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with ANOMALIES.open(newline="") as handle:
        anomalies = list(csv.DictReader(handle, delimiter="|"))
    recovery = dict(line.split("=", 1) for line in RECOVERY.read_text().splitlines())
    with REPORT.open(newline="") as handle:
        audit_rows = list(csv.DictReader(handle, delimiter="|"))
    return anomalies, recovery, audit_rows


class TestMilestone4:
    """Sequence anomalies without replay/static audit regression."""

    def test_clean_contiguous_sequence_has_no_gap_anomaly(self):
        """A complete contiguous stream emits no false sequence gap."""
        reset_base([
            ["ORB-8841", "ALPHA", "TM", "VC0", "000101", "FRM-101", "20260613173301", "h101", "COMMITTED"],
            ["ORB-8841", "ALPHA", "TM", "VC0", "000102", "FRM-102", "20260613173302", "h102", "COMMITTED"],
            ["ORB-8841", "ALPHA", "TM", "VC0", "000103", "FRM-103", "20260613173303", "h103", "COMMITTED"],
        ])
        anomalies, recovery, audit_rows = run_program()
        assert [a["reason"] for a in anomalies if a["reason"] == "SEQ_GAP"] == []
        assert set(recovery) == {"segments_seen", "frames_seen", "frames_committed", "duplicates_suppressed", "frames_quarantined", "checkpoint_status"}
        assert audit_rows[0]["status"] == "ACCEPTED"

    def test_single_and_multiple_missing_sequences_emit_gap_rows(self):
        """Each missing sequence emits the documented endpoint detail."""
        reset_base([
            ["ORB-8841", "ALPHA", "TM", "VC0", "000101", "FRM-101", "20260613173301", "h101", "COMMITTED"],
            ["ORB-8841", "ALPHA", "TM", "VC0", "000104", "FRM-104", "20260613173304", "h104", "COMMITTED"],
        ])
        anomalies, _recovery, _audit = run_program()
        gaps = [a for a in anomalies if a["reason"] == "SEQ_GAP"]
        assert [g["seq"] for g in gaps] == ["000102", "000103"]
        assert [g["detail"] for g in gaps] == [
            "missing_after=000101 before=000104",
            "missing_after=000101 before=000104",
        ]

    def test_out_of_order_complete_sequence_does_not_emit_false_gap(self):
        """Continuity is evaluated by sequence value rather than arrival order."""
        reset_base([
            ["ORB-8841", "ALPHA", "TM", "VC0", "000103", "FRM-103", "20260613173303", "h103", "COMMITTED"],
            ["ORB-8841", "ALPHA", "TM", "VC0", "000101", "FRM-101", "20260613173301", "h101", "COMMITTED"],
            ["ORB-8841", "ALPHA", "TM", "VC0", "000102", "FRM-102", "20260613173302", "h102", "COMMITTED"],
        ])
        anomalies, _recovery, _audit = run_program()
        assert not [a for a in anomalies if a["reason"] == "SEQ_GAP"]

    def test_duplicate_replay_suppression_is_not_reported_as_duplicate_sequence(self):
        """An exact replay duplicate is not misclassified as a sequence conflict."""
        reset_base([
            ["ORB-8841", "ALPHA", "TM", "VC0", "000101", "FRM-101", "20260613173301", "h101", "COMMITTED"],
        ])
        (SPOOL / "dupe.replay").write_text(
            "ORB-8841|SEG-D|BLR-GS1|ALPHA|TM|VC0|000101|FRM-101|20260613173301|h101|OK|COMPLETE\n"
        )
        anomalies, recovery, _audit = run_program()
        assert recovery["duplicates_suppressed"] == "1"
        assert not [a for a in anomalies if a["reason"] == "DUPLICATE_SEQ"]

    def test_different_frame_same_sequence_bad_format_and_out_of_range_emit_anomalies(self):
        """Distinct duplicate, malformed, and out-of-range sequences are classified."""
        reset_base([
            ["ORB-8841", "ALPHA", "TM", "VC0", "000101", "FRM-101", "20260613173301", "h101", "COMMITTED"],
            ["ORB-8841", "ALPHA", "TM", "VC0", "000101", "FRM-101B", "20260613173302", "h101b", "COMMITTED"],
            ["ORB-8841", "ALPHA", "TM", "VC0", "ABC123", "FRM-BAD", "20260613173303", "hbad", "COMMITTED"],
            ["ORB-8841", "ALPHA", "TM", "VC0", "1000000", "FRM-OOR", "20260613173304", "hoor", "COMMITTED"],
        ])
        anomalies, _recovery, _audit = run_program()
        assert any(
            row["reason"] == "DUPLICATE_SEQ"
            and row["frame_id"] == "FRM-101"
            and row["seq"] == "000101"
            for row in anomalies
        )
        assert any(
            row["reason"] == "BAD_SEQ_FORMAT"
            and row["frame_id"] == "FRM-BAD"
            and row["seq"] == "ABC123"
            for row in anomalies
        )
        assert any(
            row["reason"] == "OUT_OF_RANGE_SEQ"
            and row["frame_id"] == "FRM-OOR"
            and row["seq"] == "1000000"
            for row in anomalies
        )

    def test_wrap_enabled_accepts_boundary_but_disabled_reports_unexpected_wrap(self):
        """Boundary wrap behavior follows each stream contract."""
        reset_base([
            ["ORB-8841", "ALPHA", "TM", "VC0", "999999", "FRM-MAX", "20260613173301", "hmax", "COMMITTED"],
            ["ORB-8841", "ALPHA", "TM", "VC0", "000000", "FRM-MIN", "20260613173302", "hmin", "COMMITTED"],
            ["ORB-8841", "BETA", "TM", "VC0", "999999", "B-MAX", "20260613173301", "bmax", "COMMITTED"],
            ["ORB-8841", "BETA", "TM", "VC0", "000000", "B-MIN", "20260613173302", "bmin", "COMMITTED"],
        ])
        anomalies, _recovery, _audit = run_program()
        alpha_wraps = [a for a in anomalies if a["craft_id"] == "ALPHA" and a["reason"] == "UNEXPECTED_WRAP"]
        beta_wraps = [a for a in anomalies if a["craft_id"] == "BETA" and a["reason"] == "UNEXPECTED_WRAP"]
        assert alpha_wraps == []
        assert beta_wraps

    def test_sequence_state_does_not_bleed_across_streams_and_aliases_apply_before_contract_lookup(self):
        """Sequence state is isolated by canonical pass, craft, channel, and VCID."""
        reset_base([
            ["ORB-8841", "ALPHA", "TM", "VC0", "000001", "FRM-A1", "20260613173301", "ha1", "COMMITTED"],
            ["ORB-8841", "ALPHA", "TM", "VC0", "000003", "FRM-A3", "20260613173303", "ha3", "COMMITTED"],
            ["ORB-8841", "BETA", "TM", "VC0", "000002", "FRM-B2", "20260613173302", "hb2", "COMMITTED"],
            ["ORB-8842", "ALPHA", "TM", "VC0", "000002", "FRM-OTHERPASS", "20260613173302", "hp2", "COMMITTED"],
            ["ORB-8841", "ALPHA", "TC", "VC0", "000002", "FRM-OTHERCHAN", "20260613173302", "hc2", "COMMITTED"],
            ["ORB-8841", "ALPHA", "TM", "VC1", "000002", "FRM-OTHERVC", "20260613173302", "hv2", "COMMITTED"],
        ], seq_rows=[["ALPHA", "TM", "VC0", "000000", "999999", "Y"], ["BETA", "TM", "VC0", "000000", "999999", "N"], ["ALPHA", "TC", "VC0", "000000", "999999", "Y"], ["ALPHA", "TM", "VC1", "000000", "999999", "Y"]])
        (SPOOL / "alias_commit.seg").write_text(
            "ORB-8841|SEG-A|BLR-GS1|a|tm|VC0|000004|FRM-A4|20260613173304|ha4|OK|COMPLETE\n"
        )
        anomalies, _recovery, _audit = run_program()
        gaps = [a for a in anomalies if a["reason"] == "SEQ_GAP" and a["craft_id"] == "ALPHA" and a["channel"] == "TM" and a["vcid"] == "VC0" and a["pass_id"] == "ORB-8841"]
        assert [g["seq"] for g in gaps] == ["000002"]
