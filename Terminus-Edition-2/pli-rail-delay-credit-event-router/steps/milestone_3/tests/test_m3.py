"""Verifier tests for rail platform delay credit PL/I task."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SRC = APP / "data/trips.psv"
ACT = APP / "data/credits.psv"
WIN = APP / "config/windows.psv"
RULES = APP / "src/reconcile_rules.pli"
REPORT = APP / "out/delay_credit_report.csv"
SUMMARY = APP / "out/delay_credit_summary.txt"


def write_psv(path, header, rows):
    path.write_text(
        "|".join(header) + "\n" + "\n".join("|".join(r) for r in rows) + "\n"
    )


def write_rules(
    status="DELAYED",
    open_state="OPEN",
    reasons=("LATE", "CANCEL", "REROUTE"),
    aliases=("LOC=>LOCAL", "EXP=>EXPRESS", "AIR=>AIRPORT"),
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
            "trip_id",
            "rider_id",
            "station_id",
            "fare_type",
            "credit_cents",
            "tap_ts",
            "status",
            "platform",
        ],
        src,
    )
    write_psv(
        ACT,
        [
            "action_id",
            "trip_id",
            "rider_id",
            "station_id",
            "fare_type",
            "credit_cents",
            "credit_ts",
            "reason",
            "platform",
        ],
        act,
    )
    write_psv(WIN, ["station_id", "open_ts", "close_ts", "state"], wins)
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
            ["SRC-1", "PARTY-1", "S-A", "LOCAL", "10", "20260528120000", "READY", "L1"],
            ["SRC-2", "PARTY-2", "S-A", "EXPRESS", "20", "20260528120100", "BAD", "L2"],
            [
                "SRC-3",
                "PARTY-3",
                "S-A",
                "EXPRESS",
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
                "LOCAL",
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
                "LOCAL",
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
                "EXPRESS",
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
                "EXPRESS",
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
                "EXPRESS",
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
                "EXPRESS",
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
    assert rows[1]["fare_type"] == ""
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
            ["A-1", "P-1", "S-B", "LOCAL", "1", "20260528130000", "DELAYED", "L1"],
            ["A-2", "P-2", "S-B", "EXPRESS", "2", "20260528130100", "DELAYED", "L2"],
            ["A-3", "P-3", "S-B", "AIRPORT", "3", "20260528130200", "DELAYED", "L3"],
        ],
        [
            ["X-1", "A-1", "P-1", "S-B", "loc", "1", "20260528130500", "LATE", "L1"],
            ["X-2", "A-2", "P-2", "S-B", "EXP", "2", "20260528130600", "CANCEL", "L2"],
            ["X-3", "A-3", "P-3", "S-B", "AIR", "3", "20260528130700", "REROUTE", "L3"],
            ["X-4", "A-3", "P-3", "S-B", "BAD", "3", "20260528130800", "REROUTE", "L3"],
        ],
        [["S-B", "20260528125900", "20260528133000", "OPEN"]],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [r["fare_type"] for r in rows] == ["LOCAL", "EXPRESS", "AIRPORT", ""]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 6,
        "unmatched_count": 1,
        "unmatched_amount_cents": 3,
    }


def test_milestone3_windows_latest_candidate_and_malformed_times():
    """Milestone 3 rejects closed/malformed windows and picks latest eligible source timestamp."""
    write_rules(open_state="LIVE")
    write_inputs(
        [
            ["W-1", "P-1", "S-O", "LOCAL", "1", "20260528140000", "DELAYED", "L1"],
            ["W-2", "P-2", "S-C", "LOCAL", "2", "20260528140000", "DELAYED", "L2"],
            ["W-3", "P-3", "S-O", "EXPRESS", "3", "bad-time", "DELAYED", "L3"],
            ["DUP", "P-4", "S-O", "AIRPORT", "4", "20260528140100", "DELAYED", "L4"],
            ["DUP", "P-4", "S-O", "AIRPORT", "4", "20260528140200", "DELAYED", "L4"],
        ],
        [
            ["Y-1", "W-1", "P-1", "S-O", "LOC", "1", "20260528140500", "LATE", "L1"],
            ["Y-2", "W-2", "P-2", "S-C", "LOC", "2", "20260528140500", "LATE", "L2"],
            ["Y-3", "W-3", "P-3", "S-O", "EXP", "3", "20260528140500", "CANCEL", "L3"],
            ["Y-4", "DUP", "P-4", "S-O", "AIR", "4", "20260528140600", "REROUTE", "L4"],
            ["Y-5", "W-1", "P-1", "S-O", "LOC", "1", "20260528150000", "LATE", "L1"],
        ],
        [
            ["S-O", "20260528135900", "20260528143000", "LIVE"],
            ["S-C", "20260528135900", "20260528143000", "CLOS"],
        ],
    )
    rows, summary = run_program()
    assert [r["status"] for r in rows] == [
        "MATCHED",
        "UNMATCHED",
        "UNMATCHED",
        "MATCHED",
        "UNMATCHED",
    ]
    assert [r["fare_type"] for r in rows] == ["LOCAL", "", "", "AIRPORT", ""]
    assert summary == {
        "matched_count": 2,
        "matched_amount_cents": 5,
        "unmatched_count": 3,
        "unmatched_amount_cents": 6,
    }
