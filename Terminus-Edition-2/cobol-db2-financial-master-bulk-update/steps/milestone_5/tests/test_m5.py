
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

def write_batch(path, batch, details, total=None, source="VERIFY"):
    if total is None:
        total = sum(d[4] if d[3] == "+" else -d[4] for d in details if d[2] == "BAL")
    sign = "-" if total < 0 else "+"
    lines = [header(batch, source=source)] + [detail(*d) for d in details] + [trailer(batch, len(details), sign, abs(total))]
    path.write_text("\n".join(lines) + "\n")
    return path

def copy_seed(tmp_path):
    db = tmp_path / "financial_master.json"
    shutil.copy(APP / "data/master_seed.json", db)
    return db

def run_job(batch_file, db_path, out_dir, control, batch):
    cmd = [str(APP / "bin/run_finbulk.sh"), "--input", str(batch_file), "--db", str(db_path), "--out", str(out_dir), "--batch", batch, "--control", str(control)]
    env = os.environ.copy()
    env["APP_DIR"] = str(APP)
    env["PYTHONPATH"] = f"{APP / 'tools'}" + ((":" + env["PYTHONPATH"]) if env.get("PYTHONPATH") else "")
    return subprocess.run(cmd, cwd=APP, env=env, text=True, capture_output=True)

def run_job_without_control(batch_file, db_path, out_dir, batch):
    cmd = [str(APP / "bin/run_finbulk.sh"), "--input", str(batch_file), "--db", str(db_path), "--out", str(out_dir), "--batch", batch]
    env = os.environ.copy()
    env["APP_DIR"] = str(APP)
    env["PYTHONPATH"] = f"{APP / 'tools'}" + ((":" + env["PYTHONPATH"]) if env.get("PYTHONPATH") else "")
    return subprocess.run(cmd, cwd=APP, env=env, text=True, capture_output=True)

def control(path, batch, total, source="VERIFY", count=1):
    path.write_text(json.dumps({"batch_id": batch, "business_date": "20260618", "source": source, "expected_detail_count": count, "expected_financial_total": total}))
    return path

def control_raw(path, payload):
    path.write_text(json.dumps(payload))
    return path

class TestMilestone5:
    def test_control_source_mismatch_fails_before_mutation(self, tmp_path):
        """A control manifest source mismatch must fail closed before balances or ledger state change."""
        batch = "T5SRCMIS"
        db = copy_seed(tmp_path)
        before = json.loads(db.read_text())
        inp = write_batch(tmp_path / "src.fb", batch, [(1, "AC1000000001", "BAL", "+", 10)])
        ctl = control(tmp_path / "control.json", batch, 10, source="OTHER")
        out = tmp_path / "out"
        result = run_job(inp, db, out, ctl, batch)
        after = json.loads(db.read_text())
        assert result.returncode != 0
        assert after["master"] == before["master"]
        assert after["ledger"] == before["ledger"]
        assert json.loads((tmp_path / "out" / f"summary_{batch}.json").read_text())["status"] == "FAILED_CLOSED"
        assert json.loads((out / f"summary_{batch}.json").read_text())["status"] == "FAILED_CLOSED"

    def test_control_business_date_mismatch_fails_before_mutation(self, tmp_path):
        """A control manifest date mismatch must fail before any DB state changes."""
        batch = "T5DATEMIS"
        db = copy_seed(tmp_path)
        before = json.loads(db.read_text())
        inp = write_batch(tmp_path / "date.fb", batch, [(1, "AC1000000001", "BAL", "+", 11)])
        ctl = control_raw(tmp_path / "control.json", {
            "batch_id": batch,
            "business_date": "20260617",
            "source": "VERIFY",
            "expected_detail_count": 1,
            "expected_financial_total": 11,
        })
        result = run_job(inp, db, tmp_path / "out", ctl, batch)
        after = json.loads(db.read_text())
        assert result.returncode != 0
        assert after["master"] == before["master"]
        assert after["ledger"] == before["ledger"]
        assert json.loads((tmp_path / "out" / f"summary_{batch}.json").read_text())["status"] == "FAILED_CLOSED"

    def test_control_detail_count_mismatch_fails_before_mutation(self, tmp_path):
        """A control manifest detail-count mismatch must fail before mutation."""
        batch = "T5COUNTMS"
        db = copy_seed(tmp_path)
        before = json.loads(db.read_text())
        inp = write_batch(tmp_path / "count.fb", batch, [(1, "AC1000000001", "BAL", "+", 12)])
        ctl = control(tmp_path / "control.json", batch, 12, count=2)
        result = run_job(inp, db, tmp_path / "out", ctl, batch)
        after = json.loads(db.read_text())
        assert result.returncode != 0
        assert after["master"] == before["master"]
        assert after["ledger"] == before["ledger"]
        assert json.loads((tmp_path / "out" / f"summary_{batch}.json").read_text())["status"] == "FAILED_CLOSED"

    def test_control_financial_total_mismatch_fails_before_mutation(self, tmp_path):
        """A control manifest financial-total mismatch must fail before mutation."""
        batch = "T5TOTLMIS"
        db = copy_seed(tmp_path)
        before = json.loads(db.read_text())
        inp = write_batch(tmp_path / "total.fb", batch, [(1, "AC1000000001", "BAL", "+", 13)])
        ctl = control(tmp_path / "control.json", batch, 99)
        result = run_job(inp, db, tmp_path / "out", ctl, batch)
        after = json.loads(db.read_text())
        assert result.returncode != 0
        assert after["master"] == before["master"]
        assert after["ledger"] == before["ledger"]

    def test_successful_control_total_record_is_persisted(self, tmp_path):
        """A successful controlled batch must persist settlement provenance and input hash."""
        batch = "T5SETTLE"
        db = copy_seed(tmp_path)
        inp = write_batch(tmp_path / "settle.fb", batch, [(1, "AC1000000001", "BAL", "+", 25)])
        ctl = control(tmp_path / "control.json", batch, 25)
        result = run_job(inp, db, tmp_path / "out", ctl, batch)
        state = json.loads(db.read_text())
        entry = state["control_totals"][batch]
        assert result.returncode == 0
        assert entry["status"] == "SETTLED"
        assert entry["detail_count"] == 1
        assert entry["financial_total"] == 25
        assert len(entry["input_sha256"]) == 64

    def test_same_batch_id_with_different_payload_is_rejected(self, tmp_path):
        """A previously settled batch id cannot be replayed with a different input hash."""
        batch = "T5DUPHASH"
        db = copy_seed(tmp_path)
        inp1 = write_batch(tmp_path / "one.fb", batch, [(1, "AC1000000001", "BAL", "+", 30)])
        ctl1 = control(tmp_path / "control1.json", batch, 30)
        assert run_job(inp1, db, tmp_path / "out1", ctl1, batch).returncode == 0
        before = json.loads(db.read_text())
        inp2 = write_batch(tmp_path / "two.fb", batch, [(1, "AC1000000001", "BAL", "+", 40)], total=40)
        ctl2 = control(tmp_path / "control2.json", batch, 40)
        result = run_job(inp2, db, tmp_path / "out2", ctl2, batch)
        after = json.loads(db.read_text())
        assert result.returncode != 0
        assert after["master"] == before["master"]
        assert after["control_totals"][batch]["input_sha256"] == before["control_totals"][batch]["input_sha256"]
        assert json.loads((tmp_path / "out2" / f"summary_{batch}.json").read_text())["status"] == "FAILED_CLOSED"

    def test_same_batch_id_with_same_payload_is_idempotent(self, tmp_path):
        """A settled batch may rerun with the same payload without double-applying balances."""
        batch = "T5IDEMP"
        db = copy_seed(tmp_path)
        inp = write_batch(tmp_path / "same.fb", batch, [(1, "AC1000000001", "BAL", "+", 31)])
        ctl = control(tmp_path / "control.json", batch, 31)
        assert run_job(inp, db, tmp_path / "out1", ctl, batch).returncode == 0
        before = json.loads(db.read_text())
        result = run_job(inp, db, tmp_path / "out2", ctl, batch)
        after = json.loads(db.read_text())
        assert result.returncode == 0
        assert after["master"] == before["master"]
        assert after["ledger"] == before["ledger"]
        assert after["control_totals"][batch]["input_sha256"] == before["control_totals"][batch]["input_sha256"]
        assert json.loads((tmp_path / "out2" / f"summary_{batch}.json").read_text())["skipped"] == 1

    def test_invocation_without_control_manifest_remains_compatible(self, tmp_path):
        """The legacy run command without --control must still update balances successfully."""
        batch = "T5NOCNTRL"
        db = copy_seed(tmp_path)
        inp = write_batch(tmp_path / "legacy.fb", batch, [(1, "AC1000000001", "BAL", "+", 21)])
        result = run_job_without_control(inp, db, tmp_path / "out", batch)
        state = json.loads(db.read_text())
        summary = json.loads((tmp_path / "out" / f"summary_{batch}.json").read_text())
        assert result.returncode == 0
        assert summary["status"] == "OK"
        assert summary["applied"] == 1
        assert state["master"]["AC1000000001"]["balance_cents"] == 100021
