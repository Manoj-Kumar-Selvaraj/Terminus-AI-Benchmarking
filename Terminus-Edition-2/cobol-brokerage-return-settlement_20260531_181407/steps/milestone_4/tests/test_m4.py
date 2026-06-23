"""Milestone 4 tests for policy-driven reason codes and ANY wildcard matching."""

import csv
import subprocess
from pathlib import Path

APP = Path("/app")
WIRES = APP / "data" / "wires.dat"
RETURNS = APP / "data" / "returns.dat"
CALENDAR = APP / "config" / "cycle_calendar.txt"
REASON_CODES = APP / "config" / "reason_codes.csv"
REPORT = APP / "out" / "wire_return_report.csv"
SUMMARY = APP / "out" / "wire_return_summary.txt"
COMPILE_TIMEOUT = 30
RUN_TIMEOUT = 10

DEFAULT_CALENDAR = [
    "20260430 OPEN",
    "20260501 OPEN",
    "20260502 OPEN",
    "20260503 OPEN",
    "20260504 OPEN",
]


def assert_cobol_binary():
    """Verify the batch still comes from the COBOL compile path."""
    compile_script = (APP / "scripts" / "compile.sh").read_text().lower()
    assert "cobc" in compile_script
    assert ".cbl" in compile_script
    assert any((APP / "src").glob("*.cbl"))
    assert (APP / "build" / "batch").read_bytes().startswith(b"\x7fELF")


def compile_program():
    """Compile the COBOL wire return program."""
    subprocess.run(["/app/scripts/compile.sh"], check=True, cwd=APP, timeout=COMPILE_TIMEOUT)
    assert_cobol_binary()


def write_inputs(wires, returns, calendar=None):
    """Rewrite fixed-width input files and optionally the cycle calendar."""
    WIRES.write_text("\n".join(wires) + "\n")
    RETURNS.write_text("\n".join(returns) + "\n")
    if calendar is not None:
        CALENDAR.write_text("\n".join(calendar) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_methods(rows):
    """Replace reason code policy (header + rows)."""
    REASON_CODES.write_text("code,meaning,enabled,priority\n" + "\n".join(rows) + "\n")


def run_program():
    """Run the compiled program and return parsed report and summary outputs."""
    subprocess.run(["/app/build/batch"], check=True, cwd=APP, timeout=RUN_TIMEOUT)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        summary[key] = int(value)
    return rows, summary


class TestMilestone3Regression:
    """Key Milestone 3 behaviors must still pass under the M4 policy-driven code."""

    def test_cycle_window_clears_within_two_open_days(self):
        """A return within the two-open-day window should still clear."""
        compile_program()
        write_inputs(
            [
                "WWIR910000001CON0000000100ACCT9101S20260430",
                "WWIR910000002REF0000000200ACCT9102S20260429",
            ],
            [
                "RWIR9100000010000000100ACCT910120260501",
                "RWIR9100000020000000200ACCT910220260504",
            ],
            DEFAULT_CALENDAR,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "CLEARED"
        assert rows[1]["status"] == "EXCEPTION"
        assert summary["cleared_count"] == 1
        assert summary["cleared_amount_cents"] == 100
        assert summary["exception_count"] == 1
        assert summary["exception_amount_cents"] == 200

    def test_closed_settlement_date_blocks_clearing(self):
        """A wire with a CLOSED settlement date must not clear any return."""
        compile_program()
        write_inputs(
            ["WWIR950000001CON0000000100ACCT9501S20260502"],
            ["RWIR9500000010000000100ACCT950120260503"],
            ["20260501 OPEN", "20260502 CLOSED", "20260503 OPEN"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "EXCEPTION"
        assert rows[0]["reason"] == ""
        assert summary["cleared_count"] == 0
        assert summary["exception_amount_cents"] == 100

    def test_duplicate_returns_deduplicated_with_dates(self):
        """Consumption must prevent the same wire from clearing two identical returns."""
        compile_program()
        write_inputs(
            ["WWIR960000001B2B0000000400ACCT9601S20260501"],
            [
                "RWIR9600000010000000400ACCT960120260502",
                "RWIR9600000010000000400ACCT960120260502",
            ],
            ["20260501 OPEN", "20260502 OPEN"],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["CLEARED", "EXCEPTION"]
        assert [row["reason"] for row in rows] == ["B2B", ""]
        assert summary["cleared_count"] == 1
        assert summary["cleared_amount_cents"] == 400

    def test_undated_returns_still_clear_without_calendar(self):
        """M1/M2-style records with no date fields must still clear correctly."""
        compile_program()
        write_inputs(
            ["WWIR501000001CON0000007700ACCT5011S"],
            ["RWIR5010000010000007700ACCT5011"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "CLEARED"
        assert rows[0]["reason"] == "CON"
        assert summary["cleared_amount_cents"] == 7700


class TestMilestone4:
    """Policy-driven reason codes and ANY wildcard matching."""

    def test_disabled_reason_rejects_otherwise_valid_return(self):
        """A return whose wire has a disabled reason code must be EXCEPTION."""
        compile_program()
        write_methods([
            "CON,consumer,true,2",
            "REF,refund,false,1",
            "ADM,admin,true,3",
            "B2B,business,true,4",
        ])
        write_inputs(
            ["WWIR501000002REF0000003200ACCT5012S20260501"],
            ["RWIR5010000020000003200ACCT501220260502REF"],
            DEFAULT_CALENDAR,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "EXCEPTION"
        assert rows[0]["reason"] == ""
        assert summary["cleared_count"] == 0
        assert summary["exception_amount_cents"] == 3200

    def test_any_same_date_uses_lower_priority_reason(self):
        """When two wires tie on date, ANY should pick the lower priority reason code."""
        compile_program()
        write_methods([
            "CON,consumer,true,3",
            "B2B,business,true,1",
        ])
        write_inputs(
            [
                "WWIR502000001CON0000000600ACCT5020S20260430",
                "WWIR502000001B2B0000000600ACCT5020S20260430",
            ],
            ["RWIR5020000010000000600ACCT502020260501ANY"],
            DEFAULT_CALENDAR,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "CLEARED"
        assert rows[0]["reason"] == "B2B"
        assert summary["cleared_count"] == 1
        assert summary["cleared_amount_cents"] == 600

    def test_any_equal_priority_tie_uses_earliest_wire_input_row(self):
        """When two wires share date and priority, ANY picks the first wire in input order."""
        compile_program()
        write_methods([
            "CON,consumer,true,2",
            "ADM,admin,true,2",
        ])
        write_inputs(
            [
                "WWIR503000001CON0000000900ACCT5030S20260430",
                "WWIR503000001ADM0000000900ACCT5030S20260430",
            ],
            ["RWIR5030000010000000900ACCT503020260501ANY"],
            DEFAULT_CALENDAR,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "CLEARED"
        assert rows[0]["reason"] == "CON"
        assert summary["cleared_count"] == 1

    def test_any_consumes_wire_and_second_any_takes_next_best(self):
        """Each ANY return consumes its selected wire; the next ANY picks the next best."""
        compile_program()
        write_methods([
            "CON,consumer,true,2",
            "B2B,business,true,1",
        ])
        write_inputs(
            [
                "WWIR504000001CON0000000500ACCT5040S20260430",
                "WWIR504000001B2B0000000500ACCT5040S20260430",
            ],
            [
                "RWIR5040000010000000500ACCT504020260501ANY",
                "RWIR5040000010000000500ACCT504020260501ANY",
            ],
            DEFAULT_CALENDAR,
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["CLEARED", "CLEARED"]
        assert rows[0]["reason"] == "B2B"
        assert rows[1]["reason"] == "CON"
        assert summary["cleared_count"] == 2
        assert summary["cleared_amount_cents"] == 1000

    def test_specific_reason_requires_exact_wire_reason_match(self):
        """A return with a specific reason code must not match a wire with a different reason."""
        compile_program()
        write_methods([
            "CON,consumer,true,2",
            "B2B,business,true,1",
        ])
        write_inputs(
            ["WWIR505000001B2B0000000800ACCT5050S20260501"],
            ["RWIR5050000010000000800ACCT505020260502CON"],
            DEFAULT_CALENDAR,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "EXCEPTION"
        assert rows[0]["reason"] == ""
        assert summary["exception_amount_cents"] == 800

    def test_any_skips_disabled_reason_wire(self):
        """ANY must not match a wire whose reason is disabled in policy."""
        compile_program()
        write_methods([
            "CON,consumer,false,1",
            "B2B,business,true,2",
        ])
        write_inputs(
            [
                "WWIR506000001CON0000001100ACCT5060S20260430",
                "WWIR506000001B2B0000001100ACCT5060S20260430",
            ],
            ["RWIR5060000010000001100ACCT506020260501ANY"],
            DEFAULT_CALENDAR,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "CLEARED"
        assert rows[0]["reason"] == "B2B"
        assert summary["cleared_count"] == 1
        assert summary["cleared_amount_cents"] == 1100

    def test_any_emits_wire_reason_not_the_word_any(self):
        """The report must emit the matched wire's reason code, never the literal ANY."""
        compile_program()
        write_methods([
            "ADM,admin,true,1",
        ])
        write_inputs(
            ["WWIR507000001ADM0000002200ACCT5070S20260501"],
            ["RWIR5070000010000002200ACCT507020260502ANY"],
            DEFAULT_CALENDAR,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "CLEARED"
        assert rows[0]["reason"] == "ADM"
        assert rows[0]["reason"] != "ANY"

    def test_malformed_priority_falls_back_to_lowest_rank(self):
        """A reason with a blank or missing priority should rank last among ANY candidates."""
        compile_program()
        write_methods([
            "CON,consumer,true,",
            "B2B,business,true,1",
        ])
        write_inputs(
            [
                "WWIR508000001CON0000001500ACCT5080S20260430",
                "WWIR508000001B2B0000001500ACCT5080S20260430",
            ],
            ["RWIR5080000010000001500ACCT508020260501ANY"],
            DEFAULT_CALENDAR,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "CLEARED"
        assert rows[0]["reason"] == "B2B"
        assert summary["cleared_count"] == 1

    def test_undated_returns_obey_policy_enabled_flag(self):
        """M1-style undated records must respect the enabled flag in the policy."""
        compile_program()
        write_methods([
            "CON,consumer,false,1",
            "B2B,business,true,2",
        ])
        write_inputs(
            [
                "WWIR509000001CON0000004400ACCT5090S",
                "WWIR509000001B2B0000004400ACCT5090S",
            ],
            ["RWIR5090000010000004400ACCT5090"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "CLEARED"
        assert rows[0]["reason"] == "B2B"
        assert summary["cleared_count"] == 1
        assert summary["cleared_amount_cents"] == 4400

    def test_any_with_closed_cycle_date_stays_exception(self):
        """ANY must still respect the cycle-window gate; a closed settlement date blocks it."""
        compile_program()
        write_methods([
            "CON,consumer,true,1",
        ])
        write_inputs(
            ["WWIR510000001CON0000000700ACCT5100S20260502"],
            ["RWIR5100000010000000700ACCT510020260503ANY"],
            ["20260501 OPEN", "20260502 CLOSED", "20260503 OPEN"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "EXCEPTION"
        assert rows[0]["reason"] == ""
        assert summary["cleared_count"] == 0
        assert summary["exception_amount_cents"] == 700

    def test_blank_return_reason_matches_without_priority_ordering(self):
        """A blank reason field should clear without ANY-style priority ranking."""
        compile_program()
        write_methods([
            "CON,consumer,true,3",
            "B2B,business,true,1",
        ])
        write_inputs(
            [
                "WWIR511000001CON0000000800ACCT5110S20260430",
                "WWIR511000001B2B0000000800ACCT5110S20260430",
            ],
            ["RWIR5110000010000000800ACCT511020260501   "],
            DEFAULT_CALENDAR,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "CLEARED"
        assert rows[0]["reason"] == "CON"
        assert summary["cleared_count"] == 1
        assert summary["cleared_amount_cents"] == 800

    def test_blank_return_reason_still_rejects_disabled_wire_reason(self):
        """Blank return reason must not clear against a wire whose reason is disabled."""
        compile_program()
        write_methods([
            "CON,consumer,false,1",
            "B2B,business,true,2",
        ])
        write_inputs(
            ["WWIR512000001CON0000000900ACCT5120S20260501"],
            ["RWIR5120000010000000900ACCT5120           "],
            DEFAULT_CALENDAR,
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "EXCEPTION"
        assert rows[0]["reason"] == ""
        assert summary["cleared_count"] == 0
        assert summary["exception_amount_cents"] == 900
