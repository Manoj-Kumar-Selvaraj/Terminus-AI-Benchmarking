import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

APP = Path(os.environ.get("APP_DIR", os.environ.get("APP", "/app")))
RECOVER = APP / "bin" / "vpc-recover"


def make_root():
    td = tempfile.TemporaryDirectory()
    root = Path(td.name) / "incident"
    for name in ["infra", "evidence", "docs", "state"]:
        src = APP / name
        if src.exists():
            shutil.copytree(src, root / name, dirs_exist_ok=True)
    (root / "state").mkdir(parents=True, exist_ok=True)
    return td, root


def load_json(path):
    return json.loads(Path(path).read_text())


def write_json(path, obj):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2) + "\n")


def cfg(root):
    return load_json(root / "infra/envs/prod/vpc_config.json")


def save_cfg(root, c):
    write_json(root / "infra/envs/prod/vpc_config.json", c)


def evidence(root, name):
    return load_json(root / "evidence" / name)


def save_evidence(root, name, obj):
    write_json(root / "evidence" / name, obj)


def run(root, cmd, owner=None, fail_after=None, check=False):
    args = [str(RECOVER), cmd, "--root", str(root), "--json"]
    if owner:
        args += ["--owner", owner]
    if fail_after:
        args += ["--fail-after", fail_after]
    result = subprocess.run(
        args,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        out = json.loads(result.stdout or "{}")
    except Exception:
        out = {"stdout": result.stdout, "stderr": result.stderr}
    if check:
        assert result.returncode == 0, result.stderr + result.stdout
    return result, out


def state(root):
    return load_json(root / "state/vpc_recovered_state.json")


def journal_lines(root):
    path = root / "state/recovery_journal.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def default_target(rt):
    for route in rt.get("routes", []):
        if route.get("destination") == "0.0.0.0/0":
            return route.get("target")
    return None


def app_rts(st):
    return [rt for rt in st["route_tables"] if rt["tier"] == "app"]


def data_rts(st):
    return [rt for rt in st["route_tables"] if rt["tier"] == "data"]
