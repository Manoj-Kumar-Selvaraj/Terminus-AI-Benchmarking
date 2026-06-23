"""Verifier tests for the library waiver reconciliation CLI."""
import csv
import json
import subprocess
from pathlib import Path

APP = Path("/app")
SOURCES = APP / "data" / "fines.csv"
ACTIONS = APP / "data" / "waivers.csv"
REPORT = APP / "out" / "waiver_report.csv"
SUMMARY = APP / "out" / "waiver_summary.json"


def write_inputs(source_rows, action_rows):
    """Replace input CSV files with a focused scenario and clear previous outputs."""
    SOURCES.write_text("fine_id,patron_id,amount_cents,status,desk\n" + "\n".join(source_rows) + "\n")
    ACTIONS.write_text("fine_id,patron_id,amount_cents,desk\n" + "\n".join(action_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the reconciliation script and return parsed outputs."""
    subprocess.run(["/app/scripts/run_batch.sh"], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    return rows, json.loads(SUMMARY.read_text())
def test_mobile_waiver_matches_and_counts_positive_amount():
    """MOBILE waivers should match eligible fines and add positive cents."""
    write_inputs(
        ["FINE100000001,PATRON_ID01,0000001200,ASSESSED,FRONT", "FINE100000002,PATRON_ID02,0000002300,ASSESSED,MOBILE"],
        ["FINE100000001,PATRON_ID01,0000001200,FRONT", "FINE100000002,PATRON_ID02,0000002300,MOBILE"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["desk"] == "MOBILE"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 3500

def test_fine_id_match_uses_full_identifier():
    """A waiver must not match a fine sharing only the leading id prefix."""
    write_inputs(
        ["FINE777770001,PATRON_ID01,0000003300,ASSESSED,FRONT", "FINE777770002,PATRON_ID01,0000003300,ASSESSED,FRONT"],
        ["FINE777770003,PATRON_ID01,0000003300,FRONT", "FINE777770002,PATRON_ID01,0000003300,FRONT"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300

def test_customer_amount_status_and_desk_all_gate_matching():
    """Customer, amount, status, and desk must all gate matching."""
    write_inputs(
        [
            "FINE300000001,PATRON_ID01,0000001000,ASSESSED,FRONT",
            "FINE300000002,PATRON_ID02,0000002000,ASSESSED,ONLINE",
            "FINE300000003,PATRON_ID03,0000003000,PENDING,MOBILE",
            "FINE300000004,PATRON_ID04,0000004000,ASSESSED,OTHER",
        ],
        [
            "FINE300000001,WRONG001,0000001000,FRONT",
            "FINE300000002,PATRON_ID02,0000002100,ONLINE",
            "FINE300000003,PATRON_ID03,0000003000,MOBILE",
            "FINE300000004,PATRON_ID04,0000004000,OTHER",
        ],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
    assert summary["matched_count"] == 0
    assert summary["unmatched_amount_cents"] == 10100

def test_duplicate_waivers_do_not_reuse_consumed_fine():
    """Duplicate waivers must not reuse the same consumed fine."""
    write_inputs(
        ["FINE400000001,PATRON_ID01,0000005500,ASSESSED,ONLINE"],
        ["FINE400000001,PATRON_ID01,0000005500,ONLINE", "FINE400000001,PATRON_ID01,0000005500,ONLINE"],
    )
    rows, summary = run_program()
    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
    assert summary["matched_count"] == 1
    assert summary["unmatched_count"] == 1

def test_matching_trims_fields_and_normalizes_desk_status_case():
    """Matching should trim fields and compare status/desk case-insensitively."""
    write_inputs(
        ["  FINE500000001  ,  PATRON_ID01  , 0000006600 , assessed , online "],
        [" FINE500000001 , PATRON_ID01 , 0000006600 , ONLINE "],
    )
    rows, summary = run_program()
    assert rows[0]["status"] == "MATCHED"
    assert rows[0]["desk"] == "ONLINE"
    assert summary["matched_amount_cents"] == 6600

def test_report_schema_and_waiver_input_order_are_stable():
    """Report schema and waiver input order should be stable."""
    write_inputs(
        ["FINE600000002,PATRON_ID02,0000001200,ASSESSED,FRONT", "FINE600000001,PATRON_ID01,0000001100,ASSESSED,ONLINE"],
        ["FINE600000001,PATRON_ID01,0000001100,ONLINE", "FINENO_MATCH,PATRON_ID09,0000009900,FRONT", "FINE600000002,PATRON_ID02,0000001200,FRONT"],
    )
    rows, summary = run_program()
    assert list(rows[0].keys()) == ["fine_id", "patron_id", "desk", "amount_cents", "status"]
    assert [row["fine_id"] for row in rows] == ["FINE600000001", "FINENO_MATCH", "FINE600000002"]
    assert rows[1]["desk"] == ""
    assert summary == {"matched_count": 2, "matched_amount_cents": 2300, "unmatched_count": 1, "unmatched_amount_cents": 9900}
