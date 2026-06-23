"""Milestone 3 tests for remittance business-date controls."""

import csv
import json
import os
import subprocess
from pathlib import Path

APP = Path("/app")
DATA = APP / "data" / "remittances.dat"
CALENDAR = APP / "config" / "cycle_calendar.txt"
EXPORT = APP / "out" / "remit_export.csv"
SUMMARY = APP / "out" / "remit_summary.txt"
PAYLOAD = APP / "out" / "remit_payload.json"
RAILS = APP / "config" / "rails.csv"


def write_inputs(rows, calendar_rows):
    """Replace fixed-width remittance data and calendar rows."""
    DATA.write_text("\n".join(rows) + "\n")
    CALENDAR.write_text("\n".join(calendar_rows) + "\n")
    RAILS.write_text("rail,allowed\nACH,true\nWIR,true\nRTP,true\nCHK,false\n")
    EXPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)
    PAYLOAD.unlink(missing_ok=True)


def run_all(rules_url="http://127.0.0.1:9"):
    """Run the COBOL batch and Java adapter, returning parsed outputs."""
    env = {**os.environ, "RULES_URL": rules_url}
    subprocess.run(["/app/scripts/run_all.sh"], check=True, cwd=APP, env=env, timeout=45)
    assert (APP / "build" / "remit_reconcile").read_bytes()[:4] == b"\x7fELF"
    assert (APP / "build" / "RemittanceAdapter.class").read_bytes()[:4] == bytes.fromhex("cafebabe")
    with EXPORT.open(newline="") as handle:
        export_rows = list(csv.DictReader(handle))
    summary = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        summary[key] = int(value)
    payload = json.loads(PAYLOAD.read_text())
    return export_rows, summary, payload


class TestMilestone3:
    """Business-date calendar enforcement in the Java adapter."""

    def test_closed_dates_and_duplicates_do_not_count_as_accepted(self):
        """Only open-date, allowed-rail, first-seen transactions should be accepted."""
        write_inputs(
            [
                "RREM930000001ACCT9301ACH000000100020260429P",
                "RREM930000002ACCT9302RTP000000200020260501P",
                "RREM930000001ACCT9301ACH000000100020260429P",
                "RREM930000003ACCT9303CHK000000300020260429P",
                "RREM930000004ACCT9304WIR000000400020260502P",
            ],
            [
                "20260429 OPEN",
                "20260501 CLOSED",
            ],
        )
        export_rows, summary, payload = run_all()

        assert [row["transaction_id"] for row in export_rows] == [
            "REM930000001",
            "REM930000002",
            "REM930000001",
            "REM930000004",
        ]
        assert summary["exported_count"] == 4
        assert [tx["status"] for tx in payload["transactions"]] == [
            "ACCEPTED",
            "CLOSED_DATE",
            "DUPLICATE",
            "CLOSED_DATE",
        ]
        assert payload["accepted_count"] == 1
        assert payload["accepted_amount_cents"] == 1000
        assert payload["rejected_count"] == 3
        assert [tx["amount_cents"] for tx in payload["transactions"]] == [
            "0000001000",
            "0000002000",
            "0000001000",
            "0000004000",
        ]

    def test_closed_first_occurrence_does_not_make_later_open_row_duplicate(self):
        """Only accepted transaction ids should cause DUPLICATE status for later rows."""
        write_inputs(
            [
                "RREM940000001ACCT9401ACH000000100020260501P",
                "RREM940000001ACCT9401ACH000000100020260429P",
                "RREM940000001ACCT9401ACH000000100020260429P",
                "RREM940000002ACCT9402RTP000000200020260430P",
            ],
            [
                "20260429 open",
                "20260430 OPEN",
                "20260501 CLOSED",
            ],
        )
        export_rows, summary, payload = run_all()

        assert [row["transaction_id"] for row in export_rows] == [
            "REM940000001",
            "REM940000001",
            "REM940000001",
            "REM940000002",
        ]
        assert [tx["status"] for tx in payload["transactions"]] == [
            "CLOSED_DATE",
            "ACCEPTED",
            "DUPLICATE",
            "ACCEPTED",
        ]
        assert payload["accepted_count"] == 2
        assert payload["accepted_amount_cents"] == 3000
        assert payload["rejected_count"] == 2

    def test_missing_calendar_date_is_closed_and_preserves_zero_padded_amounts(self):
        """Dates absent from the calendar should be CLOSED_DATE without altering amount strings."""
        write_inputs(
            [
                "RREM950000001ACCT9501WIR000000000020260430P",
                "RREM950000002ACCT9502ACH000000020020260502P",
                "RREM950000003ACCT9503RTP000000030020260501P",
            ],
            [
                "20260430 OPEN",
                "20260501 holiday",
            ],
        )
        export_rows, summary, payload = run_all()

        assert [row["amount_cents"] for row in export_rows] == [
            "0000000000",
            "0000000200",
            "0000000300",
        ]
        assert [tx["status"] for tx in payload["transactions"]] == [
            "ACCEPTED",
            "CLOSED_DATE",
            "CLOSED_DATE",
        ]
        assert [tx["amount_cents"] for tx in payload["transactions"]] == [
            "0000000000",
            "0000000200",
            "0000000300",
        ]
        assert payload["accepted_count"] == 1
        assert payload["accepted_amount_cents"] == 0
        assert payload["rejected_count"] == 2

    def test_open_date_rail_rejected_by_fallback_counts_as_rejected(self):
        """Fallback rail blocking should produce REJECTED on otherwise eligible open-date rows."""
        write_inputs(
            [
                "RREM960000001ACCT9601WIR000000150020260430P",
                "RREM960000002ACCT9602ACH000000250020260430P",
            ],
            [
                "20260430 OPEN",
            ],
        )
        RAILS.write_text("rail,allowed\nACH,true\nWIR,false\nRTP,true\nCHK,false\n")
        export_rows, summary, payload = run_all()

        assert [row["rail"] for row in export_rows] == ["WIR", "ACH"]
        assert summary == {"exported_count": 2, "exported_amount_cents": 4000, "rejected_count": 0}
        assert [tx["status"] for tx in payload["transactions"]] == ["REJECTED", "ACCEPTED"]
        assert payload["accepted_count"] == 1
        assert payload["accepted_amount_cents"] == 2500
        assert payload["rejected_count"] == 1

    def test_reachable_rules_service_can_override_local_fallback_file(self):
        """When the bundled rules service is reachable, its result should be used before fallback."""
        write_inputs(
            ["RREM970000001ACCT9701RTP000000510020260430P"],
            ["20260430 OPEN"],
        )
        RAILS.write_text("rail,allowed\nACH,true\nWIR,true\nRTP,false\nCHK,false\n")
        export_rows, summary, payload = run_all("http://localhost:8080")

        assert [row["rail"] for row in export_rows] == ["RTP"]
        assert summary == {"exported_count": 1, "exported_amount_cents": 5100, "rejected_count": 0}
        assert payload["transactions"][0]["status"] == "ACCEPTED"
        assert payload["accepted_count"] == 1
        assert payload["accepted_amount_cents"] == 5100
