"""Milestone 3 verifier tests for dated warranty claim matching."""

import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SHIPMENTS = APP / "data" / "devices.csv"
CLAIMS = APP / "data" / "warranty_claims.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "warranty_report.csv"
SUMMARY = APP / "out" / "warranty_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go claim reconciliation CLI."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


def write_inputs(device_rows, claim_rows, calendar_rows):
    """Replace CSV inputs and calendar with a dated claim scenario."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SHIPMENTS.write_text("device_id,owner_id,amount_cents,status,reason,purchase_date\n" + "\n".join(device_rows) + "\n")
    CLAIMS.write_text("device_id,owner_id,amount_cents,reason,claim_date\n" + "\n".join(claim_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_raw_inputs(device_header, device_rows, claim_header, claim_rows, calendar_rows):
    """Replace inputs with explicit headers for missing-column compatibility scenarios."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    SHIPMENTS.write_text(device_header + "\n" + "\n".join(device_rows) + "\n")
    CLAIMS.write_text(claim_header + "\n" + "\n".join(claim_rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the compiled program and parse its CSV/JSON outputs."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone3:
    """Date gates and latest eligible device selection for claims."""

    def test_open_claim_date_and_latest_purchase_date_win(self):
        """Open claim dates should gate matching and latest eligible purchase date should win."""
        build_program()
        write_inputs(
            [
                "SHIP9301,ACCT9301,1000,POSTED,SCREEN,2026-04-01",
                "SHIP9301,ACCT9301,1000,POSTED,BATTERY,2026-04-03",
                "SHIP9302,ACCT9302,2000,POSTED,WATER,2026-04-05",
                "SHIP9303,ACCT9303,3000,POSTED,SCREEN,2026-04-04",
                "SHIP9304,ACCT9304,4000,POSTED,WATER,2026-04-05",
            ],
            [
                "SHIP9301,ACCT9301,1000,BAT,2026-04-04",
                "SHIP9302,ACCT9302,2000,WTR,2026-04-04",
                "SHIP9303,ACCT9303,3000,SCREEN,2026-04-05",
                "SHIP9304,ACCT9304,4000,WTR,2026-04-07",
            ],
            [
                "2026-04-04 open",
                "2026-04-05 closed",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert rows[0]["reason"] == "BATTERY"
        assert [row["reason"] for row in rows[1:]] == ["", "", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 3,
            "unmatched_amount_cents": 9000,
        }

    def test_same_purchase_date_tie_uses_device_order_and_consumption(self):
        """Same-date candidates should use device order and still enforce consumption."""
        build_program()
        write_inputs(
            [
                "SHIP9401,ACCT9401,500,POSTED,BATTERY,2026-04-05",
                "SHIP9401,ACCT9401,500,POSTED,BATTERY,2026-04-05",
                "SHIP9402,ACCT9402,700,POSTED,SCREEN,2026-04-05",
            ],
            [
                "SHIP9401,ACCT9401,500,BAT,2026-04-06",
                "SHIP9401,ACCT9401,500,BAT,2026-04-06",
                "SHIP9401,ACCT9401,500,BAT,2026-04-06",
                "SHIP9402,ACCT9402,700,SCREEN,2026-04-06",
            ],
            [
                "2026-04-06 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["reason"] for row in rows] == ["BATTERY", "BATTERY", "", "SCREEN"]
        assert summary["matched_count"] == 3
        assert summary["matched_amount_cents"] == 1700
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 500

    def test_latest_purchase_date_wins_before_older_device_is_used(self):
        """A later eligible purchase date should be consumed before an older eligible device."""
        build_program()
        write_inputs(
            [
                "SHIP9501,ACCT9501,800,POSTED,SCREEN,2026-04-01",
                "SHIP9501,ACCT9501,800,POSTED,SCREEN,2026-04-03",
            ],
            [
                "SHIP9501,ACCT9501,800,SCREEN,2026-04-04",
                "SHIP9501,ACCT9501,800,SCREEN,2026-04-02",
            ],
            [
                "2026-04-02 open",
                "2026-04-04 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
        assert [row["reason"] for row in rows] == ["SCREEN", "SCREEN"]
        assert summary == {
            "matched_count": 2,
            "matched_amount_cents": 1600,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }

    def test_purchase_date_equal_to_claim_date_is_eligible(self):
        """A device whose purchase date equals the claim date should still match."""
        build_program()
        write_inputs(
            ["SHIP9601,ACCT9601,300,POSTED,SCREEN,2026-04-06"],
            ["SHIP9601,ACCT9601,300,SCREEN,2026-04-06"],
            ["2026-04-06 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["reason"] == "SCREEN"
        assert summary["matched_count"] == 1
        assert summary["matched_amount_cents"] == 300

    def test_claim_date_before_purchase_date_stays_unmatched(self):
        """A claim date earlier than the device purchase date must stay unmatched."""
        build_program()
        write_inputs(
            ["SHIP9801,ACCT9801,900,POSTED,SCREEN,2026-04-08"],
            ["SHIP9801,ACCT9801,900,SCREEN,2026-04-07"],
            ["2026-04-07 open", "2026-04-08 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["reason"] == ""
        assert summary["unmatched_amount_cents"] == 900

    def test_closed_claim_date_stays_unmatched(self):
        """Closed calendar dates must reject otherwise valid dated matches."""
        build_program()
        write_inputs(
            ["SHIP9901,ACCT9901,1100,POSTED,BATTERY,2026-04-05"],
            ["SHIP9901,ACCT9901,1100,BAT,2026-04-06"],
            ["2026-04-06 closed"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["reason"] == ""
        assert summary["unmatched_count"] == 1

    def test_malformed_purchase_date_stays_unmatched(self):
        """Malformed purchase dates must not match even when claim dates are open."""
        build_program()
        write_inputs(
            ["SHIP9951,ACCT9951,1300,POSTED,WATER,bad-date"],
            ["SHIP9951,ACCT9951,1300,WTR,2026-04-06"],
            ["2026-04-06 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["reason"] == ""
        assert summary["unmatched_amount_cents"] == 1300

    def test_missing_and_absent_claim_dates_are_unmatched_but_readable(self):
        """Missing date values or older no-date CSV shapes should not crash and should not match."""
        build_program()
        write_raw_inputs(
            "device_id,owner_id,amount_cents,status,reason,purchase_date",
            [
                "SHIP9701,ACCT9701,400,POSTED,SCREEN,2026-04-06",
                "SHIP9702,ACCT9702,500,POSTED,BATTERY,2026-04-06",
            ],
            "device_id,owner_id,amount_cents,reason,claim_date",
            [
                "SHIP9701,ACCT9701,400,SCREEN,",
                "SHIP9702,ACCT9702,500,BAT,2026-04-07",
            ],
            [
                "2026-04-06 open",
            ],
        )
        rows, summary = run_program()

        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert [row["reason"] for row in rows] == ["", ""]
        assert summary["unmatched_count"] == 2
        assert summary["unmatched_amount_cents"] == 900

        write_raw_inputs(
            "device_id,owner_id,amount_cents,status,reason",
            ["SHIP9703,ACCT9703,600,POSTED,SCREEN"],
            "device_id,owner_id,amount_cents,reason",
            ["SHIP9703,ACCT9703,600,SCREEN"],
            ["2026-04-06 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["reason"] == ""
        assert summary["unmatched_count"] == 1
        assert summary["unmatched_amount_cents"] == 600

    def test_bat_alias_selects_latest_purchase_date_not_first_row(self):
        """Reason alias BAT must match only after choosing the latest eligible purchase_date."""
        build_program()
        write_inputs(
            [
                "SHIP-TIE1,ACCT-TIE1,500,POSTED,BATTERY,2026-04-01",
                "SHIP-TIE1,ACCT-TIE1,800,POSTED,BATTERY,2026-04-10",
            ],
            ["SHIP-TIE1,ACCT-TIE1,800,BAT,2026-04-11"],
            ["2026-04-11 open", "2026-04-10 open", "2026-04-01 open"],
        )
        rows, summary = run_program()

        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["reason"] == "BATTERY"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 800,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
