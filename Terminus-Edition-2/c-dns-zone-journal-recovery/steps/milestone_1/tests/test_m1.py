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


class TestMilestone1:
    def test_torn_closing_row_preserves_committed_prefix(self):
        """Recovery applies complete transactions and discards only a torn final closing row."""
        with tempfile.TemporaryDirectory() as d:
            seed(d)
            c1 = changes(d, "c1.tsv", "SET\tapi.internal\tA\t30\t10.0.0.2\n")
            apply(d, "tx-1", c1)
            c2 = changes(d, "c2.tsv", "SET\tnew.internal\tA\t30\t10.0.0.3\n")
            assert apply(d, "tx-2", c2, "torn_commit").returncode == 75
            p, state = recover(d)
            assert p.returncode == 0
            assert state["serial"] == 11
            assert {r["name"] for r in state["records"]} == {"api.internal"}
            assert state["records"][0]["value"] == "10.0.0.2"
            assert Path(d, "journal.log").read_text() == ""

    def test_complete_commit_after_crash_is_recovered(self):
        """A fully durable commit left before materialization is applied on restart."""
        with tempfile.TemporaryDirectory() as d:
            seed(d, 41)
            c = changes(d, "c.tsv", "SET\tx.internal\tTXT\t60\trecovered=yes\n")
            assert apply(d, "tx-complete", c, "after_commit").returncode == 75
            p, state = recover(d)
            assert p.returncode == 0 and state["serial"] == 42
            assert any(r["value"] == "recovered=yes" for r in state["records"])

    def test_checksum_corruption_fails_without_mutation(self):
        """Checksum corruption in a complete transaction is rejected without changing authoritative files."""
        with tempfile.TemporaryDirectory() as d:
            seed(d)
            c = changes(d, "c.tsv", "SET\tx.internal\tA\t30\t10.1.1.1\n")
            assert apply(d, "tx-bad", c, "after_commit").returncode == 75
            jp = Path(d, "journal.log")
            original_journal = jp.read_bytes()
            jp.write_bytes(original_journal[:-18] + b"0000000000000000\n")
            before_snapshot = Path(d, "snapshot.1.tsv").read_bytes()
            p, state = recover(d)
            assert p.returncode != 0 and state is None
            assert Path(d, "snapshot.1.tsv").read_bytes() == before_snapshot
            assert jp.read_bytes() != b""

    def test_closing_identifier_mismatch_is_not_treated_as_tail(self):
        """A complete closing row for the wrong transaction is corruption, not an ignorable interruption."""
        with tempfile.TemporaryDirectory() as d:
            seed(d)
            c = changes(d, "c.tsv", "DEL\tapi.internal\tA\n")
            assert apply(d, "tx-id", c, "after_commit").returncode == 75
            jp = Path(d, "journal.log")
            text = jp.read_text().replace("C|tx-id|", "C|other-id|")
            jp.write_text(text)
            before = query(d)
            p, _ = recover(d)
            assert p.returncode != 0
            assert query(d) == before

    def test_set_replaces_and_delete_absent_is_deterministic(self):
        """Recovered SET and DEL operations use record identity and produce deterministic sorted output."""
        with tempfile.TemporaryDirectory() as d:
            seed(d, rows="z.internal\tA\t10\t10.0.0.9\na.internal\tA\t10\t10.0.0.1\n")
            c = changes(d, "c.tsv", "SET\ta.internal\tA\t20\t10.0.0.2\nDEL\tmissing.internal\tA\n")
            assert apply(d, "tx-order", c, "after_commit").returncode == 75
            p, state = recover(d)
            assert p.returncode == 0
            assert [r["name"] for r in state["records"]] == ["a.internal", "z.internal"]
            assert state["records"][0]["ttl"] == 20

    def test_complete_malformed_operation_is_rejected(self):
        """A complete malformed operation row is corruption and cannot be discarded as a torn tail."""
        with tempfile.TemporaryDirectory() as d:
            seed(d)
            c = changes(d, "c.tsv", "SET\tx.internal\tA\t30\t10.2.2.2\n")
            assert apply(d, "tx-malformed", c, "after_commit").returncode == 75
            jp = Path(d, "journal.log")
            rows = jp.read_text().splitlines()
            rows[1] = "O|BROKEN|x.internal|A"
            jp.write_text("\n".join(rows) + "\n")
            before = query(d)
            p, _ = recover(d)
            assert p.returncode != 0
            assert query(d) == before

    def test_recovery_is_restart_safe_after_tail_cleanup(self):
        """Running recovery again after cleanup preserves the same state and serial."""
        with tempfile.TemporaryDirectory() as d:
            seed(d, 99)
            c = changes(d, "c.tsv", "SET\tr.internal\tA\t10\t10.9.0.1\n")
            assert apply(d, "tx-r", c, "torn_commit").returncode == 75
            p1, s1 = recover(d)
            p2, s2 = recover(d)
            assert p1.returncode == p2.returncode == 0
            assert s1 == s2 and s2["serial"] == 99
