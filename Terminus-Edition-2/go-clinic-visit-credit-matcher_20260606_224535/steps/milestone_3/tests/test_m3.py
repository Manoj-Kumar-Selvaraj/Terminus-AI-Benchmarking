"""Milestone 3 verifier tests for dated clinic visit credit matching CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
VISITS = APP / "data" / "visits.csv"
CREDITS = APP / "data" / "credits.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go credit reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all milestone 3 tests."""
    build_program()


def write_inputs(visit_rows, credit_rows, calendar_rows, dated=True):
    """Replace CSV inputs and calendar with a dated or legacy undated scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    if dated:
        VISITS.write_text(
            "visit_id,customer_id,amount_cents,status,channel,due_date\n" + "\n".join(visit_rows) + "\n"
        )
        CREDITS.write_text(
            "visit_id,customer_id,amount_cents,channel,credit_date\n" + "\n".join(credit_rows) + "\n"
        )
    else:
        VISITS.write_text(
            "visit_id,customer_id,amount_cents,status,channel\n" + "\n".join(visit_rows) + "\n"
        )
        CREDITS.write_text("visit_id,customer_id,amount_cents,channel\n" + "\n".join(credit_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse its CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_card_credit_matches_and_counts_positive_amount():
    """CARD credits should match posted visits and add positive cents to matched totals."""
    write_inputs(
        [
            "VISIT20260401001,CUST1001,12500,POSTED,ACH",
            "VISIT20260401002,CUST1002,9900,POSTED,CARD",
        ],
        [
            "VISIT20260401001,CUST1001,12500,ACH",
            "VISIT20260401002,CUST1002,9900,CARD",
        ],
        ["2099-12-31 closed"],
        dated=False,
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["channel"] == "CARD"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400


def test_visit_id_match_uses_full_identifier():
    """A credit must not match a visit that only shares the leading visit prefix."""
    write_inputs(
        [
            "VISIT777770001,CUST2001,3300,POSTED,ACH",
            "VISIT777770002,CUST2001,3300,POSTED,ACH",
        ],
        [
            "VISIT777770003,CUST2001,3300,ACH",
            "VISIT777770002,CUST2001,3300,ACH",
        ],
        ["2099-12-31 closed"],
        dated=False,
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert summary["matched_count"] == 1


def test_allowed_channels_must_match_exactly():
    """Two different allowed channels on the same visit should not match."""
    write_inputs(
        ["VISIT8001,CUST8001,1500,POSTED,CARD"],
        ["VISIT8001,CUST8001,1500,ACH"],
        ["2099-12-31 closed"],
        dated=False,
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["channel"] == ""
    assert summary["matched_count"] == 0


def test_duplicate_credits_do_not_reuse_consumed_visit():
    """Only the earliest eligible credit may consume a matching visit row."""
    write_inputs(
        ["VISIT5551,CUST5551,7500,POSTED,CARD"],
        [
            "VISIT5551,CUST5551,7500,CARD",
            "VISIT5551,CUST5551,7500,CARD",
        ],
        ["2099-12-31 closed"],
        dated=False,
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert summary["matched_count"] == 1


def test_legacy_channel_aliases_match_and_emit_canonical_values():
    """CC and WIR aliases should normalize and emit canonical channels."""
    write_inputs(
        [
            "VISIT7001,CUST7001,3100,POSTED,CARD",
            "VISIT7002,CUST7002,3200,POSTED,WIRE",
        ],
        [
            "VISIT7001,CUST7001,3100,CC",
            "VISIT7002,CUST7002,3200,WIR",
        ],
        ["2099-12-31 closed"],
        dated=False,
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["channel"] for row in rows] == ["CARD", "WIRE"]
    assert summary["matched_amount_cents"] == 6300


def test_report_schema_and_credit_input_order_are_stable():
    """The report should use the required schema and preserve credit input order."""
    write_inputs(
        [
            "VISIT9001,CUST9001,100,POSTED,ACH",
            "VISIT9002,CUST9002,200,POSTED,CARD",
            "VISIT9003,CUST9003,300,POSTED,WIRE",
        ],
        [
            "VISIT9003,CUST9003,300,WIRE",
            "VISIT9001,CUST9001,100,ACH",
            "VISIT9002,CUST9002,200,CARD",
        ],
        ["2099-12-31 closed"],
        dated=False,
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "visit_id,customer_id,channel,amount_cents,status"
    assert [row["visit_id"] for row in rows] == ["VISIT9003", "VISIT9001", "VISIT9002"]
    assert summary["matched_count"] == 3


class TestMilestone3:
    """Date gates and latest eligible visit selection for credits."""

    def test_open_credit_date_and_latest_due_date_win(self):
        """Open credit dates should gate matching and latest eligible due date should win."""
        write_inputs(
            [
                "VISIT9301,CUST9301,1000,POSTED,ACH,2026-04-03",
                "VISIT9301,CUST9301,1000,POSTED,CARD,2026-04-04",
                "VISIT9302,CUST9302,2000,POSTED,CARD,2026-04-02",
                "VISIT9303,CUST9303,3000,POSTED,WIRE,2026-04-05",
                "VISIT9304,CUST9304,4000,POSTED,WIRE,2026-04-05",
            ],
            [
                "VISIT9301,CUST9301,1000,CC,2026-04-02",
                "VISIT9302,CUST9302,2000,CC,2026-04-04",
                "VISIT9303,CUST9303,3000,WIR,2026-04-06",
                "VISIT9304,CUST9304,4000,WIRE,2026-04-07",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
                "2026-04-05 open",
                "2026-04-06 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert rows[0]["channel"] == "CARD"
        assert summary["matched_count"] == 1

    def test_same_due_date_tie_uses_visit_order_and_consumption(self):
        """Same-date candidates should use earliest visit row order and still enforce consumption."""
        write_inputs(
            [
                "VISIT9401,CUST9401,500,POSTED,CARD,2026-04-05",
                "VISIT9401,CUST9401,500,POSTED,CARD,2026-04-05",
                "VISIT9402,CUST9402,700,POSTED,ACH,2026-04-05",
            ],
            [
                "VISIT9401,CUST9401,500,CC,2026-04-04",
                "VISIT9401,CUST9401,500,CC,2026-04-04",
                "VISIT9401,CUST9401,500,CC,2026-04-04",
                "VISIT9402,CUST9402,700,ACH,2026-04-05",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["channel"] for row in rows] == ["CARD", "CARD", "", "ACH"]
        assert summary["matched_count"] == 3

    def test_latest_due_date_wins_before_older_visit_is_used(self):
        """Latest due_date must win even when an older visit row appears first in the file."""
        write_inputs(
            [
                "VISIT9501,CUST9501,800,POSTED,CARD,2026-04-03",
                "VISIT9501,CUST9501,800,POSTED,CARD,2026-04-06",
            ],
            [
                "VISIT9501,CUST9501,800,CC,2026-04-04",
                "VISIT9501,CUST9501,800,CC,2026-04-04",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 open",
                "2026-04-06 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert rows[0]["channel"] == "CARD"
        assert rows[1]["channel"] == ""
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 1,
            "unmatched_amount_cents": 800,
        }

    def test_undated_inputs_skip_date_gating(self):
        """Without due_date or credit_date columns, milestone 1-2 matching still applies."""
        write_inputs(
            [
                "VISIT9151,CUST9151,900,POSTED,ACH",
                "VISIT9152,CUST9152,1100,POSTED,CARD",
            ],
            [
                "VISIT9151,CUST9151,900,ACH",
                "VISIT9152,CUST9152,1100,CC",
            ],
            ["2099-12-31 closed"],
            dated=False,
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["channel"] for row in rows] == ["ACH", "CARD"]
        assert summary["matched_amount_cents"] == 2000

    def test_credit_date_equal_to_due_date_is_eligible(self):
        """A credit date equal to the visit due date should still match."""
        write_inputs(
            ["VISIT9061,CUST9061,1250,POSTED,WIRE,2026-04-05"],
            ["VISIT9061,CUST9061,1250,WIR,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["channel"] == "WIRE"
        assert summary["matched_count"] == 1

    def test_closed_credit_date_is_not_eligible(self):
        """A credit whose date is listed as closed must not match."""
        write_inputs(
            ["VISIT9601,CUST9601,1000,POSTED,CARD,2026-04-10"],
            ["VISIT9601,CUST9601,1000,CC,2026-04-05"],
            ["2026-04-05 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["channel"] == ""

    def test_unlisted_credit_date_is_not_eligible(self):
        """A credit date absent from the calendar must not be treated as open."""
        write_inputs(
            ["VISIT9651,CUST9651,500,POSTED,CARD,2026-04-30"],
            ["VISIT9651,CUST9651,500,CC,2026-04-15"],
            ["2026-04-10 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_missing_credit_date_is_not_eligible(self):
        """A credit with an empty credit_date must not match any visit."""
        write_inputs(
            ["VISIT9701,CUST9701,900,POSTED,ACH,2026-04-05"],
            ["VISIT9701,CUST9701,900,ACH,"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_visit_without_due_date_is_not_eligible(self):
        """A visit with an empty due_date cannot be consumed in dated mode."""
        write_inputs(
            ["VISIT9801,CUST9801,700,POSTED,WIRE,"],
            ["VISIT9801,CUST9801,700,WIR,2026-04-04"],
            ["2026-04-04 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_wir_alias_matches_wire_visit_and_emits_canonical_channel(self):
        """A WIR credit should match a WIRE visit and report the canonical channel."""
        write_inputs(
            ["VISIT9901,CUST9901,600,POSTED,WIRE,2026-04-10"],
            ["VISIT9901,CUST9901,600,WIR,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["channel"] == "WIRE"
        assert summary["matched_count"] == 1
