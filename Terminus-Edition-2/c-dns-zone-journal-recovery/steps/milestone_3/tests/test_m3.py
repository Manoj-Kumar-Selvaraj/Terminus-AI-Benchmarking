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


class TestMilestone3:
    def test_manifest_wins_over_higher_orphan_snapshot(self):
        """A higher-numbered snapshot not selected by the manifest is never promoted implicitly."""
        with tempfile.TemporaryDirectory() as d:
            seed(d, 5)
            orphan = Path(d, "snapshot.999.tsv")
            orphan.write_text("GEN\t999\nSERIAL\t999\nRR\tevil.internal\tA\t1\t6.6.6.6\n")
            s = query(d)
            assert s["generation"] == 1 and s["serial"] == 5
            assert all(r["name"] != "evil.internal" for r in s["records"])

    def test_crash_after_snapshot_keeps_old_generation_active(self):
        """A crash after writing the next snapshot but before manifest replacement preserves the old generation."""
        with tempfile.TemporaryDirectory() as d:
            seed(d, 10)
            before = query(d)
            p = run("compact", "--state", d, "--crash", "after_snapshot")
            assert p.returncode == 75
            assert Path(d, "snapshot.2.tsv").exists(), "snapshot must be written"
            assert query(d) == before
            rp, recovered = recover(d)
            assert rp.returncode == 0 and recovered == before
            assert not Path(d, "snapshot.2.tsv").exists()

    def test_crash_after_manifest_uses_new_generation(self):
        """A crash after manifest replacement leaves the complete new snapshot authoritative."""
        with tempfile.TemporaryDirectory() as d:
            seed(d, 11)
            p = run("compact", "--state", d, "--crash", "after_manifest")
            assert p.returncode == 75
            s = query(d)
            assert s["generation"] == 2 and s["serial"] == 11
            rp, s2 = recover(d)
            assert rp.returncode == 0 and s2 == s

    def test_successful_compaction_retires_previous_generation(self):
        """Only after a successful manifest switch may the previous active snapshot be retired."""
        with tempfile.TemporaryDirectory() as d:
            seed(d, 12)
            assert run("compact", "--state", d).returncode == 0
            assert Path(d, "snapshot.2.tsv").exists()
            assert not Path(d, "snapshot.1.tsv").exists()
            assert query(d)["generation"] == 2

    def test_repeated_compaction_preserves_contents_and_history(self):
        """Repeated compaction changes only generation metadata, not serial, records, or transaction identity."""
        with tempfile.TemporaryDirectory() as d:
            seed(d, 100)
            c = changes(d, "c.tsv", "SET\tp.internal\tTXT\t30\tx=y\n")
            apply(d, "history", c)
            base = query(d)
            run("compact", "--state", d, check=True)
            run("compact", "--state", d, check=True)
            now = query(d)
            assert now["serial"] == base["serial"]
            assert now["records"] == base["records"]
            assert now["applied_txids"] == base["applied_txids"]
            assert now["generation"] == base["generation"] + 2

    def test_wrap_state_survives_compaction_and_replay(self):
        """Serial zero after wrap, transaction history, and no-op replay survive generation changes."""
        with tempfile.TemporaryDirectory() as d:
            seed(d, 4294967295)
            c = changes(d, "c.tsv", "SET\tw.internal\tA\t1\t127.0.0.2\n")
            apply(d, "wrap-history", c)
            run("compact", "--state", d, check=True)
            apply(d, "wrap-history", c)
            s = query(d)
            assert s["serial"] == 0 and s["applied_txids"].count("wrap-history") == 1

    def test_replay_identity_survives_compaction(self):
        """A compacted transaction remains a no-op when replayed after the generation switch."""
        with tempfile.TemporaryDirectory() as d:
            seed(d, 200)
            c = changes(d, "c.tsv", "SET\tid.internal\tTXT\t30\tv=stable\n")
            apply(d, "compact-id", c)
            run("compact", "--state", d, check=True)
            before = query(d)
            apply(d, "compact-id", c)
            assert query(d) == before

    def test_conflicting_identity_after_compaction_fails_closed(self):
        """Compaction preserves conflict evidence for committed transaction IDs."""
        with tempfile.TemporaryDirectory() as d:
            seed(d, 201)
            a = changes(d, "a.tsv", "SET\tc.internal\tA\t10\t10.0.0.1\n")
            b = changes(d, "b.tsv", "SET\tc.internal\tA\t10\t10.0.0.2\n")
            apply(d, "conflict-id", a)
            run("compact", "--state", d, check=True)
            before = query(d)
            assert apply(d, "conflict-id", b).returncode != 0
            assert query(d) == before

    def test_active_snapshot_is_not_removed_during_orphan_cleanup(self):
        """Recovery cleanup removes misleading orphans while preserving the manifest-selected snapshot."""
        with tempfile.TemporaryDirectory() as d:
            seed(d, 70)
            Path(d, "snapshot.44.tsv").write_text("GEN\t44\nSERIAL\t44\n")
            p, s = recover(d)
            assert p.returncode == 0 and s["generation"] == 1
            assert Path(d, "snapshot.1.tsv").exists()
            assert not Path(d, "snapshot.44.tsv").exists(), "orphan not cleaned up"
