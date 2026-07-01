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


def copy_seed(tmp_path, locked=False):
    src = APP / ("data/locks/online_posting_lock.json" if locked else "data/master_seed.json")
    db = tmp_path / "financial_master.json"
    shutil.copy(src, db)
    return db


def run_job(batch_file, db_path, out_dir, control=None, batch=None, abend_after=None, abend_after_lim_master=False):
    cmd = [str(APP / "bin/run_finbulk.sh"), "--input", str(batch_file), "--db", str(db_path), "--out", str(out_dir)]
    if batch:
        cmd += ["--batch", batch]
    if control is not None:
        cmd += ["--control", str(control)]
    if abend_after is not None:
        cmd += ["--abend-after", str(abend_after)]
    if abend_after_lim_master:
        cmd += ["--abend-after-lim-master"]
    env = os.environ.copy()
    env["APP_DIR"] = str(APP)
    env["PYTHONPATH"] = f"{APP / 'tools'}" + ((":" + env["PYTHONPATH"]) if env.get("PYTHONPATH") else "")
    return subprocess.run(cmd, cwd=APP, env=env, text=True, capture_output=True)


def run_close(date, db_path, out_dir):
    cmd = [
        str(APP / "bin/run_finbulk.sh"),
        "--close", str(date),
        "--db", str(db_path),
        "--out", str(out_dir),
    ]
    env = os.environ.copy()
    env["APP_DIR"] = str(APP)
    return subprocess.run(cmd, cwd=APP, env=env, text=True, capture_output=True)


def run_job_without_control(batch_file, db_path, out_dir, batch):
    return run_job(batch_file, db_path, out_dir, batch=batch)


def load_db(db_path):
    return json.loads(Path(db_path).read_text())


def load_summary(out_dir, batch):
    return json.loads((Path(out_dir) / f"summary_{batch}.json").read_text())


def control(path, batch, total, source="VERIFY", count=1, date="20260618", prior_batch_id=None):
    payload = {
        "batch_id": batch,
        "business_date": date,
        "source": source,
        "expected_detail_count": count,
        "expected_financial_total": total,
    }
    if prior_batch_id is not None:
        payload["prior_batch_id"] = prior_batch_id
    path.write_text(json.dumps(payload))
    return path


def control_raw(path, payload):
    path.write_text(json.dumps(payload))
    return path


IMMUTABLE_KEYS = (
    "master", "risk", "ledger", "audit", "checkpoint",
    "applied_events", "pending_locks", "rejects", "control_totals", "chain_index",
)

EMPTY_DB_DEFAULTS = {
    "master": {},
    "risk": {},
    "ledger": [],
    "audit": [],
    "checkpoint": {},
    "applied_events": {},
    "pending_locks": [],
    "rejects": [],
    "control_totals": {},
    "chain_index": {},
}


def assert_db_unchanged(before, after):
    for key in IMMUTABLE_KEYS:
        assert after.get(key, EMPTY_DB_DEFAULTS[key]) == before.get(key, EMPTY_DB_DEFAULTS[key]), key


def assert_failed_closed_outputs(out, batch):
    summary = json.loads((out / f"summary_{batch}.json").read_text())
    assert summary["status"] == "FAILED_CLOSED"
    assert (out / f"rejects_{batch}.dat").is_file()
    assert (out / f"pending_locks_{batch}.json").is_file()
    json.loads((out / f"pending_locks_{batch}.json").read_text())

class TestBatchValidationAndRejects:
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
        applied = state.get("applied_events", {})
        assert f"{batch}|000002" not in applied
        assert state["checkpoint"].get(batch) == 3
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
        assert "MASTER" in line[24:56] or "NOT_FOUND" in line[24:56]
        assert len(line) == 56
        assert not (out / "legacy_success.txt").exists()


class TestRestartAndIdempotency:
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


class TestRetryableLockHandling:
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


class TestAtomicLimitUpdates:
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
        rejects = [r for r in after["rejects"] if r["batch_id"] == batch]
        assert len(rejects) == 1
        assert rejects[0]["sqlcode"] == -530

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


class TestControlManifestAndSettlement:
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
        assert_db_unchanged(before, after)
        assert_failed_closed_outputs(out, batch)

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
        assert_db_unchanged(before, after)
        assert_failed_closed_outputs(tmp_path / "out", batch)

    def test_control_batch_id_mismatch_fails_before_mutation(self, tmp_path):
        """A control manifest batch id mismatch must fail closed before mutation."""
        batch = "T5BATCHMS"
        db = copy_seed(tmp_path)
        before = json.loads(db.read_text())
        inp = write_batch(tmp_path / "batch.fb", batch, [(1, "AC1000000001", "BAL", "+", 15)])
        ctl = control_raw(tmp_path / "control.json", {
            "batch_id": "OTHERBATCH",
            "business_date": "20260618",
            "source": "VERIFY",
            "expected_detail_count": 1,
            "expected_financial_total": 15,
        })
        result = run_job(inp, db, tmp_path / "out", ctl, batch)
        after = json.loads(db.read_text())
        assert result.returncode != 0
        assert_db_unchanged(before, after)
        assert_failed_closed_outputs(tmp_path / "out", batch)

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
        assert_db_unchanged(before, after)
        assert_failed_closed_outputs(tmp_path / "out", batch)

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
        assert_db_unchanged(before, after)
        assert_failed_closed_outputs(tmp_path / "out", batch)

    def test_malformed_control_manifest_fails_closed(self, tmp_path):
        """An unparseable control manifest must fail closed before any DB mutation."""
        batch = "T5BADCTL"
        db = copy_seed(tmp_path)
        before = json.loads(db.read_text())
        inp = write_batch(tmp_path / "badctl.fb", batch, [(1, "AC1000000001", "BAL", "+", 14)])
        ctl = tmp_path / "control.json"
        ctl.write_text("not valid json {{{")
        out = tmp_path / "out"
        result = run_job(inp, db, out, ctl, batch)
        after = json.loads(db.read_text())
        assert result.returncode != 0
        assert_db_unchanged(before, after)
        assert_failed_closed_outputs(out, batch)

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
        assert state["master"]["AC1000000001"]["balance_cents"] == 100025
        ledger = [row for row in state["ledger"] if row["batch_id"] == batch]
        assert len(ledger) == 1
        assert ledger[0]["account"] == "AC1000000001"
        assert ledger[0]["delta_cents"] == 25
        audit = [row for row in state["audit"] if row["batch_id"] == batch]
        assert len(audit) == 1
        assert audit[0]["op"] == "BAL"
        summary = json.loads((tmp_path / "out" / f"summary_{batch}.json").read_text())
        reject_path = tmp_path / "out" / f"rejects_{batch}.dat"
        pending_path = tmp_path / "out" / f"pending_locks_{batch}.json"
        assert reject_path.is_file()
        assert reject_path.read_text() == ""
        assert pending_path.is_file()
        assert json.loads(pending_path.read_text()) == []
        assert summary["applied"] == 1
        assert entry["status"] == "SETTLED"
        assert entry["detail_count"] == 1
        assert entry["financial_total"] == 25
        assert entry["batch_id"] == batch
        assert entry["business_date"] == "20260618"
        assert entry["source"] == "VERIFY"
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
        assert_db_unchanged(before, after)
        assert_failed_closed_outputs(tmp_path / "out2", batch)

    def test_same_batch_id_with_same_payload_is_idempotent(self, tmp_path):
        """A settled batch may rerun with the same payload without double-applying balances."""
        batch = "T5IDEMP"
        db = copy_seed(tmp_path)
        inp = write_batch(tmp_path / "same.fb", batch, [(1, "AC1000000001", "BAL", "+", 31)])
        ctl = control(tmp_path / "control.json", batch, 31)
        assert run_job(inp, db, tmp_path / "out1", ctl, batch).returncode == 0
        first_state = json.loads(db.read_text())
        assert first_state["master"]["AC1000000001"]["balance_cents"] == 100031
        before = first_state
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


class TestSettlementChainAndClose:
    def test_controlled_runs_persist_chain_fields_and_idempotent_rerun_keeps_index_stable(self, tmp_path):
        batch1 = "T6CHAIN01"
        batch2 = "T6CHAIN02"
        db = copy_seed(tmp_path)

        inp1 = write_batch(tmp_path / "chain1.fb", batch1, [
            (1, "AC1000000001", "BAL", "+", 25, "GRP001", "CHN00001"),
            (2, "AC1000000002", "BAL", "-", 5, "GRP001", "CHN00002"),
        ], total=20)
        ctl1 = control(tmp_path / "control1.json", batch1, 20, count=2)
        first = run_job(inp1, db, tmp_path / "out1", ctl1, batch1)
        assert first.returncode == 0, first.stderr + first.stdout

        state1 = load_db(db)
        entry1 = state1["control_totals"][batch1]
        assert entry1["prior_chain_sha256"] == "0" * 64
        assert entry1["prior_batch_id"] is None
        assert len(entry1["chain_sha256"]) == 64
        assert state1["chain_index"]["20260618"] == [batch1]

        inp2 = write_batch(tmp_path / "chain2.fb", batch2, [
            (1, "AC1000000003", "BAL", "+", 40, "GRP001", "CHN00003"),
        ], total=40)
        ctl2 = control(tmp_path / "control2.json", batch2, 40, count=1, prior_batch_id=batch1)
        second = run_job(inp2, db, tmp_path / "out2", ctl2, batch2)
        assert second.returncode == 0, second.stderr + second.stdout

        state2 = load_db(db)
        entry2 = state2["control_totals"][batch2]
        assert entry2["prior_batch_id"] == batch1
        assert entry2["prior_chain_sha256"] == entry1["chain_sha256"]
        assert len(entry2["chain_sha256"]) == 64
        assert state2["chain_index"]["20260618"] == [batch1, batch2]

        before_rerun = json.loads(json.dumps(state2))
        ctl2_rerun = control(tmp_path / "control2_rerun.json", batch2, 40, count=1)
        rerun = run_job(inp2, db, tmp_path / "out3", ctl2_rerun, batch2)
        assert rerun.returncode == 0, rerun.stderr + rerun.stdout
        after_rerun = load_db(db)
        assert after_rerun["chain_index"]["20260618"] == [batch1, batch2]
        assert after_rerun["control_totals"][batch2] == before_rerun["control_totals"][batch2]

    def test_prior_batch_dependency_mismatch_fails_closed_without_mutation(self, tmp_path):
        batch1 = "T6DEP001"
        batch2 = "T6DEP002"
        db = copy_seed(tmp_path)

        inp1 = write_batch(tmp_path / "dep1.fb", batch1, [
            (1, "AC1000000001", "BAL", "+", 10, "GRP001", "DEP00001"),
        ], total=10)
        ctl1 = control(tmp_path / "control1.json", batch1, 10)
        assert run_job(inp1, db, tmp_path / "out1", ctl1, batch1).returncode == 0

        before = load_db(db)
        inp2 = write_batch(tmp_path / "dep2.fb", batch2, [
            (1, "AC1000000002", "BAL", "+", 11, "GRP001", "DEP00002"),
        ], total=11)
        ctl2 = control(tmp_path / "control2.json", batch2, 11, prior_batch_id="WRONGTIP")
        out = tmp_path / "out2"
        result = run_job(inp2, db, out, ctl2, batch2)
        assert result.returncode != 0
        assert_failed_closed_outputs(out, batch2)
        summary = load_summary(out, batch2)
        assert "UNMET_DEPENDENCY" in summary.get("error", "")
        after = load_db(db)
        assert_db_unchanged(before, after)

    def test_same_batch_fencing_lock_contention_returns_batch_busy(self, tmp_path):
        import fcntl

        batch = "T6LOCKBZY"
        db = copy_seed(tmp_path)
        inp = write_batch(tmp_path / "busy.fb", batch, [
            (1, "AC1000000001", "BAL", "+", 9, "GRP001", "BSY00001"),
        ], total=9)
        lock_path = Path(db).parent / f".lock_{batch}"
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(lock_path, "w", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            before = load_db(db)
            out = tmp_path / "out"
            result = run_job(inp, db, out, batch=batch)
            assert result.returncode == 73, result.stderr + result.stdout
            summary = load_summary(out, batch)
            assert summary["status"] == "BATCH_BUSY"
            assert (out / f"rejects_{batch}.dat").read_text() == ""
            assert json.loads((out / f"pending_locks_{batch}.json").read_text()) == []
            after = load_db(db)
            assert_db_unchanged(before, after)

    def test_mid_lim_abend_rolls_back_master_half_and_rerun_applies_once(self, tmp_path):
        batch = "T6LIMABD"
        db = copy_seed(tmp_path)
        before = load_db(db)
        inp = write_batch(tmp_path / "lim_abend.fb", batch, [
            (1, "ACLIMIT00001", "LIM", "+", 700000, "GRP900", "LIM00001"),
            (2, "AC1000000001", "BAL", "+", 5, "GRP001", "LIM00002"),
        ], total=5)

        first = run_job(inp, db, tmp_path / "out1", batch=batch, abend_after_lim_master=True)
        assert first.returncode == 66
        mid = load_db(db)
        assert mid["master"]["ACLIMIT00001"]["credit_limit_cents"] == before["master"]["ACLIMIT00001"]["credit_limit_cents"]
        assert mid["risk"]["ACLIMIT00001"]["exposure_limit_cents"] == before["risk"]["ACLIMIT00001"]["exposure_limit_cents"]
        assert f"{batch}|000001" not in mid["applied_events"]
        assert f"{batch}|000002" not in mid["applied_events"]
        assert load_summary(tmp_path / "out1", batch)["status"] == "SIMULATED_ABEND"

        second = run_job(inp, db, tmp_path / "out2", batch=batch)
        assert second.returncode == 0, second.stderr + second.stdout
        final = load_db(db)
        assert final["master"]["ACLIMIT00001"]["credit_limit_cents"] == 700000
        assert final["risk"]["ACLIMIT00001"]["exposure_limit_cents"] == 700000
        assert final["master"]["AC1000000001"]["balance_cents"] == before["master"]["AC1000000001"]["balance_cents"] + 5
        assert f"{batch}|000001" in final["applied_events"]
        assert f"{batch}|000002" in final["applied_events"]

    def test_close_mode_writes_closed_summary_and_contract_gl_feed(self, tmp_path):
        batch1 = "T6CLOSE01"
        batch2 = "T6CLOSE02"
        db = copy_seed(tmp_path)

        inp1 = write_batch(tmp_path / "close1.fb", batch1, [
            (1, "AC1000000001", "BAL", "+", 20, "GRP001", "CLS00001"),
            (2, "AC1000000002", "BAL", "-", 5, "GRP001", "CLS00002"),
        ], total=15)
        ctl1 = control(tmp_path / "control1.json", batch1, 15, count=2)
        assert run_job(inp1, db, tmp_path / "out1", ctl1, batch1).returncode == 0

        inp2 = write_batch(tmp_path / "close2.fb", batch2, [
            (1, "AC1000000003", "BAL", "+", 35, "GRP001", "CLS00003"),
        ], total=35)
        ctl2 = control(tmp_path / "control2.json", batch2, 35, count=1, prior_batch_id=batch1)
        assert run_job(inp2, db, tmp_path / "out2", ctl2, batch2).returncode == 0

        before_close = load_db(db)
        out_close = tmp_path / "out_close"
        close_result = run_close("20260618", db, out_close)
        assert close_result.returncode == 0, close_result.stderr + close_result.stdout

        close_summary = json.loads((out_close / "close_20260618.json").read_text())
        assert close_summary["status"] == "CLOSED"
        assert close_summary["batch_count"] == 2
        assert [b["batch_id"] for b in close_summary["batches"]] == [batch1, batch2]
        assert [b["detail_count"] for b in close_summary["batches"]] == [2, 1]
        assert close_summary["grand_total"] == 50
        state = load_db(db)
        assert close_summary["chain_root"] == state["control_totals"][batch2]["chain_sha256"]

        lines = (out_close / "glfeed_20260618.dat").read_text().splitlines()
        assert len(lines) == 4
        assert lines[0] == "H20260618000002"
        assert lines[1][0] == "G"
        assert lines[1][1:11].rstrip() == batch1
        assert lines[1][11:75] == state["control_totals"][batch1]["chain_sha256"]
        assert lines[1][75:81] == "000002"
        assert lines[2][75:81] == "000001"
        assert lines[3] == "T20260618000002+000000000050"

        after_close = load_db(db)
        assert after_close == before_close

    def test_close_mode_detects_chain_break_and_writes_empty_feed(self, tmp_path):
        batch1 = "T6BRK001"
        batch2 = "T6BRK002"
        db = copy_seed(tmp_path)

        inp1 = write_batch(tmp_path / "break1.fb", batch1, [
            (1, "AC1000000001", "BAL", "+", 5, "GRP001", "BRK00001"),
        ], total=5)
        ctl1 = control(tmp_path / "control1.json", batch1, 5)
        assert run_job(inp1, db, tmp_path / "out1", ctl1, batch1).returncode == 0

        inp2 = write_batch(tmp_path / "break2.fb", batch2, [
            (1, "AC1000000002", "BAL", "+", 6, "GRP001", "BRK00002"),
        ], total=6)
        ctl2 = control(tmp_path / "control2.json", batch2, 6, prior_batch_id=batch1)
        assert run_job(inp2, db, tmp_path / "out2", ctl2, batch2).returncode == 0

        tampered = load_db(db)
        tampered["control_totals"][batch2]["chain_sha256"] = "f" * 64
        Path(db).write_text(json.dumps(tampered, indent=2, sort_keys=True) + "\n")

        out_close = tmp_path / "out_close"
        close_result = run_close("20260618", db, out_close)
        assert close_result.returncode != 0
        close_summary = json.loads((out_close / "close_20260618.json").read_text())
        assert close_summary["status"] == "CLOSE_BROKEN"
        assert close_summary["batches"] == []
        assert (out_close / "glfeed_20260618.dat").read_bytes() == b""

    def test_close_mode_for_empty_date_writes_closed_summary_and_zero_byte_feed(self, tmp_path):
        db = copy_seed(tmp_path)
        before = load_db(db)
        out_close = tmp_path / "out_close"
        close_result = run_close("20990101", db, out_close)
        assert close_result.returncode == 0
        close_summary = json.loads((out_close / "close_20990101.json").read_text())
        assert close_summary["status"] == "CLOSED"
        assert close_summary["batch_count"] == 0
        assert close_summary["chain_root"] == "0" * 64
        assert close_summary["batches"] == []
        assert (out_close / "glfeed_20990101.dat").read_bytes() == b""
        after = load_db(db)
        assert after == before


