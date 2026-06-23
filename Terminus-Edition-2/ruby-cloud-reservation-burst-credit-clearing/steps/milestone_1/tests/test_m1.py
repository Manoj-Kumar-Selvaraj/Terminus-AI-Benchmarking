import csv
import os
import shutil
import subprocess
from pathlib import Path

APP = Path("/app")
DATA = APP / "data"
CONFIG = APP / "config"
OUT = APP / "out"
REPORT = OUT / "seat_credit_report.csv"
SUMMARY = OUT / "seat_credit_summary.txt"
GROUPS = OUT / "reservation_credit_groups.csv"
POOLS = OUT / "capacity_pool_after.csv"
COMMITS = OUT / "credit_commit_ledger.csv"
CHECKPOINT = OUT / "restart_checkpoint.txt"


def write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def reset_outputs():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)


def write_base_files(sources, credits, windows, cycles=None, pools=None, controls=None, policies=None, aliases=None):
    write_csv(DATA / "seat_events.csv", ["event_id", "account_id", "reservation_id", "sku_type", "amount", "reserve_ts", "status", "region"], sources)
    write_csv(DATA / "credits.csv", ["credit_id", "event_id", "account_id", "reservation_id", "sku_type", "amount", "credit_ts", "reason", "region"], credits)
    write_csv(CONFIG / "windows.csv", ["reservation_id", "open_ts", "close_ts", "state"], windows)
    write_csv(CONFIG / "kind_aliases.csv", ["alias", "canonical"], aliases or [["C", "CPU"], ["GPUF", "GPU"], ["MEMORY", "MEM"]])
    write_csv(CONFIG / "reservation_cycles.csv", ["group_id", "reservation_id", "account_id", "region", "billing_cycle", "required_sku_types", "expected_amount", "allow_partial"], cycles or [])
    write_csv(DATA / "capacity_pools.csv", ["region", "sku_type", "capacity"], pools or [])
    write_csv(CONFIG / "control_totals.csv", ["region", "sku_type", "billing_cycle", "expected_committed_amount"], controls or [])
    write_csv(CONFIG / "sku_policy.csv", ["region", "sku_type", "enabled", "min_amount", "max_amount", "priority"], policies or [["*", "CPU", "true", "1", "999999", "10"], ["*", "GPU", "true", "1", "999999", "20"], ["*", "MEM", "true", "1", "999999", "15"]])
    reset_outputs()


def run_batch(env=None, check=True):
    env_vars = os.environ.copy()
    if env:
        env_vars.update(env)
    return subprocess.run(["ruby", "/app/app/reconcile.rb"], cwd=APP, env=env_vars, text=True, capture_output=True, timeout=60, check=check)


def read_csv(path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def read_summary():
    result = {}
    for line in SUMMARY.read_text().splitlines():
        key, value = line.split("=", 1)
        result[key] = int(value)
    return result


def read_checkpoint():
    result = {}
    for line in CHECKPOINT.read_text().splitlines():
        key, value = line.split("=", 1)
        result[key] = value
    return result

class TestMilestone1:
    def test_strict_identity_timestamp_window_and_consumption_gates(self):
        """Only exact identity/time/window/status/reason candidates match and a source is consumed once."""
        write_base_files(
            [
                ["SRC-A", "ACCT-1", "RES-1", "CPU", "10", "20260528140000", "ALLOCATED", "us-east-1"],
                ["SRC-B", "ACCT-2", "RES-1", "GPU", "20", "20260528140100", "BAD", "us-east-1"],
                ["SRC-C", "ACCT-3", "RES-1", "MEM", "30", "20260528140200", "ALLOCATED", "us-east-1"],
            ],
            [
                ["CR-A1", "SRC-A", "ACCT-1", "RES-1", "CPU", "10", "20260528140500", "BURST", "us-east-1"],
                ["CR-A2", "SRC-A", "ACCT-1", "RES-1", "CPU", "10", "20260528140600", "BURST", "us-east-1"],
                ["CR-B", "SRC-B", "ACCT-2", "RES-1", "GPU", "20", "20260528140500", "RECLAIM", "us-east-1"],
                ["CR-C", "SRC-C", "ACCT-3", "RES-1", "MEM", "30", "20260528140500", "CORRECT", "us-east-1"],
                ["CR-D", "SRC-A", "ACCT-1", "RES-1", "CPU", "10", "20260528143100", "BURST", "us-east-1"],
                ["CR-E", "SRC-A", "ACCT-1", "RES-1", "CPU", "10", "bad-time", "BURST", "us-east-1"],
            ],
            [["RES-1", "20260528135900", "20260528143000", "OPEN"]],
        )
        run_batch()
        rows = read_csv(REPORT)
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED", "UNMATCHED"]
        assert rows[0]["sku_type"] == "CPU"
        assert all(row["sku_type"] == "" for row in rows[1:])
        assert read_summary() == {"matched_count": 1, "matched_amount": 10, "unmatched_count": 5, "unmatched_amount": 80}

    def test_sku_is_not_pairwise_key_but_must_be_individually_canonical(self):
        """A GPU credit may select a CPU source, but alias and MEM tokens are not yet eligible."""
        write_base_files(
            [
                ["SRC-X", "A1", "R1", "CPU", "12", "20260528140000", "ALLOCATED", "r1"],
                ["SRC-Y", "A2", "R1", "MEM", "13", "20260528140000", "ALLOCATED", "r1"],
            ],
            [
                ["CR-X", "SRC-X", "A1", "R1", "GPU", "12", "20260528140100", "BURST", "r1"],
                ["CR-Y", "SRC-Y", "A2", "R1", "MEMORY", "13", "20260528140100", "BURST", "r1"],
            ],
            [["R1", "20260528135900", "20260528143000", "OPEN"]],
        )
        run_batch()
        rows = read_csv(REPORT)
        assert [row["status"] for row in rows] == ["MATCHED", "UNMATCHED"]
        assert [row["sku_type"] for row in rows] == ["CPU", ""]
        assert read_summary()["matched_amount"] == 12

    def test_prefix_event_id_overlap_does_not_match(self):
        """A source event_id that only shares a prefix with the credit must stay unmatched."""
        write_base_files(
            [["SRC-A1", "ACCT-1", "RES-1", "CPU", "10", "20260528140000", "ALLOCATED", "us-east-1"]],
            [["CR-A", "SRC-A", "ACCT-1", "RES-1", "CPU", "10", "20260528140500", "BURST", "us-east-1"]],
            [["RES-1", "20260528135900", "20260528143000", "OPEN"]],
        )
        run_batch()
        rows = read_csv(REPORT)
        assert rows[0]["status"] == "UNMATCHED"
        assert rows[0]["sku_type"] == ""

    def test_latest_reserve_ts_wins_then_earliest_source_row(self):
        """Among qualifying duplicate sources, latest reserve_ts wins and ties use earliest row order."""
        write_base_files(
            [
                ["E1", "A1", "R1", "CPU", "5", "20260528140000", "ALLOCATED", "r1"],
                ["E1", "A1", "R1", "GPU", "5", "20260528140200", "ALLOCATED", "r1"],
                ["E1", "A1", "R1", "CPU", "5", "20260528140200", "ALLOCATED", "r1"],
            ],
            [["CR-1", "E1", "A1", "R1", "GPU", "5", "20260528140500", "BURST", "r1"]],
            [["R1", "20260528135900", "20260528143000", "OPEN"]],
        )
        run_batch()
        rows = read_csv(REPORT)
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["sku_type"] == "GPU"

    def test_closed_window_blocks_matching(self):
        """Sources under CLOSED reservation windows remain ineligible even with valid timestamps."""
        write_base_files(
            [
                ["SRC-CLOSED", "A1", "R1", "CPU", "10", "20260528140000", "ALLOCATED", "r1"],
                ["SRC-OPEN", "A2", "R2", "CPU", "10", "20260528140000", "ALLOCATED", "r1"],
            ],
            [
                ["CR-CLOSED", "SRC-CLOSED", "A1", "R1", "CPU", "10", "20260528140500", "BURST", "r1"],
                ["CR-OPEN", "SRC-OPEN", "A2", "R2", "CPU", "10", "20260528140500", "BURST", "r1"],
            ],
            [
                ["R1", "20260528135900", "20260528143000", "CLOSED"],
                ["R2", "20260528135900", "20260528143000", "OPEN"],
            ],
        )
        run_batch()
        rows = read_csv(REPORT)
        assert [row["status"] for row in rows] == ["UNMATCHED", "MATCHED"]
        assert [row["sku_type"] for row in rows] == ["", "CPU"]
