
import csv
import json
import subprocess
from pathlib import Path

import pytest

APP = Path("/app")
SESSIONS = APP / "data" / "sessions.csv"
REFUNDS = APP / "data" / "refunds.csv"
ALIASES = APP / "config" / "room_aliases.csv"
CALENDAR = APP / "config" / "cutoff_calendar.txt"
METHODS = APP / "config" / "methods.csv"
REPORT = APP / "out" / "refund_report.csv"
SUMMARY = APP / "out" / "refund_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


def write_file(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def run_program():
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    build_program()



def write_inputs(session_header, session_rows, refund_header, refund_rows):
    write_file(SESSIONS, session_header + "\n" + "\n".join(session_rows) + "\n")
    write_file(REFUNDS, refund_header + "\n" + "\n".join(refund_rows) + "\n")
    REPORT.write_text("stale\n") if REPORT.exists() else None
    SUMMARY.write_text('{"stale": true}\n') if SUMMARY.exists() else None


class TestMilestone1:
    def test_header_order_extra_columns_trim_casefold_and_positive_totals(self):
        write_inputs(
            "notes,room,status,amount_cents,guardian_id,session_id",
            [
                "kept, toddler , checkedin , 1200 , G100 , S-100-A ",
                "kept,INFANT,CANCELLED,900,G200,S-200-A",
            ],
            "guardian_id,session_id,room,amount_cents,export_note",
            [
                " G100 , S-100-A , TODDLER , 1200 , ok",
                "G200,S-200-A,INFANT,900,nope",
            ],
        )
        rows, summary = run_program()
        assert rows == [
            {"session_id": "S-100-A", "guardian_id": "G100", "room": "TODDLER", "amount_cents": "1200", "status": "MATCHED"},
            {"session_id": "S-200-A", "guardian_id": "G200", "room": "", "amount_cents": "900", "status": "UNMATCHED"},
        ]
        assert summary == {"matched_count": 1, "matched_amount_cents": 1200, "unmatched_count": 1, "unmatched_amount_cents": 900}

    def test_matched_report_uses_cleaned_refund_identity_fields(self):
        write_inputs(
            "session_id,guardian_id,amount_cents,status,room",
            [" CLEAN-ID , CLEAN-G , 321 , CHECKEDIN , INFANT "],
            "room,amount_cents,guardian_id,session_id",
            [" INFANT , 321 , CLEAN-G , CLEAN-ID "],
        )
        rows, summary = run_program()
        assert rows[0] == {
            "session_id": "CLEAN-ID",
            "guardian_id": "CLEAN-G",
            "room": "INFANT",
            "amount_cents": "321",
            "status": "MATCHED",
        }
        assert summary["matched_amount_cents"] == 321

    def test_full_session_id_equality_prevents_prefix_collision(self):
        write_inputs(
            "session_id,guardian_id,amount_cents,status,room",
            [
                "ABCDEF01-REAL,G900,500,CHECKEDIN,INFANT",
                "ABCDEF01-OTHER,G900,500,CHECKEDIN,INFANT",
            ],
            "session_id,guardian_id,amount_cents,room",
            ["ABCDEF01,G900,500,INFANT"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["room"] == ""
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 500

    def test_refund_input_order_consumes_each_session_row_once(self):
        write_inputs(
            "session_id,guardian_id,amount_cents,status,room",
            ["S-301,G301,700,CHECKEDIN,PREK"],
            "session_id,guardian_id,amount_cents,room",
            ["S-301,G301,700,PREK", "S-301,G301,700,PREK"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["MATCHED", "UNMATCHED"]
        assert [r["room"] for r in rows] == ["PREK", ""]
        assert summary == {"matched_count": 1, "matched_amount_cents": 700, "unmatched_count": 1, "unmatched_amount_cents": 700}

    def test_duplicate_session_ids_in_distinct_rows_are_independently_consumable(self):
        write_inputs(
            "session_id,guardian_id,amount_cents,status,room",
            ["DUP-1,G401,800,CHECKEDIN,TODDLER", "DUP-1,G401,800,CHECKEDIN,TODDLER"],
            "session_id,guardian_id,amount_cents,room",
            ["DUP-1,G401,800,TODDLER", "DUP-1,G401,800,TODDLER", "DUP-1,G401,800,TODDLER"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 2
        assert summary["unmatched_count"] == 1
        assert summary["matched_amount_cents"] == 1600

    def test_malformed_and_nonpositive_session_rows_are_ignored_without_crashing(self):
        write_inputs(
            "session_id,guardian_id,amount_cents,status,room",
            [
                "BAD-1,G501,not-cents,CHECKEDIN,INFANT",
                "BAD-2,G502,0,CHECKEDIN,TODDLER",
                "GOOD-1,G503,650,CHECKEDIN,PREK",
            ],
            "session_id,guardian_id,amount_cents,room",
            ["BAD-1,G501,not-cents,INFANT", "BAD-2,G502,0,TODDLER", "GOOD-1,G503,650,PREK"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["UNMATCHED", "UNMATCHED", "MATCHED"]
        assert [r["amount_cents"] for r in rows] == ["not-cents", "0", "650"]
        assert summary == {"matched_count": 1, "matched_amount_cents": 650, "unmatched_count": 2, "unmatched_amount_cents": 0}

    def test_refund_rows_missing_required_fields_still_report_unmatched(self):
        write_inputs(
            "session_id,guardian_id,amount_cents,status,room",
            ["MISS-REFUND,G905,500,CHECKEDIN,INFANT"],
            "session_id,amount_cents,room",
            ["MISS-REFUND,500,INFANT"],
        )
        rows, summary = run_program()
        assert rows[0] == {
            "session_id": "MISS-REFUND",
            "guardian_id": "",
            "room": "",
            "amount_cents": "500",
            "status": "UNMATCHED",
        }
        assert summary == {"matched_count": 0, "matched_amount_cents": 0, "unmatched_count": 1, "unmatched_amount_cents": 500}

    def test_session_rows_missing_required_fields_are_ignored_as_candidates(self):
        write_inputs(
            "session_id,guardian_id,amount_cents,status",
            [
                "MISS-ROOM,G901,500,CHECKEDIN",
                "MISS-STATUS,G902,600,",
            ],
            "session_id,guardian_id,amount_cents,room",
            [
                "MISS-ROOM,G901,500,INFANT",
                "MISS-STATUS,G902,600,TODDLER",
            ],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["UNMATCHED", "UNMATCHED"]
        assert [r["room"] for r in rows] == ["", ""]
        assert summary == {"matched_count": 0, "matched_amount_cents": 0, "unmatched_count": 2, "unmatched_amount_cents": 1100}

    def test_guardian_amount_status_and_room_all_remain_required(self):
        write_inputs(
            "session_id,guardian_id,amount_cents,status,room",
            [
                "S-601,G601,100,CHECKEDIN,INFANT",
                "S-602,G602,200,CHECKEDIN,TODDLER",
                "S-603,G603,300,VOID,PREK",
                "S-604,G604,400,CHECKEDIN,INFANT",
            ],
            "session_id,guardian_id,amount_cents,room",
            [
                "S-601,WRONG,100,INFANT",
                "S-602,G602,201,TODDLER",
                "S-603,G603,300,PREK",
                "S-604,G604,400,TODDLER",
            ],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["UNMATCHED"] * 4
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 1001

    def test_report_schema_is_exact_and_stale_outputs_are_replaced(self):
        write_inputs(
            "session_id,guardian_id,amount_cents,status,room,ignored",
            ["S-701,G701,333,CHECKEDIN,INFANT,x"],
            "ignored,room,amount_cents,session_id,guardian_id",
            ["x,INFANT,333,S-701,G701"],
        )
        rows, summary = run_program()
        with REPORT.open(newline="") as f:
            header = next(csv.reader(f))
        assert header == ["session_id", "guardian_id", "room", "amount_cents", "status"]
        assert rows[0]["status"] == "MATCHED"
        assert "stale" not in SUMMARY.read_text()
        assert summary["matched_amount_cents"] == 333

    def test_blank_or_unknown_rooms_are_unmatched_and_count_positive_amounts(self):
        write_inputs(
            "session_id,guardian_id,amount_cents,status,room",
            ["S-801,G801,444,CHECKEDIN,INFANT", "S-802,G802,555,CHECKEDIN,NURSERY"],
            "session_id,guardian_id,amount_cents,room",
            [" S-801 , G801 ,444, ", " S-802 , G802 ,555,NURSERY"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["UNMATCHED", "UNMATCHED"]
        assert [r["session_id"] for r in rows] == ["S-801", "S-802"]
        assert [r["guardian_id"] for r in rows] == ["G801", "G802"]
        assert summary == {"matched_count": 0, "matched_amount_cents": 0, "unmatched_count": 2, "unmatched_amount_cents": 999}
