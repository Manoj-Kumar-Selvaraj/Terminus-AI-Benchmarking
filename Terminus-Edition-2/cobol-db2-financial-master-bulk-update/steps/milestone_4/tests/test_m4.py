
import json
import os
import shutil
import subprocess
from pathlib import Path

APP = Path(os.environ.get("APP_DIR", "/app"))


def detail(seq, acct, op, sign, amount, group="GRP001", event=None):
    event = event or f"EVT{seq:05d}"
    return f"D{seq:06d}{acct:<12}{op:<3}{sign}{amount:012d}{group:<6}{event:<8}"


def header(batch, date="20260618", source="VERIFY"):
    return f"H{batch:<10}{date}{source:<8}"


def trailer(batch, count, sign, amount):
    return f"T{batch:<10}{count:06d}{sign}{amount:012d}"


def write_batch(path, batch, details, total=None):
    if total is None:
        total = sum(d[4] if d[3] == "+" else -d[4] for d in details if d[2] == "BAL")
    sign = "-" if total < 0 else "+"
    lines = [header(batch)] + [detail(*d) for d in details] + [trailer(batch, len(details), sign, abs(total))]
    path.write_text("\n".join(lines) + "\n")
    return path


def copy_seed(tmp_path, locked=False):
    src = APP / ("data/locks/online_posting_lock.json" if locked else "data/master_seed.json")
    db = tmp_path / "financial_master.json"
    shutil.copy(src, db)
    return db


def run_job(batch_file, db_path, out_dir, batch=None, abend_after=None):
    cmd = [str(APP / "bin/run_finbulk.sh")]
    if batch:
        cmd += ["--batch", batch]
    cmd += ["--input", str(batch_file), "--db", str(db_path), "--out", str(out_dir)]
    if abend_after is not None:
        cmd += ["--abend-after", str(abend_after)]
    env = os.environ.copy()
    env["APP_DIR"] = str(APP)
    env["PYTHONPATH"] = f"{APP / 'tools'}" + ((":" + env["PYTHONPATH"]) if env.get("PYTHONPATH") else "")
    return subprocess.run(cmd, cwd=APP, env=env, text=True, capture_output=True)


def load_db(db_path):
    return json.loads(Path(db_path).read_text())


def load_summary(out_dir, batch):
    return json.loads((Path(out_dir) / f"summary_{batch}.json").read_text())


class TestMilestone4:
    def test_limit_missing_master_rolls_back_without_applied_marker(self, tmp_path):
        """A +100 master miss on LIM must not mutate either table or create an applied marker."""
        batch = "T4MISSMST"
        db = copy_seed(tmp_path)
        before = load_db(db)
        inp = write_batch(tmp_path / "missing_master.fb", batch, [
            (1, "ACMISSING001", "LIM", "+", 300000, "GRP902", "MST00001"),
        ], total=0)
        out = tmp_path / "out"
        result = run_job(inp, db, out, batch=batch)
        assert result.returncode == 0, result.stderr + result.stdout
        after = load_db(db)
        assert after["master"] == before["master"]
        assert after["risk"] == before["risk"]
        assert f"{batch}|000001" not in after["applied_events"]
        rejects = [r for r in after["rejects"] if r["batch_id"] == batch]
        assert len(rejects) == 1
        assert rejects[0]["sqlcode"] == 100

    def test_limit_lock_timeout_rolls_back_and_remains_retryable(self, tmp_path):
        """A -911 on LIM must preserve both limits, stop retryably, and avoid business rejects."""
        batch = "T4LIMLOCK"
        db = copy_seed(tmp_path)
        before = load_db(db)
        before["locks"]["ACLIMIT00001"] = "VERIFY_LIMIT_UOW"
        Path(db).write_text(json.dumps(before, indent=2, sort_keys=True) + "\n")
        inp = write_batch(tmp_path / "limit_lock.fb", batch, [
            (1, "ACLIMIT00001", "LIM", "+", 750000, "GRP903", "LLK00001"),
        ], total=0)
        out = tmp_path / "out"
        result = run_job(inp, db, out, batch=batch)
        assert result.returncode == 75
        after = load_db(db)
        assert after["master"]["ACLIMIT00001"]["credit_limit_cents"] == 900000
        assert after["risk"]["ACLIMIT00001"]["exposure_limit_cents"] == 900000
        assert f"{batch}|000001" not in after["applied_events"]
        assert all(r["batch_id"] != batch for r in after["rejects"])
        assert load_summary(out, batch)["status"] == "RETRYABLE_LOCK"

    def test_limit_update_with_missing_risk_row_is_atomic_business_reject(self, tmp_path):
        """If the risk side returns -530, the master credit limit must remain unchanged and no applied marker is created."""
        batch = "T4NORISK"
        db = copy_seed(tmp_path)
        before = load_db(db)
        inp = write_batch(tmp_path / "norisk.fb", batch, [
            (1, "ACNORISK0001", "LIM", "+", 300000, "GRP901", "NRK00001"),
            (2, "AC1000000001", "BAL", "+", 10, "GRP001", "NRK00002"),
        ], total=10)
        out = tmp_path / "out"
        result = run_job(inp, db, out, batch=batch)
        assert result.returncode == 0, result.stderr + result.stdout
        after = load_db(db)
        assert after["master"]["ACNORISK0001"]["credit_limit_cents"] == before["master"]["ACNORISK0001"]["credit_limit_cents"]
        assert f"{batch}|000001" not in after["applied_events"]
        rejects = [r for r in after["rejects"] if r["batch_id"] == batch]
        assert len(rejects) == 1
        assert rejects[0]["sqlcode"] == -530
        assert after["master"]["AC1000000001"]["balance_cents"] == 100010

    def test_limit_below_balance_rolls_back_master_side(self, tmp_path):
        """A risk constraint failure must roll back the prior master-side limit update in the same logical detail."""
        batch = "T4LOWLIM"
        db = copy_seed(tmp_path)
        before = load_db(db)
        inp = write_batch(tmp_path / "lowlim.fb", batch, [
            (1, "ACLIMIT00001", "LIM", "+", 100000, "GRP900", "LOW00001"),
        ], total=0)
        result = run_job(inp, db, tmp_path / "out", batch=batch)
        assert result.returncode == 0
        after = load_db(db)
        assert after["master"]["ACLIMIT00001"]["credit_limit_cents"] == before["master"]["ACLIMIT00001"]["credit_limit_cents"]
        assert after["risk"]["ACLIMIT00001"]["exposure_limit_cents"] == before["risk"]["ACLIMIT00001"]["exposure_limit_cents"]
        assert f"{batch}|000001" not in after["applied_events"]

    def test_valid_limit_updates_master_and_risk_with_single_audit_marker(self, tmp_path):
        """A valid LIM detail should commit both tables together and create exactly one applied/audit marker."""
        batch = "T4VALID"
        db = copy_seed(tmp_path)
        inp = write_batch(tmp_path / "validlim.fb", batch, [
            (1, "ACLIMIT00001", "LIM", "+", 750000, "GRP900", "VAL00001"),
        ], total=0)
        result = run_job(inp, db, tmp_path / "out", batch=batch)
        assert result.returncode == 0, result.stderr + result.stdout
        state = load_db(db)
        assert state["master"]["ACLIMIT00001"]["credit_limit_cents"] == 750000
        assert state["risk"]["ACLIMIT00001"]["exposure_limit_cents"] == 750000
        audits = [a for a in state["audit"] if a["batch_id"] == batch and a["event_id"] == "VAL00001"]
        assert len(audits) == 1
        assert f"{batch}|000001" in state["applied_events"]
