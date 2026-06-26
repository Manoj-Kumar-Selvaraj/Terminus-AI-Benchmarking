# ruff: noqa: E501
import hashlib
import json
import shutil
import subprocess
import uuid
from pathlib import Path

import pytest

APP = Path("/app")
CLI = APP / "bin" / "pipelinectl"
RUNTIME = Path("/opt/task-tools/lambda-pipeline-runtime")


def run(*args, check=True, input_text=None):
    result = subprocess.run([str(a) for a in args], cwd=APP, text=True,
                            input=input_text, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=180)
    if check and result.returncode != 0:
        raise AssertionError(result.stdout)
    return result


def inspect(section):
    return json.loads(run(RUNTIME, "inspect", section).stdout)


def request_file(tmp_path, *, version=2, execution=None, batch=None, owner=None, artifact=None, items=2):
    token = uuid.uuid4().hex
    data = {
        "protocol_version": version,
        "execution_id": execution or f"exec-{token}",
        "batch_id": batch or f"batch-{token}",
        "artifact_digest": artifact or f"sha256:{hashlib.sha256(token.encode()).hexdigest()}",
        "items": [{"id": f"item-{i}-{token[:6]}", "amount": 9000+i, "tenant": "merchant-a"} for i in range(items)],
        "metadata": {"trace": token},
    }
    if version == 2 or owner is not None:
        data["owner"] = owner if owner is not None else f"owner-{token[:8]}"
    path = tmp_path / f"request-{token}.json"
    path.write_text(json.dumps(data))
    return path, data


def generation_infra(tmp_path, generation):
    dst = tmp_path / f"infra-{generation}-{uuid.uuid4().hex}"
    shutil.copytree(APP / "infra", dst)
    deployment = json.loads((dst / "deployment.json").read_text())
    deployment["generation"] = generation
    (dst / "deployment.json").write_text(json.dumps(deployment))
    stages = json.loads((dst / "stages.json").read_text())
    for stage in stages["stages"]:
        stage["package_hash"] = hashlib.sha256(f"{stage['name']}:g{generation}".encode()).hexdigest()
    (dst / "stages.json").write_text(json.dumps(stages))
    return dst


@pytest.fixture(scope="session", autouse=True)
def build_once():
    """Compile the complete restart and compatibility recovery implementation."""
    run("/usr/local/go/bin/go", "build", "-o", CLI, "./cmd/pipelinectl")


@pytest.fixture(autouse=True)
def fresh_deployment():
    """Reset application and trusted state before each recovery scenario."""
    shutil.rmtree(APP / "state", ignore_errors=True)
    (APP / "state").mkdir()
    run(RUNTIME, "reset")
    run(CLI, "deploy", "--infra", APP / "infra")


class TestMilestone5:
    def test_version_one_event_remains_compatible(self, tmp_path):
        """A Jenkins bridge event completes with deterministic legacy ownership."""
        path, request = request_file(tmp_path, version=1)
        checkpoint = json.loads(run(CLI, "run", "--request", path).stdout)
        assert checkpoint["status"] == "SUCCEEDED"
        assert checkpoint["protocol_version"] == 1
        assert checkpoint["owner"] == "legacy-jenkins/" + request["batch_id"]

    def test_version_two_preserves_explicit_owner(self, tmp_path):
        """The new event contract keeps its workload owner through checkpointing."""
        owner = f"lambda-pod-{uuid.uuid4().hex}"
        path, _ = request_file(tmp_path, version=2, owner=owner)
        checkpoint = json.loads(run(CLI, "run", "--request", path).stdout)
        assert checkpoint["owner"] == owner
        assert checkpoint["protocol_version"] == 2

    def test_version_two_missing_owner_rejected_before_invocation(self, tmp_path):
        """An ownerless version-two event cannot start any Lambda stage."""
        path, _ = request_file(tmp_path, version=2, owner="")
        result = run(CLI, "run", "--request", path, check=False)
        assert result.returncode != 0
        assert inspect("invocations") == []

    def test_unsupported_protocol_rejected_without_side_effect(self, tmp_path):
        """Unknown rollout protocols fail before trusted runtime work begins."""
        path, _ = request_file(tmp_path, version=7, owner="owner-x")
        result = run(CLI, "run", "--request", path, check=False)
        assert result.returncode != 0
        assert "unsupported" in result.stdout.lower()
        assert inspect("effects") == []

    def test_duplicate_execution_cannot_change_owner(self, tmp_path):
        """A second workload owner cannot take over an existing execution identity."""
        execution = f"exec-{uuid.uuid4().hex}"
        first, _ = request_file(tmp_path, execution=execution, owner="owner-a")
        run(CLI, "run", "--request", first)
        effects_before = inspect("effects")
        invocations_before = inspect("invocations")
        second, _ = request_file(tmp_path, execution=execution, owner="owner-b")
        result = run(CLI, "run", "--request", second, check=False)
        assert result.returncode != 0
        assert "conflicting" in result.stdout.lower()
        assert inspect("effects") == effects_before
        assert inspect("invocations") == invocations_before

    def test_duplicate_execution_cannot_change_batch(self, tmp_path):
        """An execution identity cannot be rebound to another settlement batch."""
        execution = f"exec-{uuid.uuid4().hex}"
        first, _ = request_file(tmp_path, execution=execution, batch="batch-a", owner="owner-a")
        run(CLI, "run", "--request", first)
        effects_before = inspect("effects")
        invocations_before = inspect("invocations")
        second, _ = request_file(tmp_path, execution=execution, batch="batch-b", owner="owner-a")
        result = run(CLI, "run", "--request", second, check=False)
        assert result.returncode != 0
        assert "conflicting" in result.stdout.lower()
        assert inspect("effects") == effects_before
        assert inspect("invocations") == invocations_before

    def test_duplicate_execution_cannot_change_artifact_digest(self, tmp_path):
        """An execution identity cannot be reused for different immutable input artifacts."""
        execution = f"exec-{uuid.uuid4().hex}"
        first, _ = request_file(tmp_path, execution=execution, owner="owner-a", artifact="sha256:" + "a" * 64)
        run(CLI, "run", "--request", first)
        effects_before = inspect("effects")
        invocations_before = inspect("invocations")
        second, _ = request_file(tmp_path, execution=execution, owner="owner-a", artifact="sha256:" + "b" * 64)
        result = run(CLI, "run", "--request", second, check=False)
        assert result.returncode != 0
        assert "conflicting" in result.stdout.lower()
        assert inspect("effects") == effects_before
        assert inspect("invocations") == invocations_before

    def test_corrupt_journal_tail_preserves_valid_records(self, tmp_path):
        """Reconciliation discards only an incomplete final JSONL record."""
        path, _ = request_file(tmp_path, items=1)
        run(CLI, "run", "--request", path)
        journal = APP / "state/operations.journal.jsonl"
        valid_lines = journal.read_text().splitlines()
        with journal.open("a") as handle:
            handle.write('{"operation_id":"truncated"')
        result = json.loads(run(CLI, "reconcile").stdout)
        repaired_lines = journal.read_text().splitlines()
        assert result["journal_repaired"] is True
        assert repaired_lines == valid_lines
        assert all(json.loads(line) for line in repaired_lines)

    def test_active_generation_drift_is_reapplied(self, tmp_path):
        """Confirmed simulator drift is repaired from the durable deployment snapshot."""
        run(RUNTIME, "drift", "generation:1")
        path, _ = request_file(tmp_path)
        assert run(CLI, "run", "--request", path, check=False).returncode != 0
        result = json.loads(run(CLI, "reconcile").stdout)
        assert result["drift_repaired"] is True
        assert inspect("state")["drift"] == {}
        checkpoint = json.loads(run(CLI, "resume", "--execution", json.loads(path.read_text())["execution_id"]).stdout)
        assert checkpoint["status"] == "SUCCEEDED"

    def test_reconcile_resumes_pending_execution(self, tmp_path):
        """A restart recovery pass resumes work from its saved failed-stage checkpoint."""
        path, request = request_file(tmp_path, items=1)
        run(RUNTIME, "inject", "BEFORE_STAGE:notify_partner", "3")
        assert run(CLI, "run", "--request", path, check=False).returncode != 0
        run(RUNTIME, "clear-failures")
        result = json.loads(run(CLI, "reconcile").stdout)
        assert request["execution_id"] in result["resumed"]
        checkpoint = json.loads(run(CLI, "inspect", "--what", "execution", "--execution", request["execution_id"]).stdout)
        assert checkpoint["status"] == "SUCCEEDED"
        assert len([e for e in inspect("effects") if e["stage"] == "write_ledger"]) == 1

    def test_repeated_reconciliation_is_idempotent(self, tmp_path):
        """A completed recovery rerun makes no additional changes or side effects."""
        path, _ = request_file(tmp_path)
        run(CLI, "run", "--request", path)
        before_effects = inspect("effects")
        first = json.loads(run(CLI, "reconcile").stdout)
        second = json.loads(run(CLI, "reconcile").stdout)
        assert first["resumed"] == second["resumed"] == []
        assert second["journal_repaired"] is False
        assert second["drift_repaired"] is False
        assert inspect("effects") == before_effects

    def test_mixed_version_workloads_run_independently(self, tmp_path):
        """Legacy Jenkins and new Lambda events coexist without shared ownership state."""
        v1, r1 = request_file(tmp_path, version=1)
        v2, r2 = request_file(tmp_path, version=2, owner="lambda-new")
        c1 = json.loads(run(CLI, "run", "--request", v1).stdout)
        c2 = json.loads(run(CLI, "run", "--request", v2).stdout)
        assert c1["status"] == c2["status"] == "SUCCEEDED"
        assert c1["owner"] == "legacy-jenkins/" + r1["batch_id"]
        assert c2["owner"] == "lambda-new"
        assert {e["batch_id"] for e in inspect("effects")} == {r1["batch_id"], r2["batch_id"]}

    def test_stale_worker_cannot_switch_registered_generation(self, tmp_path):
        """The trusted execution registration rejects a stale worker using another generation."""
        path, request = request_file(tmp_path, items=1)
        run(RUNTIME, "inject", "BEFORE_STAGE:write_ledger", "3")
        run(CLI, "run", "--request", path, check=False)
        infra2 = generation_infra(tmp_path, 2)
        run(CLI, "deploy", "--infra", infra2)
        run(CLI, "cutover", "--generation", "2", "--writer", "lambda")
        checkpoint = json.loads(run(CLI, "inspect", "--what", "execution", "--execution", request["execution_id"]).stdout)
        stale = {
            "stage": "write_ledger",
            "execution_id": request["execution_id"],
            "batch_id": request["batch_id"],
            "item_id": request["items"][0]["id"],
            "attempt": 1,
            "generation": 2,
            "epoch": checkpoint["epoch"] + 1,
            "owner": checkpoint["owner"],
            "idempotency_key": request["execution_id"] + "/write_ledger/" + request["items"][0]["id"],
            "metadata": {"artifact_digest": request["artifact_digest"]},
        }
        response = json.loads(run(RUNTIME, "invoke", input_text=json.dumps(stale)).stdout)
        assert response["ok"] is False and response["class"] == "stale"

    def test_completed_history_survives_drift_and_reconcile(self, tmp_path):
        """Repairing control-plane drift does not rewrite completed execution history."""
        path, request = request_file(tmp_path)
        completed = json.loads(run(CLI, "run", "--request", path).stdout)
        effects = inspect("effects")
        run(RUNTIME, "drift", "generation:1")
        run(CLI, "reconcile")
        after = json.loads(run(CLI, "inspect", "--what", "execution", "--execution", request["execution_id"]).stdout)
        assert after == completed
        assert inspect("effects") == effects

    def test_no_credentials_or_trusted_state_fabrication_in_source(self):
        """The recovery implementation contains no static AWS secret or direct trusted-state writer."""
        source = "\n".join(p.read_text(errors="ignore") for p in (APP / "internal").rglob("*.go"))
        assert "AKIA" not in source
        assert "aws_secret_access_key" not in source.lower()
        assert "/var/lib/lambda-pipeline-runtime/state.json" not in source
        assert "shared-settlement-pipeline" not in (APP / "internal/recovery/reconcile.go").read_text()
