"""Milestone 5 verifier tests for settlement override precedence and gates."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "events.csv"
ACTION = APP / "data" / "settlements.csv"
WINDOWS = APP / "config" / "windows.csv"
POLICY = APP / "config" / "resource_policy.csv"
OVERRIDES = APP / "config" / "settlement_overrides.csv"
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


def write_inputs(source, action, windows, policy, overrides):
    """Overwrite all runtime data, policy, and override inputs."""
    write_csv(
        SOURCE,
        ["parcel_id", "meter_id", "station_id", "resource_type", "amount", "event_ts", "status", "feeder"],
        source,
    )
    write_csv(
        ACTION,
        ["settlement_id", "parcel_id", "meter_id", "station_id", "resource_type", "amount", "settle_ts", "reason", "feeder"],
        action,
    )
    write_csv(WINDOWS, ["station_id", "open_ts", "close_ts", "state"], windows)
    write_csv(POLICY, ["station_id", "resource_type", "enabled", "priority", "max_station_amount"], policy)
    write_csv(OVERRIDES, ["settlement_id", "mode", "resource_type", "expires_ts"], overrides)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)
    CONSUMPTION.unlink(missing_ok=True)


def run_program():
    """Run the reconciler and parse its primary outputs."""
    subprocess.run(["ruby", "/app/app/reconcile.rb"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        summary[key] = int(value)
    return rows, summary


def read_consumption():
    """Read selected physical source rows from the consumption trace."""
    with CONSUMPTION.open(newline="") as handle:
        return list(csv.DictReader(handle))


class TestMilestone5:
    def test_force_resource_uses_latest_valid_override_and_preserves_policy_gates(self):
        """Latest valid FORCE_RESOURCE should change only the effective resource type."""
        build_program()
        write_inputs(
            [["SRC-FORCE", "METER-1", "S-FORCE", "SOLAR", "25", "20260528150000", "CONFIRMED", "F1"]],
            [["ACT-FORCE", "SRC-FORCE", "METER-1", "S-FORCE", "LOAD", "25", "20260528151000", "CURTAIL", "F1"]],
            [["S-FORCE", "20260528145900", "20260528153000", "OPEN"]],
            [["S-FORCE", "LOAD", "true", "1", "100"], ["S-FORCE", "SOLAR", "true", "2", "100"]],
            [
                ["ACT-FORCE", "FORCE_RESOURCE", "LOAD", "20260528152000"],
                ["ACT-FORCE", "FORCE_RESOURCE", " qR ", "20260528152500"],
            ],
        )

        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["resource_type"] == "SOLAR"
        assert read_consumption() == [{"settlement_id": "ACT-FORCE", "event_row": "0"}]
        assert summary == {"matched_count": 1, "matched_amount": 25, "unmatched_count": 0, "unmatched_amount": 0}

    def test_deny_override_prevents_consumption_and_later_settlement_can_use_source(self):
        """DENY should win before source selection and leave the source available."""
        build_program()
        write_inputs(
            [["SRC-DENY", "METER-1", "S-DENY", "LOAD", "30", "20260528150000", "CONFIRMED", "F1"]],
            [
                ["ACT-DENY", "SRC-DENY", "METER-1", "S-DENY", "LOAD", "30", "20260528151000", "CURTAIL", "F1"],
                ["ACT-NEXT", "SRC-DENY", "METER-1", "S-DENY", "LOAD", "30", "20260528151100", "BONUS", "F1"],
            ],
            [["S-DENY", "20260528145900", "20260528153000", "OPEN"]],
            [["S-DENY", "LOAD", "true", "1", "100"]],
            [
                ["ACT-DENY", "FORCE_RESOURCE", "LOAD", "20260528152000"],
                ["ACT-DENY", "DENY", "", "20260528152000"],
            ],
        )

        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert [row["resource_type"] for row in rows] == ["", "LOAD"]
        assert read_consumption() == [{"settlement_id": "ACT-NEXT", "event_row": "0"}]
        assert summary == {"matched_count": 1, "matched_amount": 30, "unmatched_count": 1, "unmatched_amount": 30}

    def test_expired_malformed_and_invalid_resource_overrides_are_ignored(self):
        """Bad override rows should not change ordinary matching outcomes."""
        build_program()
        write_inputs(
            [
                ["SRC-EXP", "METER-1", "S-IGN", "LOAD", "10", "20260528150000", "CONFIRMED", "F1"],
                ["SRC-BAD", "METER-2", "S-IGN", "BATTERY", "20", "20260528150100", "CONFIRMED", "F2"],
            ],
            [
                ["ACT-EXP", "SRC-EXP", "METER-1", "S-IGN", "SOLAR", "10", "20260528151000", "CURTAIL", "F1"],
                ["ACT-BAD", "SRC-BAD", "METER-2", "S-IGN", "LOAD", "20", "20260528151100", "CORRECT", "F2"],
            ],
            [["S-IGN", "20260528145900", "20260528153000", "OPEN"]],
            [["S-IGN", "LOAD", "true", "1", "100"], ["S-IGN", "BATTERY", "true", "2", "100"]],
            [
                ["ACT-EXP", "FORCE_RESOURCE", "LD", "20260528150959"],
                ["ACT-BAD", "FORCE_RESOURCE", "BAD", "20260528152000"],
                ["ACT-BAD", "DENY", "", "not-a-time"],
            ],
        )

        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert read_consumption() == []
        assert summary == {"matched_count": 0, "matched_amount": 0, "unmatched_count": 2, "unmatched_amount": 30}

    def test_force_resource_does_not_bypass_running_cap_or_consumption_trace_rules(self):
        """FORCE_RESOURCE must still respect budget caps and avoid consuming rejected candidates."""
        build_program()
        write_inputs(
            [
                ["SRC-CAP-1", "METER-1", "S-OCAP", "SOLAR", "40", "20260528150000", "CONFIRMED", "F1"],
                ["SRC-CAP-2", "METER-2", "S-OCAP", "SOLAR", "20", "20260528150100", "CONFIRMED", "F2"],
            ],
            [
                ["ACT-CAP-1", "SRC-CAP-1", "METER-1", "S-OCAP", "LOAD", "40", "20260528151000", "CURTAIL", "F1"],
                ["ACT-CAP-2", "SRC-CAP-2", "METER-2", "S-OCAP", "LOAD", "20", "20260528151100", "CURTAIL", "F2"],
            ],
            [["S-OCAP", "20260528145900", "20260528153000", "OPEN"]],
            [["S-OCAP", "SOLAR", "true", "1", "50"], ["S-OCAP", "LOAD", "true", "2", "100"]],
            [
                ["ACT-CAP-1", "FORCE_RESOURCE", "QR", "20260528152000"],
                ["ACT-CAP-2", "FORCE_RESOURCE", "QR", "20260528152000"],
            ],
        )

        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["resource_type"] for row in rows] == ["SOLAR", ""]
        assert read_consumption() == [{"settlement_id": "ACT-CAP-1", "event_row": "0"}]
        assert summary == {"matched_count": 1, "matched_amount": 40, "unmatched_count": 1, "unmatched_amount": 20}
