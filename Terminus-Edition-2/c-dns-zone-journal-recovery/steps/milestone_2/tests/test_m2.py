# ruff: noqa
import json
import subprocess
import tempfile
from pathlib import Path

BIN = "/app/bin/zonectl"

def run(*args, check=False):
    p = subprocess.run([BIN, *map(str, args)], text=True, capture_output=True)
    if check and p.returncode != 0:
        raise AssertionError(f"command failed: {p.args}\nstdout={p.stdout}\nstderr={p.stderr}")
    return p

def write(path, text):
    Path(path).write_text(text, encoding="utf-8")

def seed(root, serial=10, rows="api.internal\tA\t30\t10.0.0.1\n"):
    records = Path(root) / "records.tsv"
    write(records, rows)
    run("seed", "--state", root, "--serial", serial, "--records", records, check=True)

def changes(root, name, text):
    p = Path(root) / name
    write(p, text)
    return p

def query(root):
    out = Path(root) / "query.json"
    run("query", "--state", root, "--out", out, check=True)
    return json.loads(out.read_text())

def recover(root):
    out = Path(root) / "recover.json"
    p = run("recover", "--state", root, "--out", out)
    return p, (json.loads(out.read_text()) if out.exists() else None)

def apply(root, txid, change_file, crash=None):
    a = ["apply", "--state", root, "--txid", txid, "--changes", change_file]
    if crash:
        a += ["--crash", crash]
    return run(*a)


class TestMilestone2:
    def test_identical_txid_replay_is_noop(self):
        """An identical durable transaction ID replay succeeds without a second serial advance."""
        with tempfile.TemporaryDirectory() as d:
            seed(d, 7)
            c = changes(d, "c.tsv", "SET\ta.internal\tA\t30\t10.0.0.7\n")
            assert apply(d, "stable-id", c).returncode == 0
            assert apply(d, "stable-id", c).returncode == 0
            s = query(d)
            assert s["serial"] == 8 and s["applied_txids"].count("stable-id") == 1

    def test_identical_replay_after_restart_is_noop(self):
        """Transaction identity stored in snapshots suppresses a replay after process restart."""
        with tempfile.TemporaryDirectory() as d:
            seed(d, 20)
            c = changes(d, "c.tsv", "SET\tb.internal\tTXT\t30\tv=1\n")
            apply(d, "persisted-id", c)
            before = query(d)
            apply(d, "persisted-id", c)
            assert query(d) == before

    def test_conflicting_txid_reuse_fails_closed(self):
        """Reusing a committed transaction ID for different changes is rejected without state mutation."""
        with tempfile.TemporaryDirectory() as d:
            seed(d)
            a = changes(d, "a.tsv", "SET\ta.internal\tA\t30\t10.0.0.1\n")
            b = changes(d, "b.tsv", "SET\ta.internal\tA\t30\t10.0.0.2\n")
            apply(d, "same", a)
            before = query(d)
            p = apply(d, "same", b)
            assert p.returncode != 0 and "conflict" in p.stderr.lower()
            assert query(d) == before

    def test_duplicate_commits_in_one_journal_apply_once(self):
        """Two complete copies of one transaction in a journal are coalesced during a single recovery."""
        with tempfile.TemporaryDirectory() as d:
            seed(d, 100)
            c = changes(d, "c.tsv", "SET\tc.internal\tA\t30\t10.0.0.3\n")
            assert apply(d, "dup", c, "after_commit").returncode == 75
            jp = Path(d, "journal.log")
            jp.write_bytes(jp.read_bytes() * 2)
            p, s = recover(d)
            assert p.returncode == 0 and s["serial"] == 101
            assert s["applied_txids"].count("dup") == 1

    def test_stale_base_serial_is_rejected_and_journal_retained(self):
        """A new transaction whose base serial is stale is rejected and its evidence remains available."""
        with tempfile.TemporaryDirectory() as d:
            seed(d, 30)
            c = changes(d, "c.tsv", "SET\td.internal\tA\t30\t10.0.0.4\n")
            assert apply(d, "stale", c, "after_commit").returncode == 75
            jp = Path(d, "journal.log")
            jp.write_text(jp.read_text().replace("|30|31|", "|29|30|"))
            original = jp.read_bytes()
            p, _ = recover(d)
            assert p.returncode != 0
            assert jp.read_bytes() == original and query(d)["serial"] == 30

    def test_skipped_base_serial_is_rejected(self):
        """A new transaction whose base serial skips ahead is rejected without advancing state."""
        with tempfile.TemporaryDirectory() as d:
            seed(d, 30)
            c = changes(d, "c.tsv", "SET\te.internal\tA\t30\t10.0.0.5\n")
            assert apply(d, "skip", c, "after_commit").returncode == 75
            jp = Path(d, "journal.log")
            jp.write_text(jp.read_text().replace("|30|31|", "|31|32|"))
            p, _ = recover(d)
            assert p.returncode != 0 and query(d)["serial"] == 30

    def test_delete_absent_advances_once_then_replays_as_noop(self):
        """A new delete of an absent record commits once, while its replay does not advance again."""
        with tempfile.TemporaryDirectory() as d:
            seed(d, 55)
            c = changes(d, "c.tsv", "DEL\tmissing.internal\tA\n")
            apply(d, "del-1", c)
            apply(d, "del-1", c)
            assert query(d)["serial"] == 56

    def test_torn_tail_recovery_remains_available(self):
        """Milestone 1 torn-tail recovery remains intact after replay identity changes."""
        with tempfile.TemporaryDirectory() as d:
            seed(d, 88)
            c = changes(d, "tail.tsv", "SET\ttail.internal\tA\t10\t10.8.8.8\n")
            assert apply(d, "tail-id", c, "torn_commit").returncode == 75
            p, state = recover(d)
            assert p.returncode == 0 and state["serial"] == 88
            assert all(r["name"] != "tail.internal" for r in state["records"])

    def test_checksum_corruption_still_preserves_active_state(self):
        """Replay changes do not weaken complete-transaction checksum validation."""
        with tempfile.TemporaryDirectory() as d:
            seed(d, 9)
            c = changes(d, "bad.tsv", "SET\tbad.internal\tA\t10\t10.9.9.9\n")
            assert apply(d, "bad-checksum", c, "after_commit").returncode == 75
            jp = Path(d, "journal.log")
            rows = jp.read_text().splitlines()
            rows[-1] = rows[-1][:-1] + ("0" if rows[-1][-1] != "0" else "1")
            jp.write_text("\n".join(rows) + "\n")
            before = query(d)
            p, _ = recover(d)
            assert p.returncode != 0 and query(d) == before

    def test_serial_wrap_uses_unsigned_successor(self):
        """The serial after 4294967295 is zero and duplicate replay remains a no-op at the boundary."""
        with tempfile.TemporaryDirectory() as d:
            seed(d, 4294967295)
            c = changes(d, "c.tsv", "SET\twrap.internal\tA\t1\t127.0.0.1\n")
            apply(d, "wrap", c)
            apply(d, "wrap", c)
            assert query(d)["serial"] == 0
