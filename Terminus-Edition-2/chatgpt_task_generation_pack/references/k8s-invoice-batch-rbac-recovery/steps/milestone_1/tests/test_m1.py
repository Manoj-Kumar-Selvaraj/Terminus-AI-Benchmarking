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


def test_service_account_can_read_invoice_configmap():
    data = run_simulation()
    rbac = data["rbac"]
    chain = data["service_account_chain"]

    assert chain["matches"] is True
    assert rbac["authorized"] is True, rbac
    assert rbac["reason"] is None
    assert chain["workflow_ready"] is True
    assert rbac["bound_role"] == "invoice-batch-role"
