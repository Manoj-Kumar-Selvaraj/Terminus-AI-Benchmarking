
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



def write_inputs(session_rows, refund_rows, calendar_rows, alias_rows=None):
    write_file(SESSIONS, "session_id,guardian_id,amount_cents,status,room,attendance_date\n" + "\n".join(session_rows) + "\n")
    write_file(REFUNDS, "session_id,guardian_id,amount_cents,room,refund_date\n" + "\n".join(refund_rows) + "\n")
    write_file(CALENDAR, "\n".join(calendar_rows) + "\n")
    if alias_rows is None:
        alias_rows = ["INF,INFANT,true", "TOD,TODDLER,true", "PK,PREK,true"]
    write_file(ALIASES, "alias,canonical,enabled\n" + "\n".join(alias_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


class TestMilestone3:
    def test_open_calendar_and_latest_attendance_date_selection(self):
        write_inputs(
            [
                "M3-1,G1,1000,CHECKEDIN,TODDLER,2026-04-06",
                "M3-1,G1,1500,CHECKEDIN,TODDLER,2026-04-09",
                "M3-1,G1,1200,CHECKEDIN,TODDLER,2026-04-08",
            ],
            ["M3-1,G1,1500,TOD,2026-04-05", "M3-1,G1,1000,TOD,2026-04-05"],
            ["2026-04-05 open", "2026-04-06 open", "2026-04-08 open", "2026-04-09 open"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["MATCHED", "MATCHED"]
        assert [r["amount_cents"] for r in rows] == ["1500", "1000"]
        assert [r["room"] for r in rows] == ["TODDLER", "TODDLER"]
        assert summary["matched_count"] == 2
        assert summary["matched_amount_cents"] == 2500

    def test_latest_attendance_date_choice_changes_later_refund_outcome(self):
        """Same-amount sessions with different dates must consume the latest row first so a later stricter refund stays unmatched."""
        write_inputs(
            [
                "M3-8871,G1,1000,CHECKEDIN,TODDLER,2026-04-03",
                "M3-8871,G1,1000,CHECKEDIN,TODDLER,2026-04-06",
            ],
            [
                "M3-8871,G1,1000,TOD,2026-04-01",
                "M3-8871,G1,1000,TOD,2026-04-05",
            ],
            ["2026-04-01 open", "2026-04-05 open"],
        )
        rows, summary = run_program()
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["room"] for row in rows] == ["TODDLER", ""]
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 1000,
            "unmatched_count": 1,
            "unmatched_amount_cents": 1000,
        }

    def test_closed_unlisted_missing_and_malformed_refund_dates_are_rejected(self):
        write_inputs(
            [
                "M3-2A,G1,100,CHECKEDIN,INFANT,2026-04-10",
                "M3-2B,G2,200,CHECKEDIN,INFANT,2026-04-10",
                "M3-2C,G3,300,CHECKEDIN,INFANT,2026-04-10",
                "M3-2D,G4,400,CHECKEDIN,INFANT,2026-04-10",
            ],
            [
                "M3-2A,G1,100,INF,2026-04-06",
                "M3-2B,G2,200,INF,2026-04-07",
                "M3-2C,G3,300,INF,",
                "M3-2D,G4,400,INF,04/05/2026",
            ],
            ["2026-04-06 closed", "2026-04-05 open"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["UNMATCHED"] * 4
        assert summary["unmatched_amount_cents"] == 1000

    def test_missing_or_malformed_attendance_date_prevents_matching(self):
        write_inputs(
            ["M3-3A,G1,500,CHECKEDIN,PREK,", "M3-3B,G2,600,CHECKEDIN,PREK,2026/04/10"],
            ["M3-3A,G1,500,PK,2026-04-05", "M3-3B,G2,600,PK,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["UNMATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 1100

    def test_refund_date_after_attendance_date_is_ineligible(self):
        write_inputs(
            ["M3-4,G1,777,CHECKEDIN,TODDLER,2026-04-04"],
            ["M3-4,G1,777,TOD,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["unmatched_amount_cents"] == 777

    def test_tie_on_attendance_date_uses_earliest_session_row_then_consumes_it(self):
        write_inputs(
            [
                "M3-5,G1,300,CHECKEDIN,INFANT,2026-04-10",
                "M3-5,G1,300,CHECKEDIN,INFANT,2026-04-10",
            ],
            ["M3-5,G1,300,INF,2026-04-05", "M3-5,G1,300,INF,2026-04-05", "M3-5,G1,300,INF,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["MATCHED", "MATCHED", "UNMATCHED"]
        assert summary == {"matched_count": 2, "matched_amount_cents": 600, "unmatched_count": 1, "unmatched_amount_cents": 300}

    def test_calendar_allows_comments_spaces_and_casefolded_open_status(self):
        write_inputs(
            ["M3-6,G1,910,CHECKEDIN,INFANT,2026-04-09"],
            ["M3-6,G1,910,INF,2026-04-05"],
            ["# comment", "   ", " 2026-04-05   OPEN  ", "not-a-date open"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["room"] == "INFANT"
        assert summary["matched_amount_cents"] == 910

    def test_header_order_with_extra_date_columns_is_respected(self):
        write_file(SESSIONS, "extra,attendance_date,room,status,amount_cents,guardian_id,session_id\nx,2026-04-11,PREK,CHECKEDIN,990,G7,M3-7\n")
        write_file(REFUNDS, "refund_date,room,session_id,guardian_id,amount_cents,extra\n2026-04-05,PK,M3-7,G7,990,x\n")
        write_file(CALENDAR, "2026-04-05 open\n")
        write_file(ALIASES, "alias,canonical,enabled\nPK,PREK,true\n")
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["room"] == "PREK"
        assert summary["matched_count"] == 1

    def test_date_gate_does_not_bypass_room_guardian_or_amount_rules(self):
        write_inputs(
            ["M3-8A,G1,100,CHECKEDIN,INFANT,2026-04-10", "M3-8B,G2,200,CHECKEDIN,TODDLER,2026-04-10", "M3-8C,G3,300,CHECKEDIN,PREK,2026-04-10"],
            ["M3-8A,WRONG,100,INF,2026-04-05", "M3-8B,G2,201,TOD,2026-04-05", "M3-8C,G3,300,TOD,2026-04-05"],
            ["2026-04-05 open"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary["unmatched_amount_cents"] == 601
