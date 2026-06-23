
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


class TestMilestone3:
    def test_locked_row_stops_batch_without_advancing_past_retry_point(self, tmp_path):
        """SQLCODE -911 should persist a pending-lock report and prevent later details from being processed."""
        batch = "T3LOCKED"
        db = copy_seed(tmp_path, locked=True)
        inp = write_batch(tmp_path / "locked.fb", batch, [
            (1, "AC1000000001", "BAL", "+", 100, "GRP001", "LCKT0001"),
            (2, "ACLOCK000001", "BAL", "+", 700, "GRP777", "LCKT0002"),
            (3, "AC1000000002", "BAL", "+", 300, "GRP777", "LCKT0003"),
        ])
        out = tmp_path / "out"
        result = run_job(inp, db, out, batch=batch)
        assert result.returncode == 75, result.stderr + result.stdout
        state = load_db(db)
        assert state["master"]["AC1000000001"]["balance_cents"] == 100100
        assert state["master"]["ACLOCK000001"]["balance_cents"] == 125000
        assert state["master"]["AC1000000002"]["balance_cents"] == 200000
        assert state["checkpoint"][batch] == 1
        pending = json.loads((out / f"pending_locks_{batch}.json").read_text())
        assert pending and pending[0]["account"] == "ACLOCK000001"
        assert pending[0]["sqlcode"] == -911
        assert all(r["sqlcode"] != -911 for r in state.get("rejects", []))

    def test_cleared_lock_rerun_replays_locked_and_later_records_once(self, tmp_path):
        """After the external lock is cleared, rerun should apply the locked record and following records exactly once."""
        batch = "T3RETRYOK"
        db = copy_seed(tmp_path, locked=True)
        inp = write_batch(tmp_path / "retry.fb", batch, [
            (1, "AC1000000001", "BAL", "+", 100, "GRP001", "TRY00001"),
            (2, "ACLOCK000001", "BAL", "+", 700, "GRP777", "TRY00002"),
            (3, "AC1000000002", "BAL", "+", 300, "GRP777", "TRY00003"),
        ])
        first = run_job(inp, db, tmp_path / "out1", batch=batch)
        assert first.returncode == 75
        state = load_db(db)
        state["locks"] = {}
        Path(db).write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        second = run_job(inp, db, tmp_path / "out2", batch=batch)
        assert second.returncode == 0, second.stderr + second.stdout
        final = load_db(db)
        assert final["master"]["AC1000000001"]["balance_cents"] == 100100
        assert final["master"]["ACLOCK000001"]["balance_cents"] == 125700
        assert final["master"]["AC1000000002"]["balance_cents"] == 200300
        ledger_events = [r["event_id"] for r in final["ledger"] if r["batch_id"] == batch]
        assert sorted(ledger_events) == ["TRY00001", "TRY00002", "TRY00003"]
        assert final["checkpoint"][batch] == 3

    def test_retryable_lock_is_not_written_to_business_reject_file(self, tmp_path):
        """A novel runtime lock must be handled generically and kept out of business rejects."""
        batch = "T3NOREJ"
        db = copy_seed(tmp_path)
        state = load_db(db)
        state["locks"]["AC1000000003"] = "VERIFIER_UOW_9999"
        Path(db).write_text(json.dumps(state, indent=2, sort_keys=True) + "\n")
        inp = write_batch(tmp_path / "norej.fb", batch, [
            (1, "AC1000000003", "BAL", "+", 7, "GRP777", "NRE00001"),
        ])
        out = tmp_path / "out"
        result = run_job(inp, db, out, batch=batch)
        assert result.returncode == 75
        reject_path = out / f"rejects_{batch}.dat"
        assert reject_path.exists()
        assert reject_path.read_text() == ""
        summary = load_summary(out, batch)
        assert summary["status"] == "RETRYABLE_LOCK"
        assert summary["pending_locks"] == 1
        pending = json.loads((out / f"pending_locks_{batch}.json").read_text())
        assert pending[0]["account"] == "AC1000000003"
        assert pending[0]["lock_holder"] == "VERIFIER_UOW_9999"
