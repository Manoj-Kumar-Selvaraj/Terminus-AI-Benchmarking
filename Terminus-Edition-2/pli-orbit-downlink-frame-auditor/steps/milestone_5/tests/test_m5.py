"""Verifier tests for milestone 5 station handoff and segment integrity."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
RULES = APP / "src/audit_rules.pli"
CATALOG = APP / "data/catalog.psv"
AUDITS = APP / "data/audits.psv"
WINDOWS = APP / "config/pass_windows.psv"
SEQCFG = APP / "config/sequence_contract.psv"
STATIONS = APP / "config/station_priority.psv"
SPOOL = APP / "spool/downlink_segments"
STATE = APP / "state"
LEDGER = STATE / "audit_ledger.psv"
CHECKPOINT = STATE / "downlink_checkpoint.psv"
CONFLICTS = APP / "out/station_conflicts.psv"
ANOMALIES = APP / "out/downlink_anomalies.psv"
RECOVERY = APP / "out/replay_recovery_report.txt"
QUARANTINE = APP / "out/quarantine.psv"
REPORT = APP / "out/audit_report.csv"
SUMMARY = APP / "out/audit_summary.txt"

CAT_HDR = ["frame_id", "craft_id", "channel", "payload_hash", "recv_ts", "state", "service_class"]
AUD_HDR = ["audit_id", "frame_id", "craft_id", "channel", "payload_hash", "audit_ts", "verdict_code", "service_class"]
LEDGER_HDR = ["pass_id", "craft_id", "channel", "vcid", "seq", "frame_id", "recv_ts", "payload_hash", "status"]


def hash_total(*payloads):
    return str(sum(sum(payload.encode("ascii")) for payload in payloads))


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


def reset_base():
    write_rules()
    write_psv(CATALOG, CAT_HDR, [["FRM-A", "ALPHA", "D1", "h1", "20260612120000", "OPEN", "TM"]])
    write_psv(AUDITS, AUD_HDR, [["AUD-A", "FRM-A", "ALPHA", "D1", "h1", "20260612120500", "OK", "TM"]])
    write_psv(WINDOWS, ["craft_id", "channel", "open_ts", "close_ts", "state"], [["ALPHA", "TM", "20260613173000", "20260613173959", "OPEN"], ["ALPHA", "D1", "20260612115900", "20260612123000", "OPEN"]])
    write_psv(SEQCFG, ["craft_id", "channel", "vcid", "min_seq", "max_seq", "wrap_enabled"], [["ALPHA", "TM", "VC0", "000000", "999999", "Y"]])
    write_psv(STATIONS, ["pass_id", "craft_id", "channel", "station_id", "priority", "handoff_open_ts", "handoff_close_ts"], [["ORB-8841", "ALPHA", "TM", "BLR-GS1", "1", "20260613173000", "20260613173500"], ["ORB-8841", "ALPHA", "TM", "SGP-GS2", "2", "20260613173430", "20260613173959"]])
    STATE.mkdir(parents=True, exist_ok=True)
    write_psv(LEDGER, LEDGER_HDR, [])
    write_psv(CHECKPOINT, ["pass_id", "craft_id", "channel", "vcid", "last_seq", "last_frame_id", "checkpoint_ts"], [])
    SPOOL.mkdir(parents=True, exist_ok=True)
    for path in SPOOL.iterdir():
        path.unlink()
    for path in [CONFLICTS, ANOMALIES, RECOVERY, QUARANTINE, REPORT, SUMMARY]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.unlink(missing_ok=True)


def run_program():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with CONFLICTS.open(newline="") as handle:
        conflicts = list(csv.DictReader(handle, delimiter="|"))
    with LEDGER.open(newline="") as handle:
        ledger = list(csv.DictReader(handle, delimiter="|"))
    with ANOMALIES.open(newline="") as handle:
        anomalies = list(csv.DictReader(handle, delimiter="|"))
    recovery = dict(line.split("=", 1) for line in RECOVERY.read_text().splitlines())
    with QUARANTINE.open(newline="") as handle:
        quarantine = list(csv.DictReader(handle, delimiter="|"))
    with REPORT.open(newline="") as handle:
        audit_rows = list(csv.DictReader(handle, delimiter="|"))
    summary = dict(line.split("=", 1) for line in SUMMARY.read_text().splitlines())
    return conflicts, ledger, anomalies, recovery, quarantine, audit_rows, summary


class TestMilestone5:
    """Station authority, conflict resolution, segment integrity, and full regression."""

    def test_highest_priority_station_selected_and_lower_priority_duplicate_reported(self):
        """The authoritative eligible station wins a duplicate observation."""
        reset_base()
        total = hash_total("p100")
        (SPOOL / "station_dupe.seg").write_text(
            f"HDR|ORB-8841|SEG-010|BLR-GS1|a|tm|20260613173300\n"
            f"FRM|ORB-8841|SEG-010|BLR-GS1|a|tm|VC0|000100|FRM-100-BLR|20260613173310|p100|OK|COMPLETE\n"
            f"TRL|ORB-8841|SEG-010|BLR-GS1|1|{total}|20260613173320\n"
            f"HDR|ORB-8841|SEG-011|SGP-GS2|ALPHA|TM|20260613173430\n"
            f"FRM|ORB-8841|SEG-011|SGP-GS2|ALPHA|TM|VC0|000100|FRM-100-SGP|20260613173440|p100|OK|COMPLETE\n"
            f"TRL|ORB-8841|SEG-011|SGP-GS2|1|{total}|20260613173450\n"
        )
        conflicts, ledger, anomalies, recovery, quarantine, audit_rows, summary = run_program()
        assert any(c["reason"] == "LOWER_PRIORITY_DUPLICATE" and c["station_id"] == "SGP-GS2" for c in conflicts)
        assert [r["frame_id"] for r in ledger] == ["FRM-100-BLR"]
        assert list(conflicts[0].keys()) == ["pass_id", "craft_id", "channel", "vcid", "seq", "frame_id", "station_id", "reason", "detail"]
        assert recovery["frames_committed"] == "1"
        assert quarantine == []
        assert audit_rows[0]["status"] == "ACCEPTED"
        assert summary["matched_count"] == "1"

    def test_payload_conflict_is_reported_and_conflicting_payloads_are_not_both_committed(self):
        """Conflicting payload observations produce one deterministic commit."""
        reset_base()
        (SPOOL / "payload_conflict.seg").write_text(
            f"HDR|ORB-8841|SEG-020|BLR-GS1|ALPHA|TM|20260613173300\n"
            f"FRM|ORB-8841|SEG-020|BLR-GS1|ALPHA|TM|VC0|000101|FRM-101-BLR|20260613173310|p101a|OK|COMPLETE\n"
            f"TRL|ORB-8841|SEG-020|BLR-GS1|1|{hash_total('p101a')}|20260613173320\n"
            f"HDR|ORB-8841|SEG-021|SGP-GS2|ALPHA|TM|20260613173430\n"
            f"FRM|ORB-8841|SEG-021|SGP-GS2|ALPHA|TM|VC0|000101|FRM-101-SGP|20260613173440|p101b|OK|COMPLETE\n"
            f"TRL|ORB-8841|SEG-021|SGP-GS2|1|{hash_total('p101b')}|20260613173450\n"
        )
        conflicts, ledger, _anomalies, _recovery, _quarantine, _audit, _summary = run_program()
        assert any(c["reason"] == "PAYLOAD_CONFLICT" for c in conflicts)
        committed_101 = [r for r in ledger if r["seq"] == "000101"]
        assert len(committed_101) == 1
        assert committed_101[0]["frame_id"] == "FRM-101-BLR"

    def test_station_outside_handoff_before_and_after_are_reported(self):
        """Station observations outside either handoff boundary are rejected."""
        reset_base()
        write_psv(STATIONS, ["pass_id", "craft_id", "channel", "station_id", "priority", "handoff_open_ts", "handoff_close_ts"], [["ORB-8841", "ALPHA", "TM", "BLR-GS1", "1", "20260613173100", "20260613173500"]])
        (SPOOL / "handoff_window.seg").write_text(
            f"HDR|ORB-8841|SEG-030|BLR-GS1|ALPHA|TM|20260613173000\n"
            f"FRM|ORB-8841|SEG-030|BLR-GS1|ALPHA|TM|VC0|000102|FRM-102-EARLY|20260613173030|p102|OK|COMPLETE\n"
            f"TRL|ORB-8841|SEG-030|BLR-GS1|1|{hash_total('p102')}|20260613173040\n"
            f"HDR|ORB-8841|SEG-031|BLR-GS1|ALPHA|TM|20260613173510\n"
            f"FRM|ORB-8841|SEG-031|BLR-GS1|ALPHA|TM|VC0|000103|FRM-103-LATE|20260613173501|p103|OK|COMPLETE\n"
            f"TRL|ORB-8841|SEG-031|BLR-GS1|1|{hash_total('p103')}|20260613173520\n"
        )
        conflicts, ledger, _anomalies, _recovery, _quarantine, _audit, _summary = run_program()
        outside = [c for c in conflicts if c["reason"] == "STATION_OUTSIDE_HANDOFF"]
        assert len(outside) == 2
        assert ledger == []

    def test_segment_integrity_failures_are_reported_and_invalid_frames_not_committed(self):
        """All structured-segment failures are reported without blocking later valid work."""
        reset_base()
        good_total = hash_total("p200")
        (SPOOL / "integrity.seg").write_text(
            # Missing header for SEG-MH
            f"FRM|ORB-8841|SEG-MH|BLR-GS1|ALPHA|TM|VC0|000110|FRM-MH|20260613173310|pmh|OK|COMPLETE\n"
            f"TRL|ORB-8841|SEG-MH|BLR-GS1|1|{hash_total('pmh')}|20260613173320\n"
            # Missing trailer for SEG-MT
            f"HDR|ORB-8841|SEG-MT|BLR-GS1|ALPHA|TM|20260613173300\n"
            f"FRM|ORB-8841|SEG-MT|BLR-GS1|ALPHA|TM|VC0|000111|FRM-MT|20260613173311|pmt|OK|COMPLETE\n"
            # Header/frame mismatch for SEG-HF
            f"HDR|ORB-8841|SEG-HF|BLR-GS1|ALPHA|TM|20260613173300\n"
            f"FRM|ORB-8841|SEG-HF-X|BLR-GS1|ALPHA|TM|VC0|000112|FRM-HF|20260613173312|phf|OK|COMPLETE\n"
            f"TRL|ORB-8841|SEG-HF|BLR-GS1|1|{hash_total('phf')}|20260613173320\n"
            # Frame/trailer mismatch and count mismatch for SEG-FT
            f"HDR|ORB-8841|SEG-FT|BLR-GS1|ALPHA|TM|20260613173300\n"
            f"FRM|ORB-8841|SEG-FT|BLR-GS1|ALPHA|TM|VC0|000113|FRM-FT|20260613173313|pft|OK|COMPLETE\n"
            f"TRL|ORB-8841|SEG-FT-X|BLR-GS1|2|{hash_total('pft')}|20260613173320\n"
            # Hash mismatch for SEG-HASH
            f"HDR|ORB-8841|SEG-HASH|BLR-GS1|ALPHA|TM|20260613173300\n"
            f"FRM|ORB-8841|SEG-HASH|BLR-GS1|ALPHA|TM|VC0|000114|FRM-HASH|20260613173314|phash|OK|COMPLETE\n"
            f"TRL|ORB-8841|SEG-HASH|BLR-GS1|1|999999|20260613173320\n"
            # Frame after trailer for SEG-AFTER
            f"HDR|ORB-8841|SEG-AFTER|BLR-GS1|ALPHA|TM|20260613173300\n"
            f"TRL|ORB-8841|SEG-AFTER|BLR-GS1|0|0|20260613173320\n"
            f"FRM|ORB-8841|SEG-AFTER|BLR-GS1|ALPHA|TM|VC0|000115|FRM-AFTER|20260613173315|pafter|OK|COMPLETE\n"
            # Later valid segment must still process.
            f"HDR|ORB-8841|SEG-GOOD|BLR-GS1|ALPHA|TM|20260613173300\n"
            f"FRM|ORB-8841|SEG-GOOD|BLR-GS1|ALPHA|TM|VC0|000200|FRM-200|20260613173320|p200|OK|COMPLETE\n"
            f"TRL|ORB-8841|SEG-GOOD|BLR-GS1|1|{good_total}|20260613173330\n"
        )
        conflicts, ledger, anomalies, recovery, quarantine, audit_rows, summary = run_program()
        reasons = {c["reason"] for c in conflicts}
        assert {"MISSING_HEADER", "MISSING_TRAILER", "SEGMENT_ID_MISMATCH", "SEGMENT_COUNT_MISMATCH", "SEGMENT_HASH_MISMATCH", "FRAME_AFTER_TRAILER"}.issubset(reasons)
        assert [r["frame_id"] for r in ledger] == ["FRM-200"]
        assert ANOMALIES.read_text().splitlines()[0] == "pass_id|craft_id|channel|vcid|seq|frame_id|reason|detail"
        assert set(recovery) == {"segments_seen", "frames_seen", "frames_committed", "duplicates_suppressed", "frames_quarantined", "checkpoint_status"}
        assert QUARANTINE.read_text().splitlines()[0] == "source_file|line_no|pass_id|craft_id|channel|vcid|seq|frame_id|reason"
        assert audit_rows[0]["status"] == "ACCEPTED"
        assert summary["matched_count"] == "1"
