"""Verifier tests for milestone 3 replay recovery."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
RULES = APP / "src/audit_rules.pli"
CATALOG = APP / "data/catalog.psv"
AUDITS = APP / "data/audits.psv"
WINDOWS = APP / "config/pass_windows.psv"
SPOOL = APP / "spool/downlink_segments"
STATE = APP / "state"
LEDGER = STATE / "audit_ledger.psv"
CHECKPOINT = STATE / "downlink_checkpoint.psv"
REPORT = APP / "out/audit_report.csv"
SUMMARY = APP / "out/audit_summary.txt"
RECOVERY = APP / "out/replay_recovery_report.txt"
QUARANTINE = APP / "out/quarantine.psv"

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


def reset_base(ledger_rows=None, checkpoint_rows=None):
    write_rules()
    write_psv(CATALOG, ["frame_id", "craft_id", "channel", "payload_hash", "recv_ts", "state", "service_class"], [["FRM-A", "ALPHA", "D1", "h1", "20260612120000", "OPEN", "TM"]])
    write_psv(AUDITS, AUD_HDR, [["AUD-A", "FRM-A", "ALPHA", "D1", "h1", "20260612120500", "OK", "TM"]])
    write_psv(WINDOWS, ["craft_id", "channel", "open_ts", "close_ts", "state"], [["ALPHA", "TM", "20260613173000", "20260613173959", "OPEN"], ["ALPHA", "D1", "20260612115900", "20260612123000", "OPEN"]])
    SPOOL.mkdir(parents=True, exist_ok=True)
    for path in SPOOL.iterdir():
        path.unlink()
    STATE.mkdir(parents=True, exist_ok=True)
    write_psv(LEDGER, LEDGER_HDR, ledger_rows or [])
    if checkpoint_rows is None:
        CHECKPOINT.unlink(missing_ok=True)
    else:
        write_psv(CHECKPOINT, ["pass_id", "craft_id", "channel", "vcid", "last_seq", "last_frame_id", "checkpoint_ts"], checkpoint_rows)
    for path in [REPORT, SUMMARY, RECOVERY, QUARANTINE]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.unlink(missing_ok=True)


def run_program():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        audit_rows = list(csv.DictReader(handle, delimiter="|"))
    with LEDGER.open(newline="") as handle:
        ledger_rows = list(csv.DictReader(handle, delimiter="|"))
    with QUARANTINE.open(newline="") as handle:
        quarantine_rows = list(csv.DictReader(handle, delimiter="|"))
    recovery = dict(line.split("=", 1) for line in RECOVERY.read_text().splitlines())
    return audit_rows, ledger_rows, quarantine_rows, recovery


class TestMilestone3:
    """Replay recovery, checkpoint tolerance, quarantine, and non-regression."""

    def test_valid_replay_commits_and_duplicates_are_suppressed(self):
        """Valid replay commits once while ledger and same-run duplicates are suppressed."""
        reset_base(
            ledger_rows=[["ORB-8841", "ALPHA", "TM", "VC0", "000101", "FRM-101", "20260613173301", "h101", "COMMITTED"]],
            checkpoint_rows=[["ORB-8841", "ALPHA", "TM", "VC0", "000100", "FRM-100", "20260613173300"]],
        )
        (SPOOL / "segment_001.seg").write_text(
            "# replay after receiver failover\n"
            "ORB-8841|SEG-001|BLR-GS1|a|tm|VC0|000101|FRM-101|20260613173301|h101|OK|COMPLETE\n"
            "ORB-8841|SEG-001|BLR-GS1|a|tm|VC0|000102|FRM-102|20260613173302|h102|OK|COMPLETE\n"
            "ORB-8841|SEG-001|BLR-GS1|a|tm|VC0|000102|FRM-102|20260613173302|h102|OK|COMPLETE\n"
        )
        audit_rows, ledger_rows, quarantine_rows, recovery = run_program()
        assert [r["frame_id"] for r in ledger_rows] == ["FRM-101", "FRM-102"]
        assert recovery["checkpoint_status"] == "STALE"
        assert recovery["segments_seen"] == "1"
        assert recovery["frames_seen"] == "3"
        assert recovery["duplicates_suppressed"] == "2"
        assert recovery["frames_committed"] == "1"
        assert recovery["frames_quarantined"] == "0"
        assert quarantine_rows == []
        assert audit_rows[0]["status"] == "ACCEPTED"

    def test_missing_checkpoint_does_not_crash_and_ahead_checkpoint_does_not_skip_valid_frame(self):
        """Missing or ahead checkpoints never hide otherwise valid replay frames."""
        reset_base(checkpoint_rows=None)
        (SPOOL / "segment_missing_cp.seg").write_text(
            "ORB-8841|SEG-002|BLR-GS1|ALPHA|TM|VC0|000103|FRM-103|20260613173303|h103|OK|COMPLETE\n"
        )
        _audit, ledger_rows, _quarantine, recovery = run_program()
        assert recovery["checkpoint_status"] == "MISSING"
        assert any(r["frame_id"] == "FRM-103" for r in ledger_rows)

        reset_base(checkpoint_rows=[["ORB-8841", "ALPHA", "TM", "VC0", "000999", "FRM-999", "20260613173309"]])
        (SPOOL / "segment_ahead_cp.seg").write_text(
            "ORB-8841|SEG-003|BLR-GS1|ALPHA|TM|VC0|000104|FRM-104|20260613173304|h104|OK|COMPLETE\n"
        )
        _audit, ledger_rows, _quarantine, recovery = run_program()
        assert recovery["checkpoint_status"] == "AHEAD_OF_LEDGER"
        assert any(r["frame_id"] == "FRM-104" for r in ledger_rows)

    def test_partial_bad_crc_incomplete_malformed_and_pass_closed_rows_are_quarantined(self):
        """Unsafe replay rows are quarantined while later valid rows continue."""
        reset_base(checkpoint_rows=[])
        (SPOOL / "segment_004.seg").write_text(
            "ORB-8841|SEG-004|BLR-GS1|ALPHA|TM|VC0|000105|FRM-105|20260613173305|h105|BAD|COMPLETE\n"
            "ORB-8841|SEG-004|BLR-GS1|ALPHA|TM|VC0|000106|FRM-106|20260613173306|h106|OK|OPEN\n"
            "too|few|fields\n"
            "ORB-8841|SEG-004|BLR-GS1|ALPHA|TM|VC0|000107|FRM-107|20260613180000|h107|OK|COMPLETE\n"
            "ORB-8841|SEG-004|BLR-GS1|ALPHA|TM|VC0|000108|FRM-108|20260613173308|h108|OK|COMPLETE\n"
        )
        (SPOOL / "segment_005.partial").write_text(
            "ORB-8841|SEG-005|BLR-GS1|ALPHA|TM|VC0|000109|FRM-109|20260613173309|h109|OK|COMPLETE\n"
        )
        _audit, ledger_rows, quarantine_rows, recovery = run_program()
        reasons = [r["reason"] for r in quarantine_rows]
        assert QUARANTINE.read_text().splitlines()[0] == (
            "source_file|line_no|pass_id|craft_id|channel|vcid|seq|frame_id|reason"
        )
        assert {"BAD_CRC", "INCOMPLETE_SEGMENT", "MALFORMED_FRAME", "PASS_CLOSED", "PARTIAL_SEGMENT"}.issubset(set(reasons))
        assert any(r["frame_id"] == "FRM-108" for r in ledger_rows)
        assert recovery["frames_quarantined"] == str(len(quarantine_rows))

    def test_aliases_apply_to_replay_rows_and_legacy_outputs_remain_compatible(self):
        """Replay aliases persist canonically without changing legacy output schemas."""
        reset_base(checkpoint_rows=[])
        (SPOOL / "segment_alias.replay").write_text(
            "ORB-8841|SEG-006|BLR-GS1|a|tm|VC0|000110|FRM-110|20260613173310|h110|OK|COMPLETE\n"
        )
        audit_rows, ledger_rows, _quarantine, recovery = run_program()
        committed = [r for r in ledger_rows if r["frame_id"] == "FRM-110"]
        assert committed and committed[0]["craft_id"] == "ALPHA" and committed[0]["channel"] == "TM"
        assert list(audit_rows[0].keys()) == ["audit_id", "frame_id", "craft_id", "channel", "service_class", "payload_hash", "verdict_code", "status"]
        assert set(recovery) == {"segments_seen", "frames_seen", "frames_committed", "duplicates_suppressed", "frames_quarantined", "checkpoint_status"}
