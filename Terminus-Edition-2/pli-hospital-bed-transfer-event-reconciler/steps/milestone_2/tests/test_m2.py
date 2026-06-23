"""Verifier tests for hospital bed transfer PL/I task."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SRC = APP / "data/beds.psv"
ACT = APP / "data/transfers.psv"
WIN = APP / "config/windows.psv"
RULES = APP / "src/reconcile_rules.pli"
REPORT = APP / "out/transfer_report.csv"
SUMMARY = APP / "out/transfer_summary.txt"


def write_psv(path, header, rows):
    path.write_text(
        "|".join(header) + "\n" + "\n".join("|".join(r) for r in rows) + "\n"
    )


def write_rules(
    status="OCCUPIED",
    open_state="OPEN",
    reasons=("MOVE", "STEPDOWN", "DISCHARGE"),
    aliases=("I=>ICU", "M=>MEDSURG", "O=>OBS"),
):
    lines = [
        f"DCL ELIGIBLE_STATUS CHAR(12) INIT('{status}');",
        f"DCL OPEN_WINDOW_STATUS CHAR(8) INIT('{open_state}');",
        f"DCL REASON_A CHAR(12) INIT('{reasons[0]}');",
        f"DCL REASON_B CHAR(12) INIT('{reasons[1]}');",
        f"DCL REASON_C CHAR(12) INIT('{reasons[2]}');",
    ]
    lines += [f"DCL ALIAS_{i + 1} CHAR(20) INIT('{a}');" for i, a in enumerate(aliases)]
    RULES.write_text("\n".join(lines) + "\n")


def write_inputs(src, act, wins):
    write_psv(
        SRC,
        [
            "bed_id",
            "patient_id",
            "ward_id",
            "bed_type",
            "charge_cents",
            "admit_ts",
            "status",
            "nurse_unit",
        ],
        src,
    )
    write_psv(
        ACT,
        [
            "action_id",
            "bed_id",
            "patient_id",
            "ward_id",
            "bed_type",
            "charge_cents",
            "transfer_ts",
            "reason",
            "nurse_unit",
        ],
        act,
    )
    write_psv(WIN, ["ward_id", "open_ts", "close_ts", "state"], wins)
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        k, v = line.split("=", 1)
        summary[k] = int(v)
    return rows, summary


def test_milestone1_full_gates_consumption_and_totals():
    """Milestone 1 enforces full keys, PL/I status/reasons, consumption, and positive totals."""
    write_rules(status="READY", reasons=("OK", "WATCH", "DONE"))
    write_inputs(
        [
            ["SRC-1", "PARTY-1", "S-A", "ICU", "10", "20260528120000", "READY", "L1"],
            ["SRC-2", "PARTY-2", "S-A", "MEDSURG", "20", "20260528120100", "BAD", "L2"],
            [
                "SRC-3",
                "PARTY-3",
                "S-A",
                "MEDSURG",
                "30",
                "20260528120200",
                "READY",
                "L3",
            ],
        ],
        [
            [
                "ACT-1",
                "SRC-1",
                "PARTY-1",
                "S-A",
                "ICU",
                "10",
                "20260528120500",
                "OK",
                "L1",
            ],
            [
                "ACT-2",
                "SRC-1",
                "PARTY-1",
                "S-A",
                "ICU",
                "10",
                "20260528120600",
                "OK",
                "L1",
            ],
            [
                "ACT-3",
                "SRC-2",
                "PARTY-2",
                "S-A",
                "MEDSURG",
                "20",
                "20260528120700",
                "OK",
                "L2",
            ],
            [
                "ACT-4",
                "SRC-3",
                "BAD",
                "S-A",
                "MEDSURG",
                "30",
                "20260528120700",
                "WATCH",
                "L3",
            ],
            [
                "ACT-5",
                "SRC-3",
                "PARTY-3",
                "S-A",
                "MEDSURG",
                "31",
                "20260528120700",
                "WATCH",
                "L3",
            ],
            [
                "ACT-6",
                "SRC-3",
                "PARTY-3",
                "S-A",
                "MEDSURG",
                "30",
                "20260528120700",
                "NOPE",
                "L3",
            ],
        ],
        [["S-A", "20260528115900", "20260528123000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == [
        "MATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "UNMATCHED",
    ]
    assert rows[1]["bed_type"] == ""
    assert summary == {
        "matched_count": 1,
        "matched_amount_cents": 10,
        "unmatched_count": 5,
        "unmatched_amount_cents": 121,
    }


def test_milestone2_aliases_emit_canonical_values():
    """Milestone 2 applies every PL/I alias while preserving prior gates."""
    write_rules()
    write_inputs(
        [
            ["A-1", "P-1", "S-B", "ICU", "1", "20260528130000", "OCCUPIED", "L1"],
            ["A-2", "P-2", "S-B", "MEDSURG", "2", "20260528130100", "OCCUPIED", "L2"],
            ["A-3", "P-3", "S-B", "OBS", "3", "20260528130200", "OCCUPIED", "L3"],
        ],
        [
            ["X-1", "A-1", "P-1", "S-B", "i", "1", "20260528130500", "MOVE", "L1"],
            ["X-2", "A-2", "P-2", "S-B", "M", "2", "20260528130600", "STEPDOWN", "L2"],
            ["X-3", "A-3", "P-3", "S-B", "O", "3", "20260528130700", "DISCHARGE", "L3"],
            [
                "X-4",
                "A-3",
                "P-3",
                "S-B",
                "BAD",
                "3",
                "20260528130800",
                "DISCHARGE",
                "L3",
            ],
        ],
        [["S-B", "20260528125900", "20260528133000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [r["bed_type"] for r in rows] == ["ICU", "MEDSURG", "OBS", ""]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 6,
        "unmatched_count": 1,
        "unmatched_amount_cents": 3,
    }
