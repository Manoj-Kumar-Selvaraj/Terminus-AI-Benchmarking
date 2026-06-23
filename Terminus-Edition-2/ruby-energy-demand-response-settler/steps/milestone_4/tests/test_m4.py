"""Milestone 4 verifier tests for station/resource policy, ANY selection, and running caps."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "events.csv"
ACTION = APP / "data" / "settlements.csv"
WINDOWS = APP / "config" / "windows.csv"
POLICY = APP / "config" / "resource_policy.csv"
REPORT = APP / "out" / "cod_demand_response_report.csv"
SUMMARY = APP / "out" / "cod_demand_response_summary.txt"
CONSUMPTION = APP / "out" / "event_consumption.csv"


def build_program():
    """Prepare the reconciler for one verifier scenario."""
    pass


def write_csv(path, header, rows):
    """Write one CSV fixture."""
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(source, action, windows, policy):
    """Overwrite all input and policy files at runtime."""
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
    write_csv(POLICY, ["station_id", "resource_type", "enabled", "priority", "max_station_amount"], policy)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)
    CONSUMPTION.unlink(missing_ok=True)


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


def read_consumption():
    """Read physical event-row selections from the consumption trace."""
    with CONSUMPTION.open(newline="") as handle:
        return list(csv.DictReader(handle))


class TestMilestone4:
    def test_disabled_policy_resource_rejects_otherwise_valid_named_settlement(self):
        """A disabled station/resource policy row must reject a named settlement that passes M1-M3 gates."""
        build_program()
        write_inputs(
            [["SRC-DISABLED", "METER-1", "S-POL", "BATTERY", "40", "20260528150000", "CONFIRMED", "F1"]],
            [["ACT-DISABLED", "SRC-DISABLED", "METER-1", "S-POL", "CC", "40", "20260528150500", "CORRECT", "F1"]],
            [["S-POL", "20260528145900", "20260528153000", "OPEN"]],
            [
                ["S-POL", "LOAD", "true", "10", "100"],
                ["S-POL", "SOLAR", "true", "20", "100"],
                ["S-POL", "BATTERY", "false", "30", "100"],
            ],
        )

        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["resource_type"] == ""
        assert read_consumption() == []
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 1, "unmatched_amount": 40}

    def test_any_chooses_latest_timestamp_before_policy_priority(self):
        """ANY should prefer the latest eligible event_ts even when that row has lower policy priority."""
        build_program()
        write_inputs(
            [
                ["SRC-ANY", "METER-1", "S-ANY", "LOAD", "15", "20260528150000", "CONFIRMED", "F1"],
                ["SRC-ANY", "METER-1", "S-ANY", "SOLAR", "15", "20260528150200", "CONFIRMED", "F1"],
            ],
            [["ACT-ANY", "SRC-ANY", "METER-1", "S-ANY", "ANY", "15", "20260528151000", "BONUS", "F1"]],
            [["S-ANY", "20260528145900", "20260528153000", "OPEN"]],
            [
                ["S-ANY", "LOAD", "true", "1", "100"],
                ["S-ANY", "SOLAR", "true", "99", "100"],
            ],
        )

        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["resource_type"] == "SOLAR"
        assert read_consumption() == [
            {"settlement_id": "ACT-ANY", "event_row": "1"},
        ]
        assert summary["matched_amount"] == 15

    def test_any_same_timestamp_uses_policy_priority_then_source_order_and_consumption(self):
        """ANY equal-timestamp candidates should use policy priority, row order, and row consumption."""
        build_program()
        write_inputs(
            [
                ["SRC-TIE", "METER-1", "S-TIE", "LOAD", "10", "20260528150000", "CONFIRMED", "F1"],
                ["SRC-TIE", "METER-1", "S-TIE", "SOLAR", "10", "20260528150000", "CONFIRMED", "F1"],
                ["SRC-TIE", "METER-1", "S-TIE", "SOLAR", "10", "20260528150000", "CONFIRMED", "F1"],
            ],
            [
                ["ACT-TIE-1", "SRC-TIE", "METER-1", "S-TIE", "ANY", "10", "20260528151000", "BONUS", "F1"],
                ["ACT-TIE-2", "SRC-TIE", "METER-1", "S-TIE", "ANY", "10", "20260528151100", "BONUS", "F1"],
                ["ACT-TIE-3", "SRC-TIE", "METER-1", "S-TIE", "ANY", "10", "20260528151200", "BONUS", "F1"],
            ],
            [["S-TIE", "20260528145900", "20260528153000", "OPEN"]],
            [
                ["S-TIE", "LOAD", "true", "50", "100"],
                ["S-TIE", "SOLAR", "true", "5", "100"],
            ],
        )

        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["resource_type"] for row in rows] == ["SOLAR", "SOLAR", "LOAD"]
        assert read_consumption() == [
            {"settlement_id": "ACT-TIE-1", "event_row": "1"},
            {"settlement_id": "ACT-TIE-2", "event_row": "2"},
            {"settlement_id": "ACT-TIE-3", "event_row": "0"},
        ]
        assert summary == {"matched_count": 3, "matched_amount": 30, "unmatched_count": 0, "unmatched_amount": 0}

    def test_running_cap_is_partitioned_by_station_and_selected_resource_type(self):
        """max_station_amount should cap matches per station/resource without affecting other resources."""
        build_program()
        write_inputs(
            [
                ["SRC-CAP-1", "METER-1", "S-CAP", "LOAD", "40", "20260528150000", "CONFIRMED", "F1"],
                ["SRC-CAP-2", "METER-2", "S-CAP", "LOAD", "20", "20260528150100", "CONFIRMED", "F2"],
                ["SRC-CAP-3", "METER-3", "S-CAP", "SOLAR", "20", "20260528150200", "CONFIRMED", "F3"],
            ],
            [
                ["ACT-CAP-1", "SRC-CAP-1", "METER-1", "S-CAP", "LOAD", "40", "20260528151000", "CURTAIL", "F1"],
                ["ACT-CAP-2", "SRC-CAP-2", "METER-2", "S-CAP", "LOAD", "20", "20260528151100", "CURTAIL", "F2"],
                ["ACT-CAP-3", "SRC-CAP-3", "METER-3", "S-CAP", "QR", "20", "20260528151200", "CURTAIL", "F3"],
            ],
            [["S-CAP", "20260528145900", "20260528153000", "OPEN"]],
            [
                ["S-CAP", "LOAD", "true", "10", "50"],
                ["S-CAP", "SOLAR", "true", "20", "50"],
            ],
        )

        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["resource_type"] for row in rows] == ["LOAD", "", "SOLAR"]
        assert read_consumption() == [
            {"settlement_id": "ACT-CAP-1", "event_row": "0"},
            {"settlement_id": "ACT-CAP-3", "event_row": "2"},
        ]
        assert summary == {"matched_count": 2, "matched_amount": 60, "unmatched_count": 1, "unmatched_amount": 20}

    def test_any_skips_over_budget_latest_candidate_before_selecting_older_enabled_resource(self):
        """ANY selection should skip an over-budget latest source and choose an older eligible resource."""
        build_program()
        write_inputs(
            [
                ["SRC-SKIP", "METER-1", "S-SKIP", "SOLAR", "30", "20260528150000", "CONFIRMED", "F1"],
                ["SRC-SKIP", "METER-1", "S-SKIP", "LOAD", "30", "20260528150200", "CONFIRMED", "F1"],
            ],
            [["ACT-SKIP", "SRC-SKIP", "METER-1", "S-SKIP", "ANY", "30", "20260528151000", "BONUS", "F1"]],
            [["S-SKIP", "20260528145900", "20260528153000", "OPEN"]],
            [
                ["S-SKIP", "LOAD", "true", "1", "20"],
                ["S-SKIP", "SOLAR", "true", "2", "100"],
            ],
        )

        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["resource_type"] == "SOLAR"
        assert read_consumption() == [
            {"settlement_id": "ACT-SKIP", "event_row": "0"},
        ]
        assert summary == {"matched_count": 1, "matched_amount": 30, "unmatched_count": 0, "unmatched_amount": 0}

    def test_running_cap_exact_boundary_matches_and_consumption_still_applies(self):
        """A cap reached exactly should still match while duplicate later settlements cannot reuse the row."""
        build_program()
        write_inputs(
            [
                ["SRC-SAVE-1", "METER-1", "S-SAVE", "LOAD", "45", "20260528150000", "CONFIRMED", "F1"],
                ["SRC-SAVE-2", "METER-2", "S-SAVE", "LOAD", "10", "20260528150100", "CONFIRMED", "F2"],
            ],
            [
                ["ACT-SAVE-1", "SRC-SAVE-1", "METER-1", "S-SAVE", "LOAD", "45", "20260528151000", "CURTAIL", "F1"],
                ["ACT-SAVE-2", "SRC-SAVE-2", "METER-2", "S-SAVE", "LOAD", "10", "20260528151100", "CURTAIL", "F2"],
                ["ACT-SAVE-3", "SRC-SAVE-2", "METER-2", "S-SAVE", "LOAD", "10", "20260528151200", "CURTAIL", "F2"],
            ],
            [["S-SAVE", "20260528145900", "20260528153000", "OPEN"]],
            [["S-SAVE", "LOAD", "true", "10", "55"]],
        )

        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert read_consumption() == [
            {"settlement_id": "ACT-SAVE-1", "event_row": "0"},
            {"settlement_id": "ACT-SAVE-2", "event_row": "1"},
        ]
        assert summary == {"matched_count": 2, "matched_amount": 55, "unmatched_count": 1, "unmatched_amount": 10}

    def test_malformed_policy_rows_do_not_enable_candidates_or_any_priority(self):
        """Missing, disabled, nonnumeric priority, and nonnumeric cap policy rows should not enable candidates."""
        build_program()
        write_inputs(
            [
                ["SRC-POL-1", "METER-1", "S-MAL", "LOAD", "11", "20260528150000", "CONFIRMED", "F1"],
                ["SRC-POL-2", "METER-2", "S-MAL", "SOLAR", "22", "20260528150100", "CONFIRMED", "F2"],
                ["SRC-POL-3", "METER-3", "S-MAL", "BATTERY", "33", "20260528150200", "CONFIRMED", "F3"],
            ],
            [
                ["ACT-POL-1", "SRC-POL-1", "METER-1", "S-MAL", "LOAD", "11", "20260528151000", "CURTAIL", "F1"],
                ["ACT-POL-2", "SRC-POL-2", "METER-2", "S-MAL", "ANY", "22", "20260528151100", "CURTAIL", "F2"],
                ["ACT-POL-3", "SRC-POL-3", "METER-3", "S-MAL", "ANY", "33", "20260528151200", "CURTAIL", "F3"],
            ],
            [["S-MAL", "20260528145900", "20260528153000", "OPEN"]],
            [
                ["S-MAL", "LOAD", "true", "bad-priority", "100"],
                ["S-MAL", "SOLAR", "false", "20", "100"],
                ["S-MAL", "BATTERY", "true", "30", "bad-cap"],
            ],
        )

        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert [row["resource_type"] for row in rows] == ["", "", ""]
        assert read_consumption() == []
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 3, "unmatched_amount": 66}

    def test_any_does_not_bypass_window_or_identity_gates(self):
        """ANY policy matching must still honor windows, feeder equality, and full identity gates."""
        build_program()
        write_inputs(
            [
                ["SRC-ANY-GATE-1", "METER-1", "S-GATE", "LOAD", "12", "20260528150000", "CONFIRMED", "F1"],
                ["SRC-ANY-GATE-2", "METER-2", "S-GATE", "SOLAR", "13", "20260528150100", "CONFIRMED", "F2"],
            ],
            [
                ["ACT-ANY-GATE-1", "SRC-ANY-GATE-1", "METER-1", "S-GATE", "ANY", "12", "20260528154000", "CURTAIL", "F1"],
                ["ACT-ANY-GATE-2", "SRC-ANY-GATE-2", "METER-2", "S-GATE", "ANY", "13", "20260528151000", "CURTAIL", "WRONG"],
            ],
            [["S-GATE", "20260528145900", "20260528153000", "OPEN"]],
            [
                ["S-GATE", "LOAD", "true", "10", "100"],
                ["S-GATE", "SOLAR", "true", "20", "100"],
            ],
        )

        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert read_consumption() == []
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 2, "unmatched_amount": 25}

    def test_any_kind_emitted_as_canonical_not_any_in_report(self):
        """Matched ANY settlements must emit the selected source canonical resource_type and accept mixed-case enabled."""
        build_program()
        write_inputs(
            [["SRC-ANY-OUT", "METER-1", "S-ANY", "BATTERY", "97", "20260528150000", "CONFIRMED", "F1"]],
            [["ACT-ANY-OUT", "SRC-ANY-OUT", "METER-1", "S-ANY", "ANY", "97", "20260528151000", "CORRECT", "F1"]],
            [["S-ANY", "20260528145900", "20260528153000", "OPEN"]],
            [["S-ANY", "BATTERY", "TrUe", "10", "100"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["reason"] == "CORRECT"
        assert rows[0]["resource_type"] == "BATTERY"
        assert rows[0]["resource_type"] != "ANY"
        assert read_consumption() == [{"settlement_id": "ACT-ANY-OUT", "event_row": "0"}]
        assert summary == {"matched_count": 1, "matched_amount": 97, "unmatched_count": 0, "unmatched_amount": 0}
