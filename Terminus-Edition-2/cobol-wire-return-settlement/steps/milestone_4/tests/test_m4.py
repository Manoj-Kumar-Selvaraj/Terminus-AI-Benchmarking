"""Milestone 4 tests for runtime wire-reason settlement controls."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
WIRES = APP / "data" / "wires.dat"
RETURNS = APP / "data" / "returns.dat"
CALENDAR = APP / "config" / "cycle_calendar.txt"
CONTROLS = APP / "config" / "reason_controls.csv"
REPORT = APP / "out" / "wire_return_report.csv"
SUMMARY = APP / "out" / "wire_return_summary.txt"


def assert_cobol_binary():
    """Verify the batch still comes from the COBOL compile path."""
    compile_script = (APP / "scripts" / "compile.sh").read_text().lower()
    assert "cobc" in compile_script
    assert ".cbl" in compile_script
    assert any((APP / "src").glob("*.cbl"))
    assert (APP / "build" / "batch").read_bytes().startswith(b"\x7fELF")


def compile_program():
    """Compile the COBOL wire return program."""
    subprocess.run(["/app/scripts/compile.sh"], check=True, cwd=APP, timeout=60)
    assert_cobol_binary()


def write_csv(path, header, rows):
    """Write a small CSV config fixture."""
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def write_inputs(wires, returns, calendar, controls=None):
    """Rewrite fixed-width data, cycle calendar, and reason controls."""
    WIRES.write_text("\n".join(wires) + "\n")
    RETURNS.write_text("\n".join(returns) + "\n")
    CALENDAR.write_text("\n".join(calendar) + "\n")
    write_csv(
        CONTROLS,
        ["reason", "enabled", "max_open_days"],
        controls
        if controls is not None
        else [["CON", "Y", "2"], ["REF", "Y", "2"], ["ADM", "Y", "2"], ["B2B", "Y", "1"]],
    )
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and return parsed report and summary outputs."""
    subprocess.run(["/app/build/batch"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        summary[key] = int(value)
    return rows, summary


class TestMilestone4:
    """Verify reason-control config composes with settlement cycle matching."""

    def test_reason_specific_day_limit_overrides_default_cycle_window(self):
        """B2B can have a shorter configured return window than CON or REF."""
        compile_program()
        write_inputs(
            [
                "WWIR410000001B2B0000001100ACCT4101S20260601",
                "WWIR410000002REF0000001200ACCT4102S20260601",
            ],
            [
                "RWIR4100000010000001100ACCT410120260603",
                "RWIR4100000020000001200ACCT410220260603",
            ],
            ["20260601 OPEN", "20260602 OPEN", "20260603 OPEN"],
            controls=[["B2B", "Y", "1"], ["REF", "Y", "2"], ["CON", "Y", "2"], ["ADM", "Y", "2"]],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["EXCEPTION", "CLEARED"]
        assert [row["reason"] for row in rows] == ["", "REF"]
        assert summary == {
            "cleared_count": 1,
            "cleared_amount_cents": 1200,
            "exception_count": 1,
            "exception_amount_cents": 1100,
        }

    def test_disabled_missing_and_malformed_reason_controls_reject_candidates(self):
        """Missing, disabled, or malformed reason-control rows should make matching wires ineligible."""
        compile_program()
        write_inputs(
            [
                "WWIR420000001CON0000000100ACCT4201S20260601",
                "WWIR420000002REF0000000200ACCT4202S20260601",
                "WWIR420000003ADM0000000300ACCT4203S20260601",
                "WWIR420000004B2B0000000400ACCT4204S20260601",
            ],
            [
                "RWIR4200000010000000100ACCT420120260602",
                "RWIR4200000020000000200ACCT420220260602",
                "RWIR4200000030000000300ACCT420320260602",
                "RWIR4200000040000000400ACCT420420260602",
            ],
            ["20260601 OPEN", "20260602 OPEN"],
            controls=[["REF", "N", "2"], ["ADM", "Y", "bad"], ["B2B", " yes ", "1"]],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["EXCEPTION", "EXCEPTION", "EXCEPTION", "CLEARED"]
        assert [row["reason"] for row in rows] == ["", "", "", "B2B"]
        assert summary["cleared_amount_cents"] == 400
        assert summary["exception_amount_cents"] == 600

    def test_latest_wire_selection_skips_disabled_reason_before_ranking(self):
        """A newer wire with disabled reason control must be ignored before selecting by latest date."""
        compile_program()
        write_inputs(
            [
                "WWIR430000001CON0000000900ACCT4301S20260601",
                "WWIR430000001B2B0000000900ACCT4301S20260602",
            ],
            ["RWIR4300000010000000900ACCT430120260603"],
            ["20260601 OPEN", "20260602 OPEN", "20260603 OPEN"],
            controls=[["CON", "Y", "2"], ["B2B", "N", "2"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "CLEARED"
        assert rows[0]["reason"] == "CON"
        assert summary == {
            "cleared_count": 1,
            "cleared_amount_cents": 900,
            "exception_count": 0,
            "exception_amount_cents": 0,
        }

    def test_duplicate_reason_control_uses_last_valid_row(self):
        """When duplicate valid controls exist, the later row should set the effective limit."""
        compile_program()
        write_inputs(
            ["WWIR440000001ADM0000000700ACCT4401S20260601"],
            ["RWIR4400000010000000700ACCT440120260603"],
            ["20260601 OPEN", "20260602 OPEN", "20260603 OPEN"],
            controls=[["ADM", "Y", "0"], ["ADM", "1", "2"]],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "CLEARED"
        assert rows[0]["reason"] == "ADM"
        assert summary["cleared_count"] == 1
        assert summary["cleared_amount_cents"] == 700

    def test_reason_and_day_limit_fields_are_trimmed(self):
        """Whitespace around reason and max_open_days must not invalidate a control."""
        compile_program()
        write_inputs(
            ["WWIR445000001CON0000000750ACCT4451S20260601"],
            ["RWIR4450000010000000750ACCT445120260603"],
            ["20260601 OPEN", "20260602 OPEN", "20260603 OPEN"],
            controls=[[" CON ", " y ", " 2 "]],
        )
        rows, summary = run_program()

        assert rows == [
            {
                "wire_id": "WIR445000001",
                "account_id": "ACCT4451",
                "reason": "CON",
                "amount_cents": "0000000750",
                "status": "CLEARED",
            }
        ]
        assert summary == {
            "cleared_count": 1,
            "cleared_amount_cents": 750,
            "exception_count": 0,
            "exception_amount_cents": 0,
        }

    def test_blank_and_unknown_reason_control_rows_reject_wires(self):
        """Blank control fields and alias-like unknown reasons must make wires ineligible."""
        compile_program()
        write_inputs(
            [
                "WWIR450000001CON0000000500ACCT4501S20260601",
                "WWIR450000002REF0000000600ACCT4502S20260601",
            ],
            [
                "RWIR4500000010000000500ACCT450120260602",
                "RWIR4500000020000000600ACCT450220260602",
            ],
            ["20260601 OPEN", "20260602 OPEN"],
            controls=[
                ["", "Y", "2"],
                ["XYZ", "Y", "2"],
                ["REF", "", "2"],
                ["REF", "Y", ""],
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["EXCEPTION", "EXCEPTION"]
        assert all(row["reason"] == "" for row in rows)
        assert summary == {
            "cleared_count": 0,
            "cleared_amount_cents": 0,
            "exception_count": 2,
            "exception_amount_cents": 1100,
        }
