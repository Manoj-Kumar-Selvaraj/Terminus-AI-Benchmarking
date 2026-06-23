import json
import subprocess
from pathlib import Path


APP = Path("/app")


def run_simulation() -> dict:
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
