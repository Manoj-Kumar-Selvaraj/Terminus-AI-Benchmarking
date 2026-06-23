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


def summary_amount_contribution(row):
    raw = row["amount_cents"].strip()
    if row["status"] == "MATCHED":
        return int(raw)
    try:
        value = int(raw)
        return value if value > 0 else 0
    except ValueError:
        return 0


def summary_from_report(rows):
    matched = [row for row in rows if row["status"] == "MATCHED"]
    unmatched = [row for row in rows if row["status"] == "UNMATCHED"]
    return {
        "matched_count": len(matched),
        "matched_amount_cents": sum(summary_amount_contribution(row) for row in matched),
        "unmatched_count": len(unmatched),
        "unmatched_amount_cents": sum(summary_amount_contribution(row) for row in unmatched),
    }


def test_matches_all_allowed_plans_and_sums_positive_amounts():
    write_base_inputs(
        [
            "BOOK100000001,MEMBER01,0000001200,FINAL,HOTDESK",
            "BOOK100000002,MEMBER02,2300,FINAL,PRIVATE",
            "BOOK100000003,MEMBER03,0000003400,FINAL,TEAM",
        ],
        [
            "BOOK100000001,MEMBER01,1200,HOTDESK",
            "BOOK100000002,MEMBER02,0000002300,PRIVATE",
            "BOOK100000003,MEMBER03,3400,TEAM",
        ],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["plan"] for row in rows] == ["HOTDESK", "PRIVATE", "TEAM"]
    assert [row["amount_cents"] for row in rows] == ["1200", "2300", "3400"]
    assert summary == {"matched_count": 3, "matched_amount_cents": 6900, "unmatched_count": 0, "unmatched_amount_cents": 0}


def test_full_identifier_matching_not_prefix_or_substring():
    write_base_inputs(
        [
            "BOOKING777770001,MEMBER01,3300,FINAL,HOTDESK",
            "BOOKING777770002,MEMBER01,3300,FINAL,HOTDESK",
        ],
        [
            "BOOKING777770003,MEMBER01,3300,HOTDESK",
            "BOOKING777770002,MEMBER01,3300,HOTDESK",
        ],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_member_id_match_uses_full_identifier_not_prefix_or_substring():
    write_base_inputs(
        [
            "BOOK277770001,MEMBER0100,4400,FINAL,PRIVATE",
            "BOOK277770002,MEMBER02,5500,FINAL,TEAM",
        ],
        [
            "BOOK277770001,MEMBER01,4400,PRIVATE",
            "BOOK277770002,MEMBER02,5500,TEAM",
        ],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["member_id"] == "MEMBER01"
    assert summary["matched_amount_cents"] == 5500
    assert summary["unmatched_amount_cents"] == 4400


def test_member_amount_status_and_plan_all_gate_matching():
    write_base_inputs(
        [
            "BOOK300000001,MEMBER01,1000,FINAL,HOTDESK",
            "BOOK300000002,MEMBER02,2000,FINAL,PRIVATE",
            "BOOK300000003,MEMBER03,3000,PENDING,TEAM",
            "BOOK300000004,MEMBER04,4000,FINAL,OTHER",
        ],
        [
            "BOOK300000001,WRONG01,1000,HOTDESK",
            "BOOK300000002,MEMBER02,2100,PRIVATE",
            "BOOK300000003,MEMBER03,3000,TEAM",
            "BOOK300000004,MEMBER04,4000,OTHER",
        ],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary["matched_count"] == 0
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_credits_do_not_reuse_consumed_booking_row():
    write_base_inputs(
        ["BOOK400000001,MEMBER01,5500,FINAL,PRIVATE"],
        ["BOOK400000001,MEMBER01,5500,PRIVATE", "BOOK400000001,MEMBER01,5500,PRIVATE"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert summary["matched_count"] == 1
    assert summary["unmatched_count"] == 1


def test_trims_fields_and_case_folds_status_and_plan():
    write_base_inputs(
        ["  BOOK500000001  ,  MEMBER01  , 0000006600 , final , private "],
        [" BOOK500000001 , MEMBER01 , 0000006600 , PRIVATE "],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["booking_id"] == "BOOK500000001"
    assert rows[0]["member_id"] == "MEMBER01"
    assert rows[0]["plan"] == "PRIVATE"
    assert rows[0]["amount_cents"] == "6600"
    assert summary["matched_amount_cents"] == 6600


def test_case_folded_identifiers_match_after_normalization():
    write_base_inputs(
        ["book500000002,member02,7700,final,team"],
        ["BOOK500000002,MEMBER02,7700,team"],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["booking_id"] == "BOOK500000002"
    assert rows[0]["member_id"] == "MEMBER02"
    assert rows[0]["plan"] == "TEAM"
    assert summary["matched_amount_cents"] == 7700


def test_report_schema_credit_input_order_and_blank_unmatched_plan_are_stable():
    write_base_inputs(
        ["BOOK600000002,MEMBER02,1200,FINAL,HOTDESK", "BOOK600000001,MEMBER01,1100,FINAL,PRIVATE"],
        ["BOOK600000001,MEMBER01,1100,PRIVATE", "BOOKNO_MATCH,MEMBER09,9900,HOTDESK", "BOOK600000002,MEMBER02,1200,HOTDESK"],
    )
    rows, summary = run_program()
    assert list(rows[0].keys()) == ["booking_id", "member_id", "plan", "amount_cents", "status"]
    assert [row["booking_id"] for row in rows] == ["BOOK600000001", "BOOKNO_MATCH", "BOOK600000002"]
    assert rows[1]["plan"] == ""
    assert summary == {"matched_count": 2, "matched_amount_cents": 2300, "unmatched_count": 1, "unmatched_amount_cents": 9900}


def test_header_reordering_and_extra_columns_are_supported():
    write_base_inputs(
        [
            "ignored-a,FINAL,PRIVATE,BOOK700000001,2500,MEMBER01,ignored-b",
            "ignored-c,FINAL,HOTDESK,BOOK700000002,2600,MEMBER02,ignored-d",
        ],
        [
            "memo-a,2500,BOOK700000001,PRIVATE,MEMBER01",
            "memo-b,2600,BOOK700000002,HOTDESK,MEMBER02",
        ],
        booking_header="note,status,plan,booking_id,amount_cents,member_id,source",
        credit_header="memo,amount_cents,booking_id,plan,member_id",
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["plan"] for row in rows] == ["PRIVATE", "HOTDESK"]
    assert summary["matched_amount_cents"] == 5100


def test_header_matching_trims_and_case_folds_column_names():
    write_base_inputs(
        [
            "BOOK705000001,MEMBER01,FINAL,HOTDESK,2700",
            "BOOK705000002,MEMBER02,FINAL,PRIVATE,2800",
        ],
        [
            "MEMBER01,BOOK705000001,HOTDESK,2700",
            "MEMBER02,BOOK705000002,PRIVATE,2800",
        ],
        booking_header=" Booking_ID , MEMBER_ID , STATUS , PLAN , Amount_Cents ",
        credit_header=" MEMBER_ID , Booking_ID , PLAN , Amount_Cents ",
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["booking_id"] for row in rows] == ["BOOK705000001", "BOOK705000002"]
    assert [row["member_id"] for row in rows] == ["MEMBER01", "MEMBER02"]
    assert summary["matched_amount_cents"] == 5500


def test_amounts_compare_as_base10_and_zero_padded_values_do_not_use_octal():
    write_base_inputs(
        ["BOOK800000001,MEMBER01,0000000999,FINAL,TEAM", "BOOK800000002,MEMBER02,0000009900,FINAL,HOTDESK"],
        ["BOOK800000001,MEMBER01,999,TEAM", "BOOK800000002,MEMBER02,0000009900,HOTDESK"],
    )
    rows, summary = run_program()
    assert [row["amount_cents"] for row in rows] == ["999", "9900"]
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert summary["matched_amount_cents"] == 10899


def test_invalid_credit_amount_is_unmatched_and_contributes_zero_to_amount_totals():
    write_base_inputs(
        ["BOOK810000001,MEMBER01,1000,FINAL,HOTDESK", "BOOK810000002,MEMBER02,1200,FINAL,PRIVATE"],
        ["BOOK810000001,MEMBER01,abc,HOTDESK", "BOOK810000002,MEMBER02,0000,PRIVATE", "BOOK810000003,MEMBER03,-50,TEAM"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert [row["amount_cents"] for row in rows] == ["abc", "0000", "-50"]
    assert summary == {"matched_count": 0, "matched_amount_cents": 0, "unmatched_count": 3, "unmatched_amount_cents": 0}


def test_invalid_booking_amount_is_not_eligible_even_when_credit_amount_is_valid():
    write_base_inputs(
        ["BOOK820000001,MEMBER01,ten,FINAL,HOTDESK", "BOOK820000002,MEMBER02,0,FINAL,PRIVATE"],
        ["BOOK820000001,MEMBER01,10,HOTDESK", "BOOK820000002,MEMBER02,1,PRIVATE"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
    assert summary["unmatched_amount_cents"] == 11


def test_blank_or_missing_amount_fields_are_ineligible():
    write_base_inputs(
        ["BOOK815000001,MEMBER01,,FINAL,HOTDESK", "BOOK815000002,MEMBER02,1200,FINAL,PRIVATE"],
        ["BOOK815000001,MEMBER01,500,HOTDESK", "BOOK815000002,MEMBER02,,PRIVATE"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED"]
    assert summary["matched_count"] == 0
    assert summary["unmatched_amount_cents"] == 500


def test_outputs_are_regenerated_instead_of_appended_or_left_stale():
    write_base_inputs(["BOOK830000001,MEMBER01,700,FINAL,HOTDESK"], ["BOOK830000001,MEMBER01,700,HOTDESK"])
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("stale,header\nstale,row\n")
    SUMMARY.write_text('{"matched_count":99}')
    rows, summary = run_program()
    assert list(rows[0].keys()) == ["booking_id", "member_id", "plan", "amount_cents", "status"]
    assert len(rows) == 1
    assert rows[0]["status"] == "MATCHED"
    assert summary["matched_count"] == 1


def test_summary_json_matches_report_derivation():
    write_base_inputs(
        [
            "BOOK840000001,MEMBER01,1200,FINAL,HOTDESK",
            "BOOK840000002,MEMBER02,2300,FINAL,PRIVATE",
            "BOOK840000003,MEMBER03,3400,FINAL,TEAM",
        ],
        [
            "BOOK840000001,MEMBER01,1200,HOTDESK",
            "BOOK840000002,MEMBER02,9999,PRIVATE",
            "BOOK840000003,MEMBER03,00x,TEAM",
        ],
    )
    rows, summary = run_program()
    assert summary == summary_from_report(rows)
