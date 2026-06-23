
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


class TestMilestone1:
    def test_missing_master_row_is_rejected_without_halting_later_commits(self, tmp_path):
        """A +100 master miss should create a reject and still allow later valid DB2 updates to commit."""
        batch = "T1MISS100"
        db = copy_seed(tmp_path)
        inp = write_batch(tmp_path / "m1_missing.fb", batch, [
            (1, "AC1000000001", "BAL", "+", 1250, "GRP001", "M1A00001"),
            (2, "ACMISSING001", "BAL", "+", 999, "GRP001", "M1A00002"),
            (3, "AC1000000002", "RAT", "+", 425, "GRP002", "M1A00003"),
        ])
        out = tmp_path / "out"
        result = run_job(inp, db, out, batch=batch)
        assert result.returncode == 0, result.stderr + result.stdout
        state = load_db(db)
        summary = load_summary(out, batch)
        assert state["master"]["AC1000000001"]["balance_cents"] == 101250
        assert state["master"]["AC1000000002"]["rate_bp"] == 425
        ledger = [entry for entry in state["ledger"] if entry["batch_id"] == batch]
        assert len(ledger) == 1
        assert ledger[0]["account"] == "AC1000000001"
        assert ledger[0]["delta_cents"] == 1250
        audit = [entry for entry in state["audit"] if entry["batch_id"] == batch]
        assert len(audit) == 2
        assert {entry["op"] for entry in audit} == {"BAL", "RAT"}
        rejects = [r for r in state["rejects"] if r["batch_id"] == batch]
        assert len(rejects) == 1
        assert rejects[0]["account"] == "ACMISSING001"
        assert rejects[0]["sqlcode"] == 100
        assert summary["applied"] == 2
        assert summary["rejected"] == 1

    def test_trailer_mismatch_fails_closed_before_any_mutation(self, tmp_path):
        """A malformed control total must stop the batch before balances, checkpoints, ledger, or audit are changed."""
        batch = "T1BADTRL"
        db = copy_seed(tmp_path)
        before = load_db(db)
        inp = tmp_path / "bad_trailer.fb"
        inp.write_text("\n".join([
            header(batch),
            detail(1, "AC1000000001", "BAL", "+", 100, "GRP001", "BAD00001"),
            detail(2, "AC1000000002", "BAL", "+", 200, "GRP001", "BAD00002"),
            trailer(batch, 2, "+", 999),
        ]) + "\n")
        out = tmp_path / "out"
        result = run_job(inp, db, out, batch=batch)
        assert result.returncode != 0
        after = load_db(db)
        assert after["master"] == before["master"]
        assert after["ledger"] == before["ledger"]
        assert after["audit"] == before["audit"]
        assert after["checkpoint"] == before["checkpoint"]
        summary = load_summary(out, batch)
        assert summary["status"] == "FAILED_CLOSED"

    def test_trailer_count_mismatch_fails_closed_before_any_mutation(self, tmp_path):
        """A detail-count mismatch must fail closed even when the BAL financial total is correct."""
        batch = "T1BADCNT"
        db = copy_seed(tmp_path)
        before = load_db(db)
        inp = tmp_path / "bad_count.fb"
        inp.write_text("\n".join([
            header(batch),
            detail(1, "AC1000000001", "BAL", "+", 100, "GRP001", "CNT00001"),
            detail(2, "AC1000000002", "BAL", "+", 200, "GRP001", "CNT00002"),
            trailer(batch, 3, "+", 300),
        ]) + "\n")
        out = tmp_path / "out"
        result = run_job(inp, db, out, batch=batch)
        assert result.returncode != 0
        after = load_db(db)
        assert after["master"] == before["master"]
        assert after["ledger"] == before["ledger"]
        assert after["audit"] == before["audit"]
        assert after["checkpoint"] == before["checkpoint"]
        summary = load_summary(out, batch)
        assert summary["status"] == "FAILED_CLOSED"

    def test_malformed_detail_fields_fail_closed_before_any_mutation(self, tmp_path):
        """Malformed fixed-width detail fields must be rejected before DB state changes."""
        batch = "T1BADDTL"
        db = copy_seed(tmp_path)
        before = load_db(db)
        malformed_detail = "D00X001" + f"{'AC1000000001':<12}" + "BAL" + "+" + f"{100:012d}" + f"{'GRP001':<6}" + f"{'BADF0001':<8}"
        inp = tmp_path / "bad_detail.fb"
        inp.write_text("\n".join([
            header(batch),
            detail(1, "AC1000000001", "BAL", "+", 500, "GRP001", "GOOD0001"),
            malformed_detail,
            trailer(batch, 2, "+", 600),
        ]) + "\n")
        out = tmp_path / "out"
        result = run_job(inp, db, out, batch=batch)
        assert result.returncode != 0
        after = load_db(db)
        assert after["master"] == before["master"]
        assert after["ledger"] == before["ledger"]
        assert after["audit"] == before["audit"]
        assert after["checkpoint"] == before["checkpoint"]
        assert after["master"]["AC1000000001"]["balance_cents"] == before["master"]["AC1000000001"]["balance_cents"]
        summary = load_summary(out, batch)
        assert summary["status"] == "FAILED_CLOSED"

    def test_batch_id_mismatch_fails_closed_before_any_mutation(self, tmp_path):
        """Header and trailer batch IDs must match before any DB mutation."""
        db = copy_seed(tmp_path)
        before = load_db(db)
        inp = tmp_path / "mismatch.fb"
        inp.write_text("\n".join([
            header("BATCH_AAA"),
            detail(1, "AC1000000001", "BAL", "+", 100, "GRP001", "MIS00001"),
            trailer("BATCH_BBB", 1, "+", 100),
        ]) + "\n")
        out = tmp_path / "out"
        result = run_job(inp, db, out, batch="BATCH_AAA")
        assert result.returncode != 0
        after = load_db(db)
        assert after["master"] == before["master"]
        assert after["ledger"] == before["ledger"]
        assert after["audit"] == before["audit"]
        assert after["checkpoint"] == before["checkpoint"]
        summary = load_summary(out, "BATCH_AAA")
        assert summary["status"] == "FAILED_CLOSED"

    def test_reject_file_uses_documented_fixed_width_contract(self, tmp_path):
        """Reject output should be fixed-width and no legacy success marker should be used as a shortcut."""
        batch = "T1REJECTS"
        db = copy_seed(tmp_path)
        inp = write_batch(tmp_path / "rejects.fb", batch, [
            (1, "ACMISSING001", "BAL", "+", 1, "GRP001", "REJ00001"),
            (2, "AC1000000003", "RAT", "+", 399, "GRP002", "REJ00002"),
        ])
        out = tmp_path / "out"
        result = run_job(inp, db, out, batch=batch)
        assert result.returncode == 0
        reject_path = out / f"rejects_{batch}.dat"
        assert reject_path.exists()
        line = reject_path.read_text().splitlines()[0]
        assert line[0] == "R"
        assert line[1:7] == "000001"
        assert line[7:19] == "ACMISSING001"
        assert line[19:24] == "+0100"
        assert len(line[24:].rstrip()) > 0
        assert len(line) == 56
        assert not (out / "legacy_success.txt").exists()
