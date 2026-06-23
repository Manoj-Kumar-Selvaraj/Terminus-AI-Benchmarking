
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



def write_inputs(session_rows, refund_rows, alias_rows):
    write_file(SESSIONS, "session_id,guardian_id,amount_cents,status,room\n" + "\n".join(session_rows) + "\n")
    write_file(REFUNDS, "session_id,guardian_id,amount_cents,room\n" + "\n".join(refund_rows) + "\n")
    write_file(ALIASES, "alias,canonical,enabled\n" + "\n".join(alias_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


class TestMilestone2:
    def test_runtime_aliases_apply_to_sessions_and_refunds_and_emit_canonical_rooms(self):
        write_inputs(
            ["A-1,G1,100,CHECKEDIN,BABY", "A-2,G2,200,CHECKEDIN,twos", "A-3,G3,300,CHECKEDIN,Pre School"],
            ["A-1,G1,100,inf", "A-2,G2,200,TOD", "A-3,G3,300,PK"],
            ["baby,INFANT,true", "INF,INFANT,yes", "twos,TODDLER,1", "TOD,TODDLER,y", "Pre School,PREK,true", "PK,PREK,true"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [r["room"] for r in rows] == ["INFANT", "TODDLER", "PREK"]
        assert summary["matched_amount_cents"] == 600

    def test_disabled_blank_and_unlisted_alias_values_are_ineligible(self):
        write_inputs(
            ["B-1,G1,100,CHECKEDIN,BABY", "B-2,G2,200,CHECKEDIN,TODDLER", "B-3,G3,300,CHECKEDIN,PREK"],
            ["B-1,G1,100,BABY", "B-2,G2,200,TOTS", "B-3,G3,300,"],
            ["BABY,INFANT,false", "TOTS,TODDLER,no", ",PREK,true"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert [r["room"] for r in rows] == ["", "", ""]
        assert summary["unmatched_amount_cents"] == 600

    def test_alias_to_unsupported_canonical_room_is_rejected(self):
        write_inputs(
            ["C-1,G1,400,CHECKEDIN,NURSERY"],
            ["C-1,G1,400,NUR"],
            ["NURSERY,NURSERY,true", "NUR,NURSERY,true"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "UNMATCHED"
        assert summary["matched_count"] == 0

    def test_canonical_room_identities_still_work_without_alias_rows(self):
        write_inputs(
            ["D-1,G1,250,CHECKEDIN,INFANT", "D-2,G2,350,CHECKEDIN,TODDLER", "D-3,G3,450,CHECKEDIN,PREK"],
            ["D-1,G1,250,INFANT", "D-2,G2,350,TODDLER", "D-3,G3,450,PREK"],
            [],
        )
        rows, summary = run_program()
        assert [r["room"] for r in rows] == ["INFANT", "TODDLER", "PREK"]
        assert summary["matched_count"] == 3

    def test_alias_config_is_runtime_driven_not_hardcoded_to_sample_aliases(self):
        write_inputs(
            ["E-1,G1,700,CHECKEDIN,CRAWLERS", "E-2,G2,800,CHECKEDIN,PK"],
            ["E-1,G1,700,LITTLE", "E-2,G2,800,PREK"],
            ["CRAWLERS,INFANT,true", "LITTLE,INFANT,true", "PK,TODDLER,false"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["MATCHED", "UNMATCHED"]
        assert [r["room"] for r in rows] == ["INFANT", ""]
        assert summary == {"matched_count": 1, "matched_amount_cents": 700, "unmatched_count": 1, "unmatched_amount_cents": 800}

    def test_alias_file_header_order_and_extra_columns_are_handled(self):
        write_file(SESSIONS, "session_id,guardian_id,amount_cents,status,room\nF-1,G1,510,CHECKEDIN,cubs\n")
        write_file(REFUNDS, "session_id,guardian_id,amount_cents,room\nF-1,G1,510,bears\n")
        write_file(ALIASES, "enabled,comment,canonical,alias\n true ,x, INFANT , cubs \n yes ,x, INFANT , bears \n")
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["room"] == "INFANT"
        assert summary["matched_amount_cents"] == 510

    def test_malformed_alias_rows_do_not_block_valid_alias_rows(self):
        write_inputs(
            ["G-1,G1,610,CHECKEDIN,owlets", "G-2,G2,620,CHECKEDIN,badone"],
            ["G-1,G1,610,owlet-refund", "G-2,G2,620,badone"],
            ["owlets,INFANT,true", "too-short", "badone,,true", "owlet-refund,INFANT,true"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["MATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 1
        assert summary["unmatched_amount_cents"] == 620

    def test_alias_matching_does_not_relax_identifier_amount_or_status_rules(self):
        write_inputs(
            ["H-1,G1,100,CHECKEDIN,baby", "H-2,G2,200,PENDING,twos", "H-3,G3,300,CHECKEDIN,prek-old"],
            ["H-1,GX,100,inf", "H-2,G2,200,tod", "H-3,G3,301,pk"],
            ["baby,INFANT,true", "inf,INFANT,true", "twos,TODDLER,true", "tod,TODDLER,true", "prek-old,PREK,true", "pk,PREK,true"],
        )
        rows, summary = run_program()
        assert [r["status"] for r in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert summary["matched_count"] == 0
        assert summary["unmatched_amount_cents"] == 601

    def test_first_enabled_duplicate_alias_row_wins_for_same_alias(self):
        """When two alias rows map the same alias differently, the first enabled row wins."""
        write_inputs(
            ["I-1,G1,900,CHECKEDIN,INFANT"],
            ["I-1,G1,900,cubs"],
            ["cubs,INFANT,true", "cubs,TODDLER,true"],
        )
        rows, summary = run_program()
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["room"] == "INFANT"
        assert summary == {
            "matched_count": 1,
            "matched_amount_cents": 900,
            "unmatched_count": 0,
            "unmatched_amount_cents": 0,
        }
