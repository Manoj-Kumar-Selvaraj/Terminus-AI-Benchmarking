"""Verifier tests for the license rebate reconciliation CLI."""

import csv
import json
import subprocess
from pathlib import Path

import pytest


APP = Path("/app")
LICENSES = APP / "data" / "licenses.csv"
REBATES = APP / "data" / "rebates.csv"
REPORT = APP / "out" / "rebate_report.csv"
SUMMARY = APP / "out" / "rebate_summary.json"
BIN = APP / "build" / "reconcile"
GO = Path("/usr/local/go/bin/go")


def build_program():
    """Compile the Go reconciliation CLI for the current source tree."""
    BIN.parent.mkdir(parents=True, exist_ok=True)
    go_cmd = str(GO) if GO.exists() else "go"
    subprocess.run([go_cmd, "build", "-o", str(BIN), "/app/cmd/reconcile"], check=True, cwd=APP, timeout=60)


@pytest.fixture(scope="session", autouse=True)
def compiled_binary():
    """Compile the Go reconciliation CLI once for all verifier tests."""
    build_program()
    assert BIN.exists()


def write_inputs(license_rows, rebate_rows):
    """Replace input CSV files with a test scenario and clear previous outputs."""
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    LICENSES.write_text("license_id,tenant_id,amount_cents,status,tier\n" + "\n".join(license_rows) + "\n")
    REBATES.write_text("license_id,tenant_id,amount_cents,tier\n" + "\n".join(rebate_rows) + "\n")
    REPORT.unlink(missing_ok=True)
    SUMMARY.unlink(missing_ok=True)


def run_program():
    """Run the CLI and return parsed report rows plus the summary object."""
    subprocess.run([str(BIN)], check=True, cwd=APP, timeout=60)
    with REPORT.open(newline="") as f:
        rows = list(csv.DictReader(f))
    return rows, json.loads(SUMMARY.read_text())


def test_business_rebate_matches_and_counts_positive_amount():
    """BUSINESS rebates should match licensed licenses and add positive cents to matched totals."""
    write_inputs(
        [
            "LIC20260401001,CUST1001,12500,LICENSED,STARTER",
            "LIC20260401002,CUST1002,9900,LICENSED,BUSINESS",
        ],
        [
            "LIC20260401001,CUST1001,12500,STARTER",
            "LIC20260401002,CUST1002,9900,BUSINESS",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert rows[1]["tier"] == "BUSINESS"
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 22400
    assert summary["unmatched_count"] == 0


def test_license_id_match_uses_full_identifier():
    """A rebate must not match a license that only shares the leading license prefix."""
    write_inputs(
        [
            "LIC777770001,CUST2001,3300,LICENSED,STARTER",
            "LIC777770002,CUST2001,3300,LICENSED,STARTER",
        ],
        [
            "LIC777770003,CUST2001,3300,STARTER",
            "LIC777770002,CUST2001,3300,STARTER",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
    assert rows[0]["tier"] == ""
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 3300
    assert summary["unmatched_amount_cents"] == 3300


def test_tenant_amount_status_and_tier_all_gate_matching():
    """Tenant, amount, licensed status, and allowed tier must all be satisfied."""
    write_inputs(
        [
            "LIC3001,CUST3001,1000,LICENSED,STARTER",
            "LIC3002,CUST3002,2000,LICENSED,BUSINESS",
            "LIC3003,CUST3003,3000,DRAFT,ENTERPRISE",
            "LIC3004,CUST3004,4000,LICENSED,TRIAL",
            "LIC3005,CUST3005,5000,LICENSED,ENTERPRISE",
        ],
        [
            "LIC3001,CUST9999,1000,STARTER",
            "LIC3002,CUST3002,2100,BUSINESS",
            "LIC3003,CUST3003,3000,ENTERPRISE",
            "LIC3004,CUST3004,4000,TRIAL",
            "LIC3005,CUST3005,5000,ENTERPRISE",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "MATCHED"]
    assert rows[-1]["tier"] == "ENTERPRISE"
    assert summary["matched_count"] == 1
    assert summary["matched_amount_cents"] == 5000
    assert summary["unmatched_count"] == 4
    assert summary["unmatched_amount_cents"] == 10100


def test_duplicate_rebates_do_not_reuse_consumed_license():
    """Only the earliest eligible rebate may consume a matching license."""
    write_inputs(
        [
            "LIC5551,CUST5551,7500,LICENSED,BUSINESS",
            "LIC5552,CUST5552,8800,LICENSED,STARTER",
        ],
        [
            "LIC5551,CUST5551,7500,BUSINESS",
            "LIC5551,CUST5551,7500,BUSINESS",
            "LIC5552,CUST5552,8800,STARTER",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "MATCHED"]
    assert rows[1]["tier"] == ""
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 16300
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 7500


def test_matching_trims_fields_and_normalizes_tier_status_case():
    """Matching should tolerate surrounding spaces and case differences in tier/status values."""
    write_inputs(
        [
            " LIC6601 , CUST6601 , 6100 , licensed , business ",
            "LIC6602,CUST6602,7200,LICENSED,enterprise",
        ],
        [
            "LIC6601,CUST6601, 6100 ,BUSINESS",
            " LIC6602 , CUST6602 ,7200, ENTERPRISE ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED"]
    assert [row["license_id"] for row in rows] == ["LIC6601", "LIC6602"]
    assert [row["tenant_id"] for row in rows] == ["CUST6601", "CUST6602"]
    assert [row["tier"] for row in rows] == ["BUSINESS", "ENTERPRISE"]
    assert summary["matched_count"] == 2
    assert summary["matched_amount_cents"] == 13300


def test_tier_mismatch_blocks_when_other_fields_align():
    """Canonical tier must match on both sides even when license_id, tenant_id, and amount align."""
    build_program()
    assert BIN.exists()
    write_inputs(
        ["LIC-TIER,TENANT-T,3000,LICENSED,STARTER"],
        ["LIC-TIER,TENANT-T,3000,BUSINESS"],
    )
    rows, summary = run_program()

    assert rows[0]["status"] == "UNMATCHED"
    assert rows[0]["tier"] == ""
    assert summary == {
        "matched_count": 0,
        "matched_amount_cents": 0,
        "unmatched_count": 1,
        "unmatched_amount_cents": 3000,
    }


def test_alias_trim_and_mixed_case_are_required():
    """Legacy aliases must normalize after trimming and case folding."""
    build_program()
    assert BIN.exists()
    write_inputs(
        [
            "LIC-CF1,CUST-CF,1000,LICENSED,STARTER",
            "LIC-CF2,CUST-CF,2000,LICENSED,BUSINESS",
            "LIC-CF3,CUST-CF,3000,LICENSED,ENTERPRISE",
        ],
        [
            "LIC-CF1,CUST-CF,1000, str ",
            "LIC-CF2,CUST-CF,2000, Bus",
            "LIC-CF3,CUST-CF,3000, ent ",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
    assert [row["tier"] for row in rows] == ["STARTER", "BUSINESS", "ENTERPRISE"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 6000,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }


def test_legacy_tier_aliases_match_and_emit_canonical_tiers():
    """Legacy STR, BUS, and ENT rebate tiers should match as STARTER, BUSINESS, and ENTERPRISE."""
    write_inputs(
        [
            "LIC7701,CUST7701,8800,LICENSED,BUSINESS",
            "LIC7702,CUST7702,9100,licensed,enterprise",
            "LIC7703,CUST7703,4200,LICENSED,STARTER",
            "LIC7704,CUST7704,3300,LICENSED,TRIAL",
        ],
        [
            "LIC7701,CUST7701,8800,bus",
            "LIC7702,CUST7702,9100,ENT",
            "LIC7703,CUST7703,4200,STR",
            "LIC7704,CUST7704,3300,trial",
        ],
    )
    rows, summary = run_program()

    assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED", "UNMATCHED"]
    assert [row["tier"] for row in rows] == ["BUSINESS", "ENTERPRISE", "STARTER", ""]
    assert summary["matched_count"] == 3
    assert summary["matched_amount_cents"] == 22100
    assert summary["unmatched_count"] == 1
    assert summary["unmatched_amount_cents"] == 3300


def test_report_schema_and_rebate_input_order_are_stable():
    """The report should use the required schema and preserve rebate input order."""
    write_inputs(
        [
            "LIC9001,CUST9001,100,LICENSED,STARTER",
            "LIC9002,CUST9002,200,LICENSED,BUSINESS",
            "LIC9003,CUST9003,300,LICENSED,ENTERPRISE",
        ],
        [
            "LIC9003,CUST9003,300,ENTERPRISE",
            "LIC9001,CUST9001,100,STARTER",
            "LIC9002,CUST9002,200,BUSINESS",
        ],
    )
    rows, summary = run_program()

    assert REPORT.read_text().splitlines()[0] == "license_id,tenant_id,tier,amount_cents,status"
    assert [row["license_id"] for row in rows] == ["LIC9003", "LIC9001", "LIC9002"]
    assert [row["amount_cents"] for row in rows] == ["300", "100", "200"]
    assert summary == {
        "matched_count": 3,
        "matched_amount_cents": 600,
        "unmatched_count": 0,
        "unmatched_amount_cents": 0,
    }
