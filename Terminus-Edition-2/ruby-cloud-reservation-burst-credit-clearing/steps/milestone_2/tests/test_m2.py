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

class TestMilestone2:
    def test_aliases_and_group_settlement_hold_incomplete_cycle(self):
        """Group settlement requires matched members, required SKUs, and expected amount reconciliation."""
        write_base_files(
            [
                ["SRC-CPU", "ACC-1", "RES-A", "CPU", "40", "20260528140000", "ALLOCATED", "iad"],
                ["SRC-GPU", "ACC-1", "RES-A", "GPU", "60", "20260528140100", "ALLOCATED", "iad"],
                ["SRC-MEM", "ACC-2", "RES-B", "MEM", "20", "20260528140200", "ALLOCATED", "iad"],
            ],
            [
                ["CR-CPU", "SRC-CPU", "ACC-1", "RES-A", "C", "40", "20260528140500", "BURST", "iad"],
                ["CR-GPU", "SRC-GPU", "ACC-1", "RES-A", "GPUF", "60", "20260528140600", "RECLAIM", "iad"],
                ["CR-MEM", "SRC-MEM", "ACC-2", "RES-B", "MEMORY", "20", "20260528140700", "CORRECT", "iad"],
            ],
            [["RES-A", "20260528135900", "20260528143000", "OPEN"], ["RES-B", "20260528135900", "20260528143000", "OPEN"]],
            cycles=[
                ["GRP-A", "RES-A", "ACC-1", "iad", "2026-05", "CPU|GPU", "100", "false"],
                ["GRP-B", "RES-B", "ACC-2", "iad", "2026-05", "MEM|GPU", "20", "false"],
            ],
        )
        run_batch()
        rows = read_csv(REPORT)
        groups = {row["group_id"]: row for row in read_csv(GROUPS)}
        assert [row["status"] for row in rows] == ["MATCHED", "MATCHED", "MATCHED"]
        assert [row["sku_type"] for row in rows] == ["CPU", "GPU", "MEM"]
        assert groups["GRP-A"]["status"] == "CLEARABLE"
        assert groups["GRP-A"]["matched_amount"] == "100"
        assert groups["GRP-B"]["status"] == "HELD"
        assert groups["GRP-B"]["reason"] == "MISSING_REQUIRED_SKU"

    def test_group_total_mismatch_and_member_unmatched_are_not_partially_cleared(self):
        """A group with one unmatched member or wrong aggregate total is held as a whole."""
        write_base_files(
            [
                ["SRC-1", "ACC", "RES-C", "CPU", "20", "20260528140000", "ALLOCATED", "dub"],
                ["SRC-2", "ACC", "RES-C", "GPU", "21", "20260528140100", "ALLOCATED", "dub"],
            ],
            [
                ["CR-1", "SRC-1", "ACC", "RES-C", "C", "20", "20260528140500", "BURST", "dub"],
                ["CR-2", "SRC-2", "ACC", "RES-C", "BAD", "21", "20260528140600", "BURST", "dub"],
            ],
            [["RES-C", "20260528135900", "20260528143000", "OPEN"]],
            cycles=[["GRP-C", "RES-C", "ACC", "dub", "2026-05", "CPU|GPU", "41", "false"]],
        )
        run_batch()
        groups = read_csv(GROUPS)
        assert groups == [{
            "group_id": "GRP-C", "reservation_id": "RES-C", "account_id": "ACC", "region": "dub", "billing_cycle": "2026-05",
            "required_sku_types": "CPU|GPU", "expected_amount": "41", "matched_amount": "20", "status": "HELD", "reason": "MEMBER_UNMATCHED"
        }]

    def test_group_total_mismatch_when_all_members_matched(self):
        """A fully matched group is held when matched_amount differs from expected_amount."""
        write_base_files(
            [
                ["SRC-1", "ACC", "RES-D", "CPU", "30", "20260528140000", "ALLOCATED", "dub"],
                ["SRC-2", "ACC", "RES-D", "GPU", "30", "20260528140100", "ALLOCATED", "dub"],
            ],
            [
                ["CR-1", "SRC-1", "ACC", "RES-D", "C", "30", "20260528140500", "BURST", "dub"],
                ["CR-2", "SRC-2", "ACC", "RES-D", "GPUF", "30", "20260528140600", "BURST", "dub"],
            ],
            [["RES-D", "20260528135900", "20260528143000", "OPEN"]],
            cycles=[["GRP-D", "RES-D", "ACC", "dub", "2026-05", "CPU|GPU", "100", "false"]],
        )
        run_batch()
        group = read_csv(GROUPS)[0]
        assert group["status"] == "HELD"
        assert group["reason"] == "GROUP_TOTAL_MISMATCH"
        assert group["matched_amount"] == "60"

    def test_no_matched_credits_holds_empty_cycle(self):
        """A configured cycle with no member credits is held with NO_MATCHED_CREDITS."""
        write_base_files(
            [["SRC-1", "ACC", "RES-E", "CPU", "10", "20260528140000", "ALLOCATED", "dub"]],
            [["CR-1", "SRC-1", "ACC", "RES-E", "C", "10", "20260528140500", "BURST", "dub"]],
            [["RES-E", "20260528135900", "20260528143000", "OPEN"]],
            cycles=[
                ["GRP-E", "RES-E", "ACC", "dub", "2026-05", "CPU", "10", "false"],
                ["GRP-F", "RES-F", "ACC", "dub", "2026-05", "CPU", "25", "false"],
            ],
        )
        run_batch()
        groups = {row["group_id"]: row for row in read_csv(GROUPS)}
        assert groups["GRP-E"]["status"] == "CLEARABLE"
        assert groups["GRP-F"]["status"] == "HELD"
        assert groups["GRP-F"]["reason"] == "NO_MATCHED_CREDITS"

    def test_cross_sku_credit_can_match_different_canonical_source_sku(self):
        """sku_type is not a pairwise key, so a GPU credit may consume a CPU source in group settlement."""
        write_base_files(
            [["SRC-CPU", "ACC", "RES-G", "CPU", "50", "20260528140000", "ALLOCATED", "dub"]],
            [["CR-GPU", "SRC-CPU", "ACC", "RES-G", "GPUF", "50", "20260528140500", "BURST", "dub"]],
            [["RES-G", "20260528135900", "20260528143000", "OPEN"]],
            cycles=[["GRP-G", "RES-G", "ACC", "dub", "2026-05", "CPU", "50", "false"]],
        )
        run_batch()
        rows = read_csv(REPORT)
        groups = read_csv(GROUPS)[0]
        assert rows[0]["status"] == "MATCHED"
        assert rows[0]["sku_type"] == "CPU"
        assert groups["status"] == "CLEARABLE"
