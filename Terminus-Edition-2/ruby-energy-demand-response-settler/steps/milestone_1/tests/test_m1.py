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


class TestMilestone1:
    def test_core_match_schema_and_positive_totals(self):
        """A fully valid settlement should match, preserve schema, and count positive totals."""
        build_program()
        write_inputs(
            [
                [
                    "SRC-CORE",
                    "METER-1",
                    "S-CORE",
                    "LOAD",
                    "25",
                    "20260528140000",
                    "CONFIRMED",
                    "F1",
                ],
            ],
            [
                [
                    "ACT-CORE",
                    "SRC-CORE",
                    "METER-1",
                    "S-CORE",
                    "LOAD",
                    "25",
                    "20260528140500",
                    "CURTAIL",
                    "F1",
                ],
            ],
            [["S-CORE", "20260528135900", "20260528143000", "OPEN"]],
        )

        rows, summary = run_program()

        assert (
            REPORT.read_text().splitlines()[0]
            == "settlement_id,parcel_id,meter_id,station_id,resource_type,amount,reason,status"
        )
        assert rows == [
            {
                "settlement_id": "ACT-CORE",
                "parcel_id": "SRC-CORE",
                "meter_id": "METER-1",
                "station_id": "S-CORE",
                "resource_type": "LOAD",
                "amount": "25",
                "reason": "CURTAIL",
                "status": "MATCHED",
            }
        ]
        assert summary == {
            "matched_count": 1,
            "matched_amount": 25,
            "unmatched_count": 0,
            "unmatched_amount": 0,
        }

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

    def test_malformed_source_or_settlement_timestamps_stay_unmatched(self):
        """Non-numeric source event_ts or action settle_ts values must not match otherwise valid rows."""
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
                    "SOLAR",
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
                    "LOAD",
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
                    "SOLAR",
                    "22",
                    "not-a-ts",
                    "BONUS",
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

    def test_latest_event_ts_wins_when_multiple_rows_qualify(self):
        """Latest event_ts selection should leave the older source available for an earlier second correction."""
        build_program()
        write_inputs(
            [
                ["P-TIE-1", "M1", "S-TIE", "LOAD", "50", "20260528140000", "CONFIRMED", "F1"],
                ["P-TIE-1", "M1", "S-TIE", "LOAD", "50", "20260528140200", "CONFIRMED", "F1"],
            ],
            [
                ["ACT-TIE-1", "P-TIE-1", "M1", "S-TIE", "LOAD", "50", "20260528140500", "CURTAIL", "F1"],
                ["ACT-TIE-2", "P-TIE-1", "M1", "S-TIE", "LOAD", "50", "20260528140100", "CURTAIL", "F1"],
            ],
            [["S-TIE", "20260528135900", "20260528143000", "OPEN"]],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert summary == {"matched_count": 2, "matched_amount": 100, "unmatched_count": 0, "unmatched_amount": 0}

    def test_equal_event_ts_tie_uses_earliest_source_row(self):
        """Equal event_ts candidates must resolve by earliest physical source input row."""
        build_program()
        write_inputs(
            [
                ["P-EQ", "M1", "S-EQ", "LOAD", "40", "20260528140000", "CONFIRMED", "F1"],
                ["P-EQ", "M1", "S-EQ", "LOAD", "40", "20260528140000", "CONFIRMED", "F1"],
            ],
            [
                ["ACT-EQ-1", "P-EQ", "M1", "S-EQ", "LOAD", "40", "20260528140500", "CURTAIL", "F1"],
                ["ACT-EQ-2", "P-EQ", "M1", "S-EQ", "LOAD", "40", "20260528140600", "CURTAIL", "F1"],
            ],
            [["S-EQ", "20260528135900", "20260528143000", "OPEN"]],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert summary == {"matched_count": 2, "matched_amount": 80, "unmatched_count": 0, "unmatched_amount": 0}

    def test_correction_alias_rejected_before_milestone_2(self):
        """Milestone 1 must reject alias resource_type values on the settlement row."""
        build_program()
        write_inputs(
            [["P-ALIAS", "M1", "S-AL", "LOAD", "10", "20260528140000", "CONFIRMED", "F1"]],
            [["ACT-ALIAS", "P-ALIAS", "M1", "S-AL", "LD", "10", "20260528140500", "CURTAIL", "F1"]],
            [["S-AL", "20260528135900", "20260528143000", "OPEN"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["resource_type"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 10}

    def test_full_parcel_id_must_match_not_prefix(self):
        """Prefix parcel_id matching must not satisfy the full-key contract."""
        build_program()
        write_inputs(
            [["SRC-FULL-1", "M1", "S-PFX", "LOAD", "15", "20260528140000", "CONFIRMED", "F1"]],
            [["ACT-PFX", "SRC-FULL", "M1", "S-PFX", "LOAD", "15", "20260528140500", "CURTAIL", "F1"]],
            [["S-PFX", "20260528135900", "20260528143000", "OPEN"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["resource_type"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 15}

    def test_invalid_correction_resource_type_stays_unmatched(self):
        """Invalid settlement resource_type must stay unmatched when the source row is otherwise eligible."""
        build_program()
        write_inputs(
            [["SRC-BAD-RT", "M1", "S-BRT", "LOAD", "12", "20260528140000", "CONFIRMED", "F1"]],
            [["ACT-BAD-RT", "SRC-BAD-RT", "M1", "S-BRT", "BAD", "12", "20260528140500", "CURTAIL", "F1"]],
            [["S-BRT", "20260528135900", "20260528143000", "OPEN"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["resource_type"] == ""
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 12}
