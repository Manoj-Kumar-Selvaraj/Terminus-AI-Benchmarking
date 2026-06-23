"""Verifier tests for dated Ruby theater refund reconciliation."""

import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCE = APP / "data" / "bookings.csv"
ACTIONS = APP / "data" / "refunds.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
REPORT = APP / "out" / "refund_report.csv"
SUMMARY = APP / "out" / "refund_summary.json"


def write_inputs(source_rows, action_rows, calendar_rows=None, dated=False):
    """Replace CSV inputs and optional calendar with a focused scenario."""
    source_header = "booking_id,patron_id,amount_cents,status,seat_zone" + (",show_date" if dated else "")
    action_header = "booking_id,patron_id,amount_cents,seat_zone" + (",refund_date" if dated else "")
    SOURCE.write_text(source_header + "\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text(action_header + "\n" + "\n".join(action_rows) + "\n")
    if calendar_rows is not None:
        CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the Ruby batch and return parsed report and summary outputs."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())


class TestMilestone3:
    """Calendar lead-time gates, latest show-date selection, aliases, and row consumption."""

    def test_undated_inputs_keep_alias_and_consumption_behavior(self):
        """Without date columns, milestone 1-2 matching should still work."""
        write_inputs(
            [
                "UND1001,CUST1001,900,TICKETED,ORCH",
                "UND1001,CUST1001,900,TICKETED,ORCH",
                "UND1002,CUST1002,1100,TICKETED,BALC",
            ],
            [
                "UND1001,CUST1001,900,ORC",
                "UND1001,CUST1001,900,ORC",
                "UND1001,CUST1001,900,ORC",
                "UND1002,CUST1002,1100,BAL",
            ],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED", "MATCHED"]
        assert [row["seat_zone"] for row in rows] == ["ORCH", "ORCH", "", "BALC"]
        assert summary == {
            "matched_count": 3,
            "matched_amount_cents": 2900,
            "unmatched_count": 1,
            "unmatched_amount_cents": 900,
        }

    def test_latest_show_date_wins_and_consumed_rows_are_skipped(self):
        """Latest eligible show_date should win even when first-row selection changes later outcomes."""
        write_inputs(
            [
                "DATE2001,CUST2001,1000,TICKETED,MEZZ,2026-04-05",
                "DATE2001,CUST2001,1000,TICKETED,MEZZ,2026-04-08",
            ],
            [
                "DATE2001,CUST2001,1000,MEZ,2026-04-03",
                "DATE2001,CUST2001,1000,MEZ,2026-04-06",
            ],
            [
                "2026-04-03 open",
                "2026-04-04 open",
                "2026-04-05 open",
                "2026-04-06 open",
                "2026-04-07 open",
                "2026-04-08 open",
            ],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["seat_zone"] for row in rows] == ["MEZZ", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1000,
        }

    def test_exactly_two_open_days_after_refund_is_eligible(self):
        """A refund with exactly two open dates before the show should match."""
        write_inputs(
            ["DATE3001,CUST3001,1250,TICKETED,BALC,2026-05-03"],
            ["DATE3001,CUST3001,1250,BAL,2026-05-01"],
            ["2026-05-01 open", "2026-05-02 open", "2026-05-03 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["seat_zone"] == "BALC"
        assert summary["matched_amount_cents"] == 1250

    def test_equal_or_one_open_day_lead_time_is_ineligible(self):
        """Same-day and one-open-day lead times should not match."""
        write_inputs(
            [
                "DATE4001,CUST4001,700,TICKETED,ORCH,2026-06-10",
                "DATE4002,CUST4002,800,TICKETED,ORCH,2026-06-11",
            ],
            [
                "DATE4001,CUST4001,700,ORCH,2026-06-10",
                "DATE4002,CUST4002,800,ORCH,2026-06-10",
            ],
            ["2026-06-10 open", "2026-06-11 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 1500

    def test_refund_date_must_be_open_even_when_show_date_is_open(self):
        """A closed refund_date should reject even when the show_date and lead time qualify."""
        write_inputs(
            ["X001,C001,500,TICKETED,ORCH,2026-10-05"],
            ["X001,C001,500,ORC,2026-10-02"],
            [
                "2026-10-02 closed",
                "2026-10-03 open",
                "2026-10-04 open",
                "2026-10-05 open",
            ],
            dated=True,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["seat_zone"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 500

    def test_closed_unlisted_and_missing_dates_are_ineligible(self):
        """Closed, unlisted, and blank refund/show dates should all reject matches."""
        write_inputs(
            [
                "DATE5001,CUST5001,100,TICKETED,MEZZ,2026-07-05",
                "DATE5002,CUST5002,200,TICKETED,MEZZ,2026-07-06",
                "DATE5003,CUST5003,300,TICKETED,MEZZ,",
                "DATE5004,CUST5004,400,TICKETED,MEZZ,2026-07-08",
            ],
            [
                "DATE5001,CUST5001,100,MEZ,2026-07-03",
                "DATE5002,CUST5002,200,MEZ,2026-07-03",
                "DATE5003,CUST5003,300,MEZ,2026-07-03",
                "DATE5004,CUST5004,400,MEZ,",
            ],
            [
                "2026-07-03 open",
                "2026-07-04 closed",
                "2026-07-05 open",
                "2026-07-06 closed",
                "2026-07-07 open",
                "2026-07-08 open",
            ],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert [row["seat_zone"] for row in rows] == ["", "", "", ""]
        assert summary["unmatched_amount_cents"] == 1000

    def test_same_show_date_tie_uses_booking_input_order_and_row_consumption(self):
        """Same-date duplicate bookings should be consumed by row position."""
        write_inputs(
            [
                "DATE6001,CUST6001,500,TICKETED,BALC,2026-08-05",
                "DATE6001,CUST6001,500,TICKETED,BALC,2026-08-05",
            ],
            [
                "DATE6001,CUST6001,500,BAL,2026-08-03",
                "DATE6001,CUST6001,500,BAL,2026-08-03",
                "DATE6001,CUST6001,500,BAL,2026-08-03",
            ],
            ["2026-08-03 open", "2026-08-04 open", "2026-08-05 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 2
        assert summary["unmatched_count"] == 1

    def test_prior_matching_gates_still_apply_under_dates(self):
        """Patron, amount, status, seat_zone equality, and full id gates should still block matches."""
        write_inputs(
            [
                "PREFIX770001,CUST7001,1000,TICKETED,ORCH,2026-09-05",
                "PREFIX770002,CUST7002,2000,DRAFT,MEZZ,2026-09-05",
                "DATE7003,CUST7003,3100,TICKETED,MEZZ,2026-09-05",
                "DATE7004,CUST7004,4000,TICKETED,BALC,2026-09-05",
                "DATE7005,CUST7005,5000,TICKETED,ORCH,2026-09-05",
            ],
            [
                "PREFIX770003,CUST7001,1000,ORC,2026-09-03",
                "PREFIX770002,CUST7002,2000,MEZ,2026-09-03",
                "DATE7003,CUST7003,3000,MEZ,2026-09-03",
                "DATE7004,CUST7004,4000,MEZ,2026-09-03",
                "DATE7005,CUST9999,5000,ORC,2026-09-03",
            ],
            ["2026-09-03 open", "2026-09-04 open", "2026-09-05 open"],
            dated=True,
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary == {
            "matched_count": 0,
            "matched_amount_cents": 0,
            "unmatched_count": 5,
            "unmatched_amount_cents": 15000,
        }
