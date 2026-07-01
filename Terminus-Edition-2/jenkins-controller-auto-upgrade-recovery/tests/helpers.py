import hashlib
import json
import os
import shutil
import subprocess
from pathlib import Path

APP = Path(os.environ.get("TASK_APP_DIR", "/app"))
RECOVER = Path(os.environ.get("RECOVER_WRAPPER", str(APP / "scripts" / "jenkins-recover")))
SOURCE = Path(os.environ.get("RECOVERY_SOURCE", str(APP / "recovery" / "main.go")))
SIM = Path(os.environ.get("SIM_BIN", str(APP / "scripts" / "jenkins_cluster_sim")))


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def fresh_root(tmp_path: Path) -> Path:
    root = tmp_path / "incident"
    root.mkdir()
    for name in ("cluster", "config", "backups", "jenkins_home", "evidence", "docs"):
        src = APP / name
        if src.exists():
            shutil.copytree(src, root / name)
    return root


def run_recover(root: Path, *args: str, check: bool = False, extra_env: dict | None = None):
    env = os.environ.copy()
    env.update(
        {
            "APP_ROOT": str(root),
            "JENKINS_RECOVERY_SOURCE": str(SOURCE),
            "JENKINS_SIM_BIN": str(SIM),
        }
    )
    if extra_env:
        for key, value in extra_env.items():
            if value is None:
                env.pop(key, None)
            else:
                env[key] = str(value)
    result = subprocess.run(
        [str(RECOVER), *args],
        text=True,
        capture_output=True,
        env=env,
        timeout=45,
    )
    if check and result.returncode != 0:
        raise AssertionError(f"command failed: {result.stderr}\n{result.stdout}")
    return result


def run_sim(root: Path, *args: str):
    env = os.environ.copy()
    env["APP_ROOT"] = str(root)
    return subprocess.run(
        [str(SIM), *args],
        text=True,
        capture_output=True,
        env=env,
        timeout=20,
    )


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    if not root.exists():
        return digest.hexdigest()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def journal_records(root: Path):
    path = root / "recovery_state" / "journal.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def create_snapshot(
    root: Path,
    name: str,
    created_at: str,
    target: str = "2.462.3",
    source: str = "2.426.3",
    corrupt: str | None = None,
):
    template = root / "backups" / "pre-upgrade-20260618"
    dest = root / "backups" / name
    shutil.copytree(template, dest)
    jobs = read_json(dest / "jobs.json")["jobs"]
    rels = ["config.xml", "credentials.xml", "queue.xml", "jobs.json"]
    rels += [f"jobs/{job.split('/')[0]}/config.xml" for job in jobs]
    checksums = {rel: hashlib.sha256((dest / rel).read_bytes()).hexdigest() for rel in rels}
    manifest = {
        "snapshot_id": name,
        "created_at": created_at,
        "source_version": source,
        "compatible_targets": [target],
        "checksums": checksums,
        "metadata": {"random_marker": name},
    }
    write_json(dest / "manifest.json", manifest)
    if corrupt:
        (dest / corrupt).write_text("corrupted", encoding="utf-8")
    return dest
