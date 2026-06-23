import hashlib
import json
import subprocess
from pathlib import Path

import yaml

APP = Path("/app")
SIM_DIR = APP / "sim"
MANIFESTS = APP / "manifests"

EXPECTED_SIM_HASHES = {
    "__init__.py": "8cafcaae67e024e85ac5d91398dddb6c59e8bf5ffa2a9b16980b1583dc308658",
    "config.json": "637111fea41fbfdec98cd91f2ab429f08ac92d22fbefafec94c51763d8319ee8",
    "ledger.py": "afc9e986007d8750df561b1437de723871a49f160131d3fc286c199598eb8c25",
    "loader.py": "e83bbbf900f1b5186d3823847f09db68cba33d7c10c6e6489f6f21662c187592",
    "rbac.py": "18d7ee927deac4bedeee58103a6aeabf9d51dfd64d7e678e187582189535cfde",
    "scheduler.py": "c6862326cc25ca4a08d292e1803ebd93488cb1fc1d1c5ab0e6245e25f3085050",
    "simulate.py": "943203168f8b1abeeabd333199f23fa927c6556674971f31234ef9bbb1c69ff3",
}


def assert_sim_integrity() -> None:
    for fname, expected in EXPECTED_SIM_HASHES.items():
        actual = hashlib.sha256((SIM_DIR / fname).read_bytes()).hexdigest()
        assert actual == expected, f"{fname} was modified"


def assert_cronjob_concurrency_forbid() -> None:
    cronjob = yaml.safe_load((MANIFESTS / "cronjob.yaml").read_text())
    assert cronjob["spec"]["concurrencyPolicy"] == "Forbid"


def run_simulation() -> dict:
    assert_sim_integrity()
    result = subprocess.run(
        ["python3", "-m", "sim.simulate"],
        cwd=APP,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout
    return json.loads(result.stdout)


def test_overlap_publishes_single_ledger_per_window():
    """Verify overlapping CronJob slots publish only the fixture's single ledger artifact."""
    assert_cronjob_concurrency_forbid()
    data = run_simulation()

    assert data["service_account_chain"]["workflow_ready"] is True
    overlap = data["overlap"]
    publication = data["publication"]

    assert overlap["concurrency_policy"] == "Forbid"
    assert overlap["overlap_detected"] is True
    assert len(overlap["started_jobs"]) == 1
    assert len(overlap["skipped_jobs"]) == 1
    assert overlap["duplicate_window_ids"] == []
    assert overlap["single_publication_per_window"] is True
    assert publication["single_publication_per_window"] is True
    assert publication["artifact_name"] == "ledger-WIN-20260612"
