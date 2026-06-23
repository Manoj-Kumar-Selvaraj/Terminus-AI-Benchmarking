"""Verifier tests for realtime energy demand response settlement."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "events.csv"
ACTION = APP / "data" / "settlements.csv"
WINDOWS = APP / "config" / "windows.csv"
REPORT = APP / "out" / "cod_demand_response_report.csv"
SUMMARY = APP / "out" / "cod_demand_response_summary.txt"


def build_program():
    """Prepare the reconciler for one verifier scenario."""
    pass


def write_csv(path, header, rows):
    """Write one CSV fixture."""
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(source, action, windows):
    """Overwrite all input files at runtime."""
    write_csv(
        SOURCE,
        [
            "parcel_id",
            "meter_id",
            "station_id",
            "resource_type",
            "amount",
            "event_ts",
            "status",
            "feeder",
        ],
        source,
    )
    write_csv(
        ACTION,
        [
            "settlement_id",
            "parcel_id",
            "meter_id",
            "station_id",
            "resource_type",
            "amount",
            "settle_ts",
            "reason",
            "feeder",
        ],
        action,
    )
    write_csv(WINDOWS, ["station_id", "open_ts", "close_ts", "state"], windows)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the reconciler and parse outputs."""
    subprocess.run(["ruby", "/app/app/reconcile.rb"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        summary[key] = int(value)
    return rows, summary


class TestMilestone2:
    def test_all_gates_consumption_and_positive_unmatched_totals(self):
        """Every identity, status, timestamp, reason, and consumption gate should reject bad candidates."""
        build_program()
        write_inputs(
            [
                [
                    "SRC-GATE-1",
                    "PARTY-1",
                    "S-G",
                    "LOAD",
                    "10",
                    "20260528140000",
                    "CONFIRMED",
                    "L1",
                ],
                [
                    "SRC-GATE-2",
                    "PARTY-2",
                    "S-G",
                    "LOAD",
                    "20",
                    "20260528140100",
                    "BAD",
                    "L2",
                ],
                [
                    "SRC-GATE-3",
                    "PARTY-3",
                    "S-G",
                    "SOLAR",
                    "30",
                    "20260528140200",
                    "CONFIRMED",
                    "L3",
                ],
                [
                    "SRC-GATE-4",
                    "PARTY-4",
                    "S-G",
                    "BAD",
                    "40",
                    "20260528140300",
                    "CONFIRMED",
                    "L4",
                ],
            ],
            [
                [
                    "ACT-A",
                    "SRC-GATE-1",
                    "PARTY-1",
                    "S-G",
                    "LOAD",
                    "10",
                    "20260528140500",
                    "CURTAIL",
                    "L1",
                ],
                [
                    "ACT-B",
                    "SRC-GATE-1",
                    "PARTY-1",
                    "S-G",
                    "LOAD",
                    "10",
                    "20260528140600",
                    "CURTAIL",
                    "L1",
                ],
                [
                    "ACT-C",
                    "SRC-GATE-2",
                    "PARTY-2",
                    "S-G",
                    "LOAD",
                    "20",
                    "20260528140700",
                    "CURTAIL",
                    "L2",
                ],
                [
                    "ACT-D",
                    "SRC-GATE-3",
                    "PARTY-X",
                    "S-G",
                    "SOLAR",
                    "30",
                    "20260528140700",
                    "BONUS",
                    "L3",
                ],
                [
                    "ACT-E",
                    "SRC-GATE-3",
                    "PARTY-3",
                    "S-G",
                    "SOLAR",
                    "31",
                    "20260528140700",
                    "BONUS",
                    "L3",
                ],
                [
                    "ACT-F",
                    "SRC-GATE-3",
                    "PARTY-3",
                    "S-G",
                    "SOLAR",
                    "30",
                    "20260528135959",
                    "BONUS",
                    "L3",
                ],
                [
                    "ACT-G",
                    "SRC-GATE-3",
                    "PARTY-3",
                    "S-G",
                    "SOLAR",
                    "30",
                    "20260528140700",
                    "INFO",
                    "L3",
                ],
                [
                    "ACT-H",
                    "SRC-GATE-4",
                    "PARTY-4",
                    "S-G",
                    "BAD",
                    "40",
                    "20260528140700",
                    "CORRECT",
                    "L4",
                ],
                [
                    "ACT-I",
                    "SRC-GATE-3",
                    "PARTY-3",
                    "S-G",
                    "SOLAR",
                    "30",
                    "20260528140700",
                    "BONUS",
                    "WRONG-FEEDER",
                ],
            ],
            [["S-G", "20260528135900", "20260528143000", "OPEN"]],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == [
            "MATCHED",
            "UNMATCHED",
            "UNMATCHED",
            "UNMATCHED",
            "UNMATCHED",
            "UNMATCHED",
            "UNMATCHED",
            "UNMATCHED",
            "UNMATCHED",
        ]
        assert rows[1]["resource_type"] == ""
        assert summary == {
            "matched_count": 1,
            "matched_amount": 10,
            "unmatched_count": 8,
            "unmatched_amount": 221,
        }


    def test_aliases_full_keys_and_canonical_output(self):
        """Aliases should match full source keys and emit canonical resource_type values."""
        build_program()
        write_inputs(
            [
                [
                    "SRC-100000001",
                    "PARTY-1",
                    "S-A",
                    "LOAD",
                    "12",
                    "20260528120500",
                    "CONFIRMED",
                    "LOC-1",
                ],
                [
                    "SRC-100000002",
                    "PARTY-2",
                    "S-A",
                    "SOLAR",
                    "34",
                    "20260528120600",
                    "CONFIRMED",
                    "LOC-2",
                ],
                [
                    "SRC-100000003",
                    "PARTY-3",
                    "S-B",
                    "BATTERY",
                    "56",
                    "20260528130500",
                    "CONFIRMED",
                    "LOC-3",
                ],
            ],
            [
                [
                    "ACT-1",
                    "SRC-100000001",
                    "PARTY-1",
                    "S-A",
                    "LD",
                    "12",
                    "20260528121000",
                    "CURTAIL",
                    "LOC-1",
                ],
                [
                    "ACT-2",
                    "SRC-100000002",
                    "PARTY-2",
                    "S-A",
                    "QR",
                    "34",
                    "20260528121100",
                    "BONUS",
                    "LOC-2",
                ],
                [
                    "ACT-3",
                    "SRC-100000003",
                    "PARTY-3",
                    "S-B",
                    "CC",
                    "56",
                    "20260528131000",
                    "CORRECT",
                    "LOC-3",
                ],
            ],
            [
                ["S-A", "20260528120000", "20260528123000", "OPEN"],
                ["S-B", "20260528130000", "20260528133000", "OPEN"],
            ],
        )
        rows, summary = run_program()
        assert (
            REPORT.read_text().splitlines()[0]
            == "settlement_id,parcel_id,meter_id,station_id,resource_type,amount,reason,status"
        )
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["resource_type"] for row in rows] == ["LOAD", "SOLAR", "BATTERY"]
        assert summary == {
            "matched_count": 3,
            "matched_amount": 102,
            "unmatched_count": 0,
            "unmatched_amount": 0,
        }

    def test_aliases_trim_and_case_fold_before_matching(self):
        """Aliases with mixed case and surrounding spaces should normalize on both source and settlement rows."""
        build_program()
        write_inputs(
            [
                [
                    "SRC-ALIAS-1",
                    "METER-1",
                    "S-ALIAS",
                    " ld ",
                    "15",
                    "20260528120000",
                    "CONFIRMED",
                    "F1",
                ],
                [
                    "SRC-ALIAS-2",
                    "METER-2",
                    "S-ALIAS",
                    " qR ",
                    "25",
                    "20260528120100",
                    "CONFIRMED",
                    "F2",
                ],
                [
                    "SRC-ALIAS-3",
                    "METER-3",
                    "S-ALIAS",
                    " cC ",
                    "35",
                    "20260528120200",
                    "CONFIRMED",
                    "F3",
                ],
            ],
            [
                [
                    "ACT-ALIAS-1",
                    "SRC-ALIAS-1",
                    "METER-1",
                    "S-ALIAS",
                    " ld ",
                    "15",
                    "20260528120500",
                    "CURTAIL",
                    "F1",
                ],
                [
                    "ACT-ALIAS-2",
                    "SRC-ALIAS-2",
                    "METER-2",
                    "S-ALIAS",
                    " qR ",
                    "25",
                    "20260528120600",
                    "BONUS",
                    "F2",
                ],
                [
                    "ACT-ALIAS-3",
                    "SRC-ALIAS-3",
                    "METER-3",
                    "S-ALIAS",
                    " cC ",
                    "35",
                    "20260528120700",
                    "CORRECT",
                    "F3",
                ],
            ],
            [["S-ALIAS", "20260528115900", "20260528123000", "OPEN"]],
        )

        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["resource_type"] for row in rows] == ["LOAD", "SOLAR", "BATTERY"]
        assert summary == {
            "matched_count": 3,
            "matched_amount": 75,
            "unmatched_count": 0,
            "unmatched_amount": 0,
        }

    def test_malformed_timestamps_remain_unmatched_with_aliases(self):
        """Alias normalization must not bypass numeric timestamp validation."""
        build_program()
        write_inputs(
            [
                [
                    "SRC-BAD-SOURCE-TS",
                    "METER-1",
                    "S-TIME",
                    "LOAD",
                    "11",
                    "bad-time",
                    "CONFIRMED",
                    "F1",
                ],
                [
                    "SRC-BAD-ACTION-TS",
                    "METER-2",
                    "S-TIME",
                    "BATTERY",
                    "22",
                    "20260528140100",
                    "CONFIRMED",
                    "F2",
                ],
            ],
            [
                [
                    "ACT-BAD-SOURCE-TS",
                    "SRC-BAD-SOURCE-TS",
                    "METER-1",
                    "S-TIME",
                    "LD",
                    "11",
                    "20260528140500",
                    "CURTAIL",
                    "F1",
                ],
                [
                    "ACT-BAD-ACTION-TS",
                    "SRC-BAD-ACTION-TS",
                    "METER-2",
                    "S-TIME",
                    "CC",
                    "22",
                    "not-a-ts",
                    "CORRECT",
                    "F2",
                ],
            ],
            [["S-TIME", "20260528135900", "20260528143000", "OPEN"]],
        )

        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert [row["resource_type"] for row in rows] == ["", ""]
        assert summary == {
            "matched_count": 0,
            "matched_amount": 0,
            "unmatched_count": 2,
            "unmatched_amount": 33,
        }

    def test_alias_tie_break_uses_latest_ts_then_earliest_row(self):
        """Alias-normalized latest event_ts selection should leave older rows for earlier second corrections."""
        build_program()
        write_inputs(
            [
                ["P-AL-TIE", "M1", "S-ALT", "LOAD", "30", "20260528140000", "CONFIRMED", "F1"],
                ["P-AL-TIE", "M1", "S-ALT", "LOAD", "30", "20260528140200", "CONFIRMED", "F1"],
            ],
            [
                ["ACT-AL-1", "P-AL-TIE", "M1", "S-ALT", "LD", "30", "20260528140500", "CURTAIL", "F1"],
                ["ACT-AL-2", "P-AL-TIE", "M1", "S-ALT", "LD", "30", "20260528140100", "BONUS", "F1"],
            ],
            [["S-ALT", "20260528135900", "20260528143000", "OPEN"]],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["resource_type"] for row in rows] == ["LOAD", "LOAD"]
        assert summary == {"matched_count": 2, "matched_amount": 60, "unmatched_count": 0, "unmatched_amount": 0}
