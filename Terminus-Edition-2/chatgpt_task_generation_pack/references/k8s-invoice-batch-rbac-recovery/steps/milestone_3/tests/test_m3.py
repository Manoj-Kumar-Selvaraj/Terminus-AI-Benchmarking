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


def test_role_permissions_are_minimal_and_workflow_still_passes():
    data = run_simulation()
    least = data["least_privilege"]

    assert data["service_account_chain"]["workflow_ready"] is True
    assert data["overlap"]["single_publication_per_window"] is True
    assert least["has_wildcards"] is False
    assert least["covers_workflow"] is True
    assert least["is_minimal"] is True
    assert least["concurrency_policy"] == "Forbid"

    permissions = least["permissions"]
    assert len(permissions) == 2

    configmap_rule = next(rule for rule in permissions if "configmaps" in rule["resources"])
    secret_rule = next(rule for rule in permissions if "secrets" in rule["resources"])

    assert configmap_rule["verbs"] == ["get"]
    assert set(secret_rule["verbs"]) == {"create", "get"}
