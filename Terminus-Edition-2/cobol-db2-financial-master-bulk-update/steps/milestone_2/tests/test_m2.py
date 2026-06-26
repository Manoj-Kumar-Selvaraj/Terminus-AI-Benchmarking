
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


class TestMilestone2:
    def test_abend_rerun_does_not_duplicate_committed_side_effects(self, tmp_path):
        """Records committed before a simulated ABEND should be skipped on rerun without duplicate ledger/audit rows."""
        batch = "T2REPLAY1"
        db = copy_seed(tmp_path)
        inp = write_batch(tmp_path / "restart.fb", batch, [
            (1, "AC1000000001", "BAL", "+", 250, "GRP001", "RPL00001"),
            (2, "AC1000000002", "BAL", "-", 500, "GRP001", "RPL00002"),
            (3, "AC1000000003", "RAT", "+", 390, "GRP002", "RPL00003"),
        ])
        out1 = tmp_path / "out1"
        first = run_job(inp, db, out1, batch=batch, abend_after=2)
        assert first.returncode == 66
        mid = load_db(db)
        assert mid["checkpoint"][batch] == 2
        ae = mid["applied_events"]
        assert f"{batch}|000001" in ae
        assert ae[f"{batch}|000001"]["event_id"] == "RPL00001"
        assert ae[f"{batch}|000001"]["account"] == "AC1000000001"
        assert ae[f"{batch}|000001"]["op"] == "BAL"
        assert f"{batch}|000002" in ae
        assert ae[f"{batch}|000002"]["event_id"] == "RPL00002"
        assert ae[f"{batch}|000002"]["account"] == "AC1000000002"
        assert ae[f"{batch}|000002"]["op"] == "BAL"
        assert f"{batch}|000003" not in ae
        assert mid["master"]["AC1000000001"]["balance_cents"] == 100250
        assert mid["master"]["AC1000000002"]["balance_cents"] == 199500
        assert mid["master"]["AC1000000003"]["rate_bp"] == 325
        assert sorted(row["event_id"] for row in mid["ledger"] if row["batch_id"] == batch) == ["RPL00001", "RPL00002"]
        assert sorted(row["event_id"] for row in mid["audit"] if row["batch_id"] == batch) == ["RPL00001", "RPL00002"]
        assert load_summary(out1, batch)["status"] == "SIMULATED_ABEND"
        out2 = tmp_path / "out2"
        second = run_job(inp, db, out2, batch=batch)
        assert second.returncode == 0, second.stderr + second.stdout
        state = load_db(db)
        assert state["master"]["AC1000000001"]["balance_cents"] == 100250
        assert state["master"]["AC1000000002"]["balance_cents"] == 199500
        assert state["master"]["AC1000000003"]["rate_bp"] == 390
        ledger_events = [row["event_id"] for row in state["ledger"] if row["batch_id"] == batch]
        assert sorted(ledger_events) == ["RPL00001", "RPL00002"]
        audit_events = [row["event_id"] for row in state["audit"] if row["batch_id"] == batch]
        assert sorted(audit_events) == ["RPL00001", "RPL00002", "RPL00003"]
        assert state["checkpoint"][batch] == 3
        final_ae = state["applied_events"]
        assert f"{batch}|000003" in final_ae
        assert final_ae[f"{batch}|000003"]["event_id"] == "RPL00003"
        assert final_ae[f"{batch}|000003"]["account"] == "AC1000000003"
        assert final_ae[f"{batch}|000003"]["op"] == "RAT"

    def test_duplicate_sequence_in_same_batch_is_skipped_not_reapplied(self, tmp_path):
        """A repeated batch/sequence event should be considered already applied and must not double-post balance or ledger."""
        batch = "T2DUPSEQ"
        db = copy_seed(tmp_path)
        inp = write_batch(tmp_path / "dups.fb", batch, [
            (1, "AC1000000001", "BAL", "+", 100, "GRP001", "DUP00001"),
            (1, "AC1000000001", "BAL", "+", 100, "GRP001", "DUP00001"),
            (2, "AC1000000002", "RAT", "+", 415, "GRP002", "DUP00002"),
        ])
        out = tmp_path / "out"
        result = run_job(inp, db, out, batch=batch)
        assert result.returncode == 0
        state = load_db(db)
        assert state["master"]["AC1000000001"]["balance_cents"] == 100100
        assert state["master"]["AC1000000002"]["rate_bp"] == 415
        assert [row["event_id"] for row in state["ledger"] if row["batch_id"] == batch] == ["DUP00001"]
        audit_events = sorted(
            row["event_id"] for row in state["audit"] if row["batch_id"] == batch
        )
        assert audit_events == ["DUP00001", "DUP00002"]
        summary = load_summary(out, batch)
        assert summary["skipped"] == 1

    def test_completed_batch_rerun_leaves_state_stable(self, tmp_path):
        """Running a completed batch a second time should leave balances, audit, ledger, and checkpoint unchanged."""
        batch = "T2STABLE"
        db = copy_seed(tmp_path)
        inp = write_batch(tmp_path / "stable.fb", batch, [
            (1, "AC1000000002", "BAL", "+", 321, "GRP001", "STB00001"),
            (2, "AC1000000003", "RAT", "+", 388, "GRP002", "STB00002"),
        ])
        first = run_job(inp, db, tmp_path / "out1", batch=batch)
        assert first.returncode == 0
        before = load_db(db)
        second = run_job(inp, db, tmp_path / "out2", batch=batch)
        assert second.returncode == 0
        after = load_db(db)
        assert after == before
        assert load_summary(tmp_path / "out2", batch)["skipped"] == 2
