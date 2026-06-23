
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



def write_inputs(session_rows, refund_rows, calendar_rows, method_rows, include_method=True, include_settlement=True):
    write_file(SESSIONS, "session_id,guardian_id,amount_cents,status,room,attendance_date\n" + "\n".join(session_rows) + "\n")
    header = "session_id,guardian_id,amount_cents,room,refund_date"
    if include_method:
        header += ",refund_method"
    if include_settlement:
        header += ",settlement_date"
    write_file(REFUNDS, header + "\n" + "\n".join(refund_rows) + "\n")
    write_file(CALENDAR, "\n".join(calendar_rows) + "\n")
    write_file(ALIASES, "alias,canonical,enabled\nINF,INFANT,true\nTOD,TODDLER,true\nPK,PREK,true\n")
    write_file(METHODS, "method,enabled,max_lag_days\n" + "\n".join(method_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


class TestMilestone4:
    def test_enabled_method_and_settlement_lag_compose_with_latest_selection(self):
        write_inputs(
            [
                "M4-1,G1,1200,CHECKEDIN,TODDLER,2026-04-07",
                "M4-1,G1,1200,CHECKEDIN,TODDLER,2026-04-09",
            ],
            ["M4-1,G1,1200,TOD,2026-04-05, ach ,2026-04-08"],
            ["2026-04-05 open"],
            [" ACH , TRUE , 3"],
        )
        rows, summary = run_program()
        assert rows == [{"session_id": "M4-1", "guardian_id": "G1", "room": "TODDLER", "amount_cents": "1200", "status": "MATCHED"}]
        assert summary == {"matched_count": 1, "matched_amount_cents": 1200, "unmatched_count": 0, "unmatched_amount_cents": 0}

    def test_disabled_blank_unlisted_and_duplicate_method_rows_are_rejected_or_first_wins(self):
        write_inputs(
            ["M4-2A,G1,100,CHECKEDIN,INFANT,2026-04-10", "M4-2B,G2,200,CHECKEDIN,INFANT,2026-04-10", "M4-2C,G3,300,CHECKEDIN,INFANT,2026-04-10", "M4-2D,G4,400,CHECKEDIN,INFANT,2026-04-10"],
            ["M4-2A,G1,100,INF,2026-04-05,CASH,2026-04-05", "M4-2B,G2,200,INF,2026-04-05,,2026-04-05", "M4-2C,G3,300,INF,2026-04-05,WIRE,2026-04-05", "M4-2D,G4,400,INF,2026-04-05,DUP,2026-04-05"],
            ["2026-04-05 open"],
            ["CASH,false,5", "DUP,false,5", "DUP,true,5"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary["unmatched_amount_cents"] == 1000

    def test_enabled_values_y_yes_and_one_are_accepted(self):
        write_inputs(
            ["M4-3A,G1,100,CHECKEDIN,INFANT,2026-04-10", "M4-3B,G2,200,CHECKEDIN,TODDLER,2026-04-10", "M4-3C,G3,300,CHECKEDIN,PREK,2026-04-10"],
            ["M4-3A,G1,100,INF,2026-04-05,ACH,2026-04-05", "M4-3B,G2,200,TOD,2026-04-05,CARD,2026-04-06", "M4-3C,G3,300,PK,2026-04-05,VOUCHER,2026-04-07"],
            ["2026-04-05 open"],
            ["ACH,y,0", "CARD,Yes,1", "VOUCHER,1,2"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [r["room"] for r in rows] == ["INFANT", "TODDLER", "PREK"]
        assert summary["matched_amount_cents"] == 600

    def test_method_config_header_order_and_extra_columns_are_supported(self):
        write_inputs(
            ["M4-3D,G4,450,CHECKEDIN,INFANT,2026-04-10"],
            ["M4-3D,G4,450,INF,2026-04-05,WIRE,2026-04-06"],
            ["2026-04-05 open"],
            [],
        )
        write_file(METHODS, "enabled,notes,max_lag_days,method\n yes ,runtime row, 2 , wire \n")
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["room"] == "INFANT"
        assert summary["matched_amount_cents"] == 450

    def test_absent_method_column_preserves_dated_matching_behavior(self):
        write_inputs(
            ["M4-4,G1,900,CHECKEDIN,PREK,2026-04-09"],
            ["M4-4,G1,900,PK,2026-04-05"],
            ["2026-04-05 open"],
            ["ACH,false,0"],
            include_method=False,
            include_settlement=False,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["room"] == "PREK"
        assert summary["matched_count"] == 1

    def test_settlement_date_must_be_valid_not_before_refund_and_within_lag(self):
        write_inputs(
            ["M4-5A,G1,100,CHECKEDIN,INFANT,2026-04-10", "M4-5B,G2,200,CHECKEDIN,INFANT,2026-04-10", "M4-5C,G3,300,CHECKEDIN,INFANT,2026-04-10", "M4-5D,G4,400,CHECKEDIN,INFANT,2026-04-10"],
            ["M4-5A,G1,100,INF,2026-04-05,ACH,2026-04-04", "M4-5B,G2,200,INF,2026-04-05,ACH,2026-04-08", "M4-5C,G3,300,INF,2026-04-05,ACH,bad-date", "M4-5D,G4,400,INF,2026-04-05,ACH,"],
            ["2026-04-05 open"],
            ["ACH,true,2"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 1000

    def test_absent_settlement_column_applies_method_gate_without_lag_check(self):
        write_inputs(
            ["M4-6,G1,650,CHECKEDIN,TODDLER,2026-04-10"],
            ["M4-6,G1,650,TOD,2026-04-05,CARD"],
            ["2026-04-05 open"],
            ["CARD,true,0"],
            include_method=True,
            include_settlement=False,
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["room"] == "TODDLER"
        assert summary["matched_amount_cents"] == 650

    def test_malformed_or_negative_max_lag_disables_method(self):
        write_inputs(
            ["M4-7A,G1,111,CHECKEDIN,PREK,2026-04-10", "M4-7B,G2,222,CHECKEDIN,PREK,2026-04-10"],
            ["M4-7A,G1,111,PK,2026-04-05,BAD,2026-04-05", "M4-7B,G2,222,PK,2026-04-05,NEG,2026-04-05"],
            ["2026-04-05 open"],
            ["BAD,true,abc", "NEG,true,-1"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["UNMATCHED", "UNMATCHED"]
        assert summary["unmatched_amount_cents"] == 333

    def test_method_gate_does_not_bypass_prior_room_calendar_or_date_rules(self):
        write_inputs(
            ["M4-8A,G1,300,CHECKEDIN,INFANT,2026-04-10", "M4-8B,G2,400,CHECKEDIN,TODDLER,2026-04-04", "M4-8C,G3,500,CHECKEDIN,PREK,2026-04-10"],
            ["M4-8A,G1,300,TOD,2026-04-05,ACH,2026-04-05", "M4-8B,G2,400,TOD,2026-04-05,ACH,2026-04-05", "M4-8C,G3,500,PK,2026-04-06,ACH,2026-04-06"],
            ["2026-04-05 open", "2026-04-06 closed"],
            ["ACH,true,5"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary["unmatched_amount_cents"] == 1200
