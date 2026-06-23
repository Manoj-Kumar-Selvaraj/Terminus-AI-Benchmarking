"""Verifier tests for the COBOL and Java remittance router."""
import csv
import json
import os
import subprocess
from pathlib import Path

APP = Path("/app")
DATA = APP / "data" / "remittances.dat"
EXPORT = APP / "out" / "remit_export.csv"
SUMMARY = APP / "out" / "remit_summary.txt"
PAYLOAD = APP / "out" / "remit_payload.json"
RAILS = APP / "config" / "rails.csv"


def write_inputs(rows):
    """Replace the fixed-width remittance input data for a focused scenario."""
    DATA.write_text("\n".join(rows) + "\n")
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


class TestMilestone2:
    """Duplicate transaction-id behavior layered on the milestone 1 router fixes."""

    def test_rtp_is_exported_and_service_payload_accepts_allowed_rails(self):
        """RTP should be exported by COBOL and accepted after the Java service lookup."""
        write_inputs([
            "RREM202604101ACCT1001ACH000001250020260430P",
            "RREM202604102ACCT1002RTP000000880020260430P",
            "RREM202604103ACCT1003WIR000000410020260430P",
            "RREM202604104ACCT1004CHK000000070020260430P",
            "RREM202604105ACCT1005ACH000000050020260430H",
        ])
        export_rows, summary, payload = run_all()

        assert [row["rail"] for row in export_rows] == ["ACH", "RTP", "WIR"]
        assert summary["exported_count"] == 3
        assert summary["exported_amount_cents"] == 25400
        assert summary["rejected_count"] == 2
        assert payload["accepted_count"] == 3
        assert payload["accepted_amount_cents"] == 25400
        assert [tx["account_id"] for tx in payload["transactions"]] == ["ACCT1001", "ACCT1002", "ACCT1003"]
        assert [tx["status"] for tx in payload["transactions"]] == ["ACCEPTED", "ACCEPTED", "ACCEPTED"]

    def test_export_schema_order_and_zero_padded_amounts_are_stable(self):
        """The COBOL export should preserve input order and raw zero-padded amount text."""
        write_inputs([
            "RREM900000003ACCT9003WIR000000030020260430P",
            "RREM900000001ACCT9001ACH000000010020260430P",
            "RREM900000002ACCT9002RTP000000020020260430P",
        ])
        export_rows, summary, payload = run_all()

        assert EXPORT.read_text().splitlines()[0] == "transaction_id,account_id,rail,amount_cents,business_date"
        assert [row["transaction_id"] for row in export_rows] == ["REM900000003", "REM900000001", "REM900000002"]
        assert [row["amount_cents"] for row in export_rows] == ["0000000300", "0000000100", "0000000200"]
        assert [tx["amount_cents"] for tx in payload["transactions"]] == ["0000000300", "0000000100", "0000000200"]
        assert summary["exported_amount_cents"] == 600
        assert payload["accepted_amount_cents"] == 600

    def test_unreachable_rules_service_uses_rails_csv_fallback(self):
        """When RULES_URL is unreachable, the adapter should honor the local rails.csv fallback."""
        write_inputs([
            "RREM810000001ACCT8101WIR000000330020260430P",
            "RREM810000002ACCT8102ACH000000120020260430P",
        ])
        RAILS.write_text("rail,allowed\nACH,true\nWIR,false\nRTP,true\nCHK,false\n")
        export_rows, summary, payload = run_all()

        assert [row["rail"] for row in export_rows] == ["WIR", "ACH"]
        assert summary == {"exported_count": 2, "exported_amount_cents": 4500, "rejected_count": 0}
        assert [tx["status"] for tx in payload["transactions"]] == ["REJECTED", "ACCEPTED"]
        assert payload["accepted_count"] == 1
        assert payload["accepted_amount_cents"] == 1200
        assert payload["rejected_count"] == 1

    def test_reachable_rules_service_takes_precedence_over_modified_fallback_file(self):
        """A reachable rules service should be used before local fallback configuration."""
        write_inputs(["RREM820000001ACCT8201RTP000000440020260430P"])
        RAILS.write_text("rail,allowed\nACH,true\nWIR,true\nRTP,false\nCHK,false\n")
        export_rows, summary, payload = run_all("http://localhost:8080")

        assert [row["rail"] for row in export_rows] == ["RTP"]
        assert summary == {"exported_count": 1, "exported_amount_cents": 4400, "rejected_count": 0}
        assert payload["transactions"][0]["status"] == "ACCEPTED"
        assert payload["accepted_count"] == 1
        assert payload["accepted_amount_cents"] == 4400

    def test_duplicate_transaction_ids_do_not_double_count(self):
        """Later duplicate transaction ids should stay in the payload as DUPLICATE and not count as accepted."""
        write_inputs([
            "RREM555500001ACCT5551ACH000000720020260430P",
            "RREM555500001ACCT5551ACH000000720020260430P",
            "RREM555500002ACCT5552RTP000000410020260430P",
        ])
        export_rows, summary, payload = run_all()

        assert [row["transaction_id"] for row in export_rows] == ["REM555500001", "REM555500001", "REM555500002"]
        assert [tx["status"] for tx in payload["transactions"]] == ["ACCEPTED", "DUPLICATE", "ACCEPTED"]
        assert payload["accepted_count"] == 2
        assert payload["accepted_amount_cents"] == 11300
        assert payload["rejected_count"] == 1
        assert payload["transactions"][1]["amount_cents"] == "0000007200"

    def test_duplicate_rows_keep_payload_order_and_do_not_poison_new_ids(self):
        """Duplicate accounting should preserve order while later unique ids still accept."""
        write_inputs([
            "RREM565600001ACCT5601RTP000000100020260430P",
            "RREM565600002ACCT5602ACH000000200020260430P",
            "RREM565600001ACCT5601RTP000000100020260430P",
            "RREM565600003ACCT5603WIR000000300020260430P",
            "RREM565600002ACCT5602ACH000000200020260430P",
        ])
        export_rows, summary, payload = run_all()

        assert [row["transaction_id"] for row in export_rows] == [
            "REM565600001",
            "REM565600002",
            "REM565600001",
            "REM565600003",
            "REM565600002",
        ]
        assert [tx["status"] for tx in payload["transactions"]] == [
            "ACCEPTED",
            "ACCEPTED",
            "DUPLICATE",
            "ACCEPTED",
            "DUPLICATE",
        ]
        assert payload["accepted_count"] == 3
        assert payload["accepted_amount_cents"] == 6000
        assert payload["rejected_count"] == 2
