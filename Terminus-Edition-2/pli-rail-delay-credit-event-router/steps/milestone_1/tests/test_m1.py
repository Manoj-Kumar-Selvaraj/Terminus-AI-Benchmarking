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
