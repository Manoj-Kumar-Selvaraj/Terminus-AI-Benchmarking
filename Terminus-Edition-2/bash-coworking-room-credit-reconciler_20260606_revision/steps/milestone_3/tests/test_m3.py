"""Verifier tests for the coworking room credit reconciliation batch."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
BOOKINGS = APP / "data" / "bookings.csv"
CREDITS = APP / "data" / "credits.csv"
ALIASES = APP / "config" / "plan_aliases.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
PROFILE = APP / "config" / "run_profile.ini"
REPORT = APP / "out" / "credit_report.csv"
SUMMARY = APP / "out" / "credit_summary.json"
REPORT_FIELDS = ["booking_id", "member_id", "plan", "amount_cents", "status"]
SUMMARY_FIELDS = ["matched_count", "matched_amount_cents", "unmatched_count", "unmatched_amount_cents"]


def write_base_inputs(booking_rows, credit_rows, booking_header=None, credit_header=None):
    if booking_header is None:
        booking_header = "booking_id,member_id,amount_cents,status,plan"
    if credit_header is None:
        credit_header = "booking_id,member_id,amount_cents,plan"
    BOOKINGS.write_text(booking_header + "\n" + "\n".join(booking_rows) + "\n")
    CREDITS.write_text(credit_header + "\n" + "\n".join(credit_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def write_aliases(rows=None, header="alias,canonical,enabled"):
    if rows is None:
        rows = ["CC,PRIVATE,true", "INS,TEAM,true", "CA,HOTDESK,true", "FLEX,HOTDESK,false"]
    ALIASES.write_text(header + "\n" + "\n".join(rows) + "\n")


def run_program():
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        reader = csv.DictReader(handle)
        assert reader.fieldnames == REPORT_FIELDS
        rows = list(reader)
    summary = json.loads(SUMMARY.read_text())
    assert list(summary) == SUMMARY_FIELDS
    assert all(type(summary[key]) is int for key in SUMMARY_FIELDS)
    return rows, summary


def write_dated_inputs(booking_rows, credit_rows, calendar_rows=None, profile_text="max_open_days_back=2\n", booking_header=None, credit_header=None):
    if booking_header is None:
        booking_header = "booking_id,member_id,amount_cents,status,plan,booking_date"
    if credit_header is None:
        credit_header = "booking_id,member_id,amount_cents,plan,credit_date"
    BOOKINGS.write_text(booking_header + "\n" + "\n".join(booking_rows) + "\n")
    CREDITS.write_text(credit_header + "\n" + "\n".join(credit_rows) + "\n")
    if calendar_rows is None:
        calendar_rows = ["2026-04-01 open"]
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    PROFILE.write_text(profile_text)
    write_aliases()
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def test_latest_booking_date_consumption_affects_later_credit():
    write_dated_inputs(
        [
            "BOOK900000001,MEMBER01,5000,FINAL,HOTDESK,2026-04-10",
            "BOOK900000001,MEMBER01,5000,FINAL,HOTDESK,2026-04-11",
        ],
        [
            "BOOK900000001,MEMBER01,5000,HOTDESK,2026-04-09",
            "BOOK900000001,MEMBER01,5000,HOTDESK,2026-04-11",
        ],
        ["2026-04-09 open", "2026-04-10 open", "2026-04-11 open"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert summary == {"matched_count": 1, "matched_amount_cents": 5000, "unmatched_count": 1, "unmatched_amount_cents": 5000}


def test_credit_date_after_booking_date_is_not_eligible():
    write_dated_inputs(
        ["BOOK900000002,MEMBER02,6000,FINAL,PRIVATE,2026-04-05"],
        ["BOOK900000002,MEMBER02,6000,PRIVATE,2026-04-07"],
        ["2026-04-05 open", "2026-04-07 open"],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert summary["matched_count"] == 0
    assert summary["unmatched_amount_cents"] == 6000


def test_same_booking_date_tie_uses_booking_input_order_and_consumption():
    write_dated_inputs(
        [
            "BOOK910000001,MEMBER01,4100,FINAL,TEAM,2026-04-30",
            "BOOK910000001,MEMBER01,4100,FINAL,TEAM,2026-04-30",
        ],
        [
            "BOOK910000001,MEMBER01,4100,TEAM,2026-04-20",
            "BOOK910000001,MEMBER01,4100,TEAM,2026-04-20",
            "BOOK910000001,MEMBER01,4100,TEAM,2026-04-20",
        ],
        ["2026-04-20 open", "2026-04-30 open"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
    assert summary["matched_count"] == 2
    assert summary["unmatched_count"] == 1


def test_closed_or_unlisted_dates_are_not_eligible():
    write_dated_inputs(
        [
            "BOOK920000001,MEMBER01,5100,FINAL,HOTDESK,2026-04-30",
            "BOOK920000002,MEMBER02,5200,FINAL,PRIVATE,2026-04-30",
        ],
        [
            "BOOK920000001,MEMBER01,5100,HOTDESK,2026-04-10",
            "BOOK920000002,MEMBER02,5200,PRIVATE,2026-04-11",
        ],
        ["2026-04-10 closed", "2026-04-30 open"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
    assert summary["unmatched_amount_cents"] == 10300


def test_booking_date_closed_causes_unmatched():
    """Both credit and booking dates must be open; a closed booking_date must reject the match."""
    write_dated_inputs(
        ["BOOK999001,MEMBER01,5000,FINAL,HOTDESK,2026-04-15"],
        ["BOOK999001,MEMBER01,5000,HOTDESK,2026-04-10"],
        ["2026-04-10 open", "2026-04-15 closed"],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["plan"] == ""
    assert summary == {
        "matched_count": 0,
        "matched_amount_cents": 0,
        "unmatched_count": 1,
        "unmatched_amount_cents": 5000,
    }


def test_missing_or_malformed_dates_are_not_eligible():
    write_dated_inputs(
        [
            "BOOK940000001,MEMBER01,5300,FINAL,PRIVATE,",
            "BOOK940000002,MEMBER02,5400,FINAL,HOTDESK,20260430",
        ],
        [
            "BOOK940000001,MEMBER01,5300,PRIVATE,2026-04-10",
            "BOOK940000002,MEMBER02,5400,HOTDESK,2026/04/10",
        ],
        ["2026-04-10 open", "2026-04-30 open"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
    assert summary["matched_count"] == 0


def test_same_day_and_exact_configured_open_day_window_are_eligible():
    write_dated_inputs(
        ["BOOK970000001,MEMBER01,5700,FINAL,HOTDESK,2026-04-04", "BOOK970000002,MEMBER02,5800,FINAL,PRIVATE,2026-04-05"],
        ["BOOK970000001,MEMBER01,5700,HOTDESK,2026-04-01", "BOOK970000002,MEMBER02,5800,PRIVATE,2026-04-05"],
        ["2026-04-01 open", "2026-04-02 open", "2026-04-03 closed", "2026-04-04 open", "2026-04-05 open"],
        profile_text="max_open_days_back=2\n",
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert summary["matched_amount_cents"] == 11500


def test_above_configured_open_day_window_is_not_eligible():
    write_dated_inputs(
        ["BOOK970000003,MEMBER01,5900,FINAL,HOTDESK,2026-04-04"],
        ["BOOK970000003,MEMBER01,5900,HOTDESK,2026-04-01"],
        ["2026-04-01 open", "2026-04-02 open", "2026-04-03 open", "2026-04-04 open"],
        profile_text="max_open_days_back=2\n",
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert summary["unmatched_amount_cents"] == 5900


def test_runtime_profile_first_valid_assignment_tightens_open_day_limit():
    """The first positive max_open_days_back assignment wins over later values."""
    write_dated_inputs(
        [
            "BOOK980000001,MEMBER01,6100,FINAL,HOTDESK,2026-04-04",
            "BOOK980000002,MEMBER02,6200,FINAL,PRIVATE,2026-04-04",
        ],
        [
            "BOOK980000001,MEMBER01,6100,HOTDESK,2026-04-02",
            "BOOK980000002,MEMBER02,6200,PRIVATE,2026-04-01",
        ],
        ["2026-04-01 open", "2026-04-02 open", "2026-04-03 open", "2026-04-04 open"],
        profile_text="# tightened first\n[batch]\nmax_open_days_back=1\nmax_open_days_back=5\n",
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
    assert summary["matched_count"] == 0
    assert summary["unmatched_amount_cents"] == 12300


def test_runtime_profile_first_valid_assignment_expands_open_day_limit():
    """A later max_open_days_back assignment is ignored once an earlier valid value is found."""
    write_dated_inputs(
        ["BOOK980000003,MEMBER01,6150,FINAL,HOTDESK,2026-04-04"],
        ["BOOK980000003,MEMBER01,6150,HOTDESK,2026-04-01"],
        ["2026-04-01 open", "2026-04-02 open", "2026-04-03 closed", "2026-04-04 open"],
        profile_text="max_open_days_back=5\nmax_open_days_back=1\n",
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert summary["matched_amount_cents"] == 6150


def test_invalid_profile_defaults_to_two_open_days():
    write_dated_inputs(
        ["BOOK981000001,MEMBER01,6300,FINAL,HOTDESK,2026-04-04"],
        ["BOOK981000001,MEMBER01,6300,HOTDESK,2026-04-01"],
        ["2026-04-01 open", "2026-04-02 open", "2026-04-03 closed", "2026-04-04 open"],
        profile_text="# bad config\nmax_open_days_back=zero\n",
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert summary["matched_amount_cents"] == 6300


def test_calendar_comments_blanks_and_status_case_are_handled():
    write_dated_inputs(
        ["BOOK982000001,MEMBER01,6400,FINAL,HOTDESK,2026-04-04"],
        ["BOOK982000001,MEMBER01,6400,HOTDESK,2026-04-02"],
        ["# maintenance note", "", "2026-04-02 OPEN", "2026-04-03 Closed", "2026-04-04 open"],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert summary["matched_amount_cents"] == 6400


def test_dated_batches_still_use_header_reordering_aliases_and_amount_normalization():
    write_dated_inputs(
        [
            "alpha,2026-04-04,DAY,FINAL,0000006500,MEMBER01,BOOK990000001",
            "beta,2026-04-04,SUITE,FINAL,6600,MEMBER02,BOOK990000002",
        ],
        [
            "2026-04-02,6500,BOOK990000001,MEMBER01,HOTDESK,x",
            "2026-04-02,0000006600,BOOK990000002,MEMBER02,SUITE,y",
        ],
        ["2026-04-02 open", "2026-04-03 open", "2026-04-04 open"],
        booking_header="note,booking_date,plan,status,amount_cents,member_id,booking_id",
        credit_header="credit_date,amount_cents,booking_id,member_id,plan,note",
    )
    write_aliases(["DAY,HOTDESK,true", "SUITE,PRIVATE,true"])
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["plan"] for row in rows] == ["HOTDESK", "PRIVATE"]
    assert [row["amount_cents"] for row in rows] == ["6500", "6600"]
    assert summary["matched_amount_cents"] == 13100


def test_invalid_credit_amount_with_dates_is_unmatched_without_crashing():
    write_dated_inputs(
        ["BOOK991000001,MEMBER01,7000,FINAL,HOTDESK,2026-04-04"],
        ["BOOK991000001,MEMBER01,07x0,HOTDESK,2026-04-02"],
        ["2026-04-02 open", "2026-04-04 open"],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["amount_cents"] == "07x0"
    assert summary["unmatched_amount_cents"] == 0


def test_undated_batches_skip_calendar_and_profile_rules():
    write_aliases()
    write_base_inputs(
        ["BOOK998000001,MEMBER01,8000,FINAL,HOTDESK"],
        ["BOOK998000001,MEMBER01,8000,HOTDESK"],
    )
    CALENDAR.write_text("2026-04-01 closed\n")
    PROFILE.write_text("max_open_days_back=0\n")
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert summary["matched_amount_cents"] == 8000


def test_partial_date_headers_use_undated_matching():
    write_aliases()
    write_base_inputs(
        ["BOOK998000002,MEMBER01,8100,FINAL,HOTDESK,2026-04-10"],
        ["BOOK998000002,MEMBER01,8100,HOTDESK"],
        booking_header="booking_id,member_id,amount_cents,status,plan,booking_date",
        credit_header="booking_id,member_id,amount_cents,plan",
    )
    CALENDAR.write_text("2026-04-01 closed\n")
    PROFILE.write_text("max_open_days_back=0\n")
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert summary["matched_amount_cents"] == 8100


def test_credit_date_header_without_booking_date_header_uses_undated_matching():
    write_aliases()
    write_base_inputs(
        ["BOOK998000003,MEMBER01,8200,FINAL,HOTDESK"],
        ["BOOK998000003,MEMBER01,8200,HOTDESK,2026-04-10"],
        booking_header="booking_id,member_id,amount_cents,status,plan",
        credit_header="booking_id,member_id,amount_cents,plan,credit_date",
    )
    CALENDAR.write_text("2026-04-01 closed\n")
    PROFILE.write_text("max_open_days_back=0\n")
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert summary["matched_amount_cents"] == 8200


def test_malformed_calendar_lines_without_status_are_ignored():
    write_dated_inputs(
        ["BOOK983000001,MEMBER01,6450,FINAL,HOTDESK,2026-04-04"],
        ["BOOK983000001,MEMBER01,6450,HOTDESK,2026-04-02"],
        ["2026-04-02 open", "20260404", "2026-04-04 open"],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert summary["matched_amount_cents"] == 6450


def test_profile_defaults_when_no_valid_assignment_exists():
    write_dated_inputs(
        ["BOOK981000002,MEMBER01,6400,FINAL,HOTDESK,2026-04-04"],
        ["BOOK981000002,MEMBER01,6400,HOTDESK,2026-04-01"],
        ["2026-04-01 open", "2026-04-02 open", "2026-04-03 closed", "2026-04-04 open"],
        profile_text="# no numeric assignment\n[batch]\n",
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert summary["matched_amount_cents"] == 6400
