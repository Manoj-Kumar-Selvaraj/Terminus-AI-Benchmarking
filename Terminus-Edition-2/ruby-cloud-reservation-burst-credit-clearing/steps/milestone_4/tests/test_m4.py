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

class TestMilestone4:
    def test_abend_restart_commits_each_group_once_and_updates_checkpoint(self):
        """After an interrupted run, rerun must continue pending groups without duplicate commits."""
        write_base_files(
            [
                ["SRC-A", "ACC-A", "RES-A", "CPU", "40", "20260528140000", "ALLOCATED", "iad"],
                ["SRC-B", "ACC-B", "RES-B", "CPU", "30", "20260528140100", "ALLOCATED", "iad"],
                ["SRC-C", "ACC-C", "RES-C", "GPU", "50", "20260528140200", "ALLOCATED", "iad"],
            ],
            [
                ["CR-A", "SRC-A", "ACC-A", "RES-A", "ANY", "40", "20260528140500", "BURST", "iad"],
                ["CR-B", "SRC-B", "ACC-B", "RES-B", "ANY", "30", "20260528140600", "BURST", "iad"],
                ["CR-C", "SRC-C", "ACC-C", "RES-C", "ANY", "50", "20260528140700", "BURST", "iad"],
            ],
            [["RES-A", "20260528135900", "20260528143000", "OPEN"], ["RES-B", "20260528135900", "20260528143000", "OPEN"], ["RES-C", "20260528135900", "20260528143000", "OPEN"]],
            cycles=[
                ["GRP-A", "RES-A", "ACC-A", "iad", "2026-05", "CPU", "40", "false"],
                ["GRP-B", "RES-B", "ACC-B", "iad", "2026-05", "CPU", "30", "false"],
                ["GRP-C", "RES-C", "ACC-C", "iad", "2026-05", "GPU", "50", "false"],
            ],
            pools=[["iad", "CPU", "100"], ["iad", "GPU", "100"]],
            controls=[["iad", "CPU", "2026-05", "70"], ["iad", "GPU", "2026-05", "50"]],
            policies=[["iad", "CPU", "true", "1", "99", "5"], ["iad", "GPU", "true", "1", "99", "7"]],
        )
        first = run_batch(env={"ABEND_AFTER_GROUPS": "1"}, check=False)
        assert first.returncode == 17
        first_commits = read_csv(COMMITS)
        assert [row["group_id"] for row in first_commits] == ["GRP-A"]
        assert read_checkpoint()["committed_count"] == "1"
        run_batch()
        commits = read_csv(COMMITS)
        assert [row["group_id"] for row in commits] == ["GRP-A", "GRP-B", "GRP-C"]
        assert len({row["group_id"] for row in commits}) == 3
        assert read_checkpoint()["last_committed_group"] == "GRP-C"
        assert read_checkpoint()["committed_count"] == "3"
        pools = {(row["region"], row["sku_type"]): row for row in read_csv(POOLS)}
        assert pools[("iad", "CPU")]["committed_amount"] == "70"
        assert pools[("iad", "GPU")]["committed_amount"] == "50"

    def test_held_groups_are_never_written_to_commit_ledger(self):
        """A held group remains in the group report but is absent from the committed ledger."""
        write_base_files(
            [
                ["SRC-OK", "ACC-OK", "RES-OK", "CPU", "10", "20260528140000", "ALLOCATED", "iad"],
                ["SRC-HOLD", "ACC-H", "RES-H", "GPU", "99", "20260528140000", "ALLOCATED", "iad"],
            ],
            [
                ["CR-OK", "SRC-OK", "ACC-OK", "RES-OK", "ANY", "10", "20260528140500", "BURST", "iad"],
                ["CR-HOLD", "SRC-HOLD", "ACC-H", "RES-H", "ANY", "99", "20260528140500", "BURST", "iad"],
            ],
            [["RES-OK", "20260528135900", "20260528143000", "OPEN"], ["RES-H", "20260528135900", "20260528143000", "OPEN"]],
            cycles=[["GRP-OK", "RES-OK", "ACC-OK", "iad", "2026-05", "CPU", "10", "false"], ["GRP-HOLD", "RES-H", "ACC-H", "iad", "2026-05", "GPU", "99", "false"]],
            pools=[["iad", "CPU", "10"], ["iad", "GPU", "10"]],
            controls=[["iad", "CPU", "2026-05", "10"], ["iad", "GPU", "2026-05", "99"]],
            policies=[["iad", "CPU", "true", "1", "20", "1"], ["iad", "GPU", "true", "1", "100", "1"]],
        )
        run_batch()
        groups = {row["group_id"]: row for row in read_csv(GROUPS)}
        commits = read_csv(COMMITS)
        assert groups["GRP-HOLD"]["status"] == "HELD"
        assert groups["GRP-HOLD"]["reason"] == "CAPACITY_EXCEEDED"
        assert [row["group_id"] for row in commits] == ["GRP-OK"]
