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


def run(*args, check=True):
    result = subprocess.run([str(a) for a in args], cwd=APP, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            timeout=180)
    if check and result.returncode != 0:
        raise AssertionError(result.stdout)
    return result


def inspect(section):
    return json.loads(run(RUNTIME, "inspect", section).stdout)


def request_file(tmp_path, *, execution=None, batch=None):
    token = uuid.uuid4().hex
    request = {
        "protocol_version": 2,
        "execution_id": execution or f"exec-{token}",
        "batch_id": batch or f"batch-{token}",
        "artifact_digest": f"sha256:{hashlib.sha256(token.encode()).hexdigest()}",
        "owner": f"owner-{token[:10]}",
        "items": [{"id": f"item-{token[:8]}", "amount": 7100, "tenant": "merchant-a"}],
        "metadata": {"trace": token},
    }
    path = tmp_path / f"request-{token}.json"
    path.write_text(json.dumps(request))
    return path, request


def generation_infra(tmp_path, generation):
    dst = tmp_path / f"infra-{generation}-{uuid.uuid4().hex}"
    shutil.copytree(APP / "infra", dst)
    deployment = json.loads((dst / "deployment.json").read_text())
    deployment["generation"] = generation
    (dst / "deployment.json").write_text(json.dumps(deployment))
    stages = json.loads((dst / "stages.json").read_text())
    for stage in stages["stages"]:
        stage["package_hash"] = hashlib.sha256(
            f"{stage['name']}:generation:{generation}".encode()
        ).hexdigest()
    (dst / "stages.json").write_text(json.dumps(stages))
    return dst


@pytest.fixture(scope="session", autouse=True)
def build_once():
    """Compile the version-aware migration controller once for this verifier."""
    run("/usr/local/go/bin/go", "build", "-o", CLI, "./cmd/pipelinectl")


@pytest.fixture(autouse=True)
def fresh_generation_one():
    """Reset the runtime and install generation one before each cutover scenario."""
    shutil.rmtree(APP / "state", ignore_errors=True)
    (APP / "state").mkdir()
    run(RUNTIME, "reset")
    run(CLI, "deploy", "--infra", APP / "infra")


class TestMilestone4:
    def test_deploy_and_cutover_to_new_generation(self, tmp_path):
        """A distinct package set can be deployed and selected for future executions."""
        infra2 = generation_infra(tmp_path, 2)
        deployed = json.loads(run(CLI, "deploy", "--infra", infra2).stdout)
        cutover = json.loads(run(CLI, "cutover", "--generation", "2", "--writer", "lambda").stdout)
        assert deployed["generation"] == 2
        assert cutover["active_generation"] == 2
        assert inspect("state")["active_generation"] == 2

    def test_inflight_execution_remains_on_original_generation(self, tmp_path):
        """An alias shift cannot mix function generations inside one execution."""
        path, request = request_file(tmp_path)
        run(RUNTIME, "inject", "BEFORE_STAGE:write_ledger", "3")
        assert run(CLI, "run", "--request", path, check=False).returncode != 0
        infra2 = generation_infra(tmp_path, 2)
        run(CLI, "deploy", "--infra", infra2)
        run(CLI, "cutover", "--generation", "2", "--writer", "lambda")
        run(RUNTIME, "clear-failures")
        checkpoint = json.loads(run(CLI, "resume", "--execution", request["execution_id"]).stdout)
        assert checkpoint["status"] == "SUCCEEDED"
        assert checkpoint["generation"] == 1
        generations = {i["generation"] for i in inspect("invocations") if i["execution_id"] == request["execution_id"]}
        assert generations == {1}

    def test_new_execution_uses_new_active_generation(self, tmp_path):
        """After cutover, newly accepted work pins the selected generation."""
        infra2 = generation_infra(tmp_path, 2)
        run(CLI, "deploy", "--infra", infra2)
        run(CLI, "cutover", "--generation", "2", "--writer", "lambda")
        path, request = request_file(tmp_path)
        checkpoint = json.loads(run(CLI, "run", "--request", path).stdout)
        assert checkpoint["generation"] == 2
        assert {i["generation"] for i in inspect("invocations") if i["execution_id"] == request["execution_id"]} == {2}

    def test_lost_cutover_response_reconciles_committed_alias(self, tmp_path):
        """A timeout after alias commit is recovered from authoritative control-plane state."""
        infra2 = generation_infra(tmp_path, 2)
        run(CLI, "deploy", "--infra", infra2)
        run(RUNTIME, "inject", "AFTER_ALIAS_SHIFT", "1")
        result = run(CLI, "cutover", "--generation", "2", "--writer", "lambda")
        cutover = json.loads(result.stdout)
        runtime = inspect("state")
        assert cutover["active_generation"] == runtime["active_generation"] == 2
        assert cutover["epoch"] == runtime["epoch"]

    def test_jenkins_shadow_is_read_only_after_lambda_cutover(self, tmp_path):
        """The comparison job cannot create a second settlement effect while Lambda is primary."""
        path, request = request_file(tmp_path)
        run(CLI, "run", "--request", path)
        before = list(inspect("effects"))
        shadow = json.loads(run(CLI, "jenkins-shadow", "--request", path).stdout)
        assert shadow["wrote"] is False
        assert inspect("effects") == before
        assert inspect("state")["jenkins_writes"] == 0
        assert request["batch_id"] in {e["batch_id"] for e in before}

    def test_cutover_does_not_hand_writer_back_to_jenkins(self, tmp_path):
        """The requested Lambda-primary writer remains authoritative after generation change."""
        infra2 = generation_infra(tmp_path, 2)
        run(CLI, "deploy", "--infra", infra2)
        cutover = json.loads(run(CLI, "cutover", "--generation", "2", "--writer", "lambda").stdout)
        assert cutover["writer"] == "lambda"
        assert inspect("state")["writer"] == "lambda"

    def test_rollback_affects_new_work_not_inflight_generation(self, tmp_path):
        """Rollback selects generation one for new work while a generation-two execution completes pinned."""
        infra2 = generation_infra(tmp_path, 2)
        run(CLI, "deploy", "--infra", infra2)
        run(CLI, "cutover", "--generation", "2", "--writer", "lambda")
        path2, request2 = request_file(tmp_path)
        run(RUNTIME, "inject", "BEFORE_STAGE:notify_partner", "3")
        run(CLI, "run", "--request", path2, check=False)
        run(CLI, "rollback", "--generation", "1")
        run(RUNTIME, "clear-failures")
        resumed = json.loads(run(CLI, "resume", "--execution", request2["execution_id"]).stdout)
        assert resumed["generation"] == 2 and resumed["status"] == "SUCCEEDED"
        path1, _ = request_file(tmp_path)
        new_checkpoint = json.loads(run(CLI, "run", "--request", path1).stdout)
        assert new_checkpoint["generation"] == 1

    def test_redeploy_same_generation_is_stable(self):
        """Reapplying unchanged infrastructure preserves one digest and deployment generation."""
        first = json.loads(run(CLI, "deploy", "--infra", APP / "infra").stdout)
        second = json.loads(run(CLI, "deploy", "--infra", APP / "infra").stdout)
        assert first["digest"] == second["digest"]
        assert list(inspect("deployments")) == ["1"]

    def test_new_packages_change_deployment_digest(self, tmp_path):
        """A new generation is tied to a changed immutable package set."""
        first = json.loads(run(CLI, "deploy", "--infra", APP / "infra").stdout)
        infra2 = generation_infra(tmp_path, 2)
        second = json.loads(run(CLI, "deploy", "--infra", infra2).stdout)
        assert first["digest"] != second["digest"]
        assert len({s["package_hash"] for s in second["stages"]}) == 12

    def test_cutover_and_rollback_preserve_exactly_once_effects(self, tmp_path):
        """Separate executions on both generations each publish their own effects exactly once."""
        first_path, _ = request_file(tmp_path)
        run(CLI, "run", "--request", first_path)
        infra2 = generation_infra(tmp_path, 2)
        run(CLI, "deploy", "--infra", infra2)
        run(CLI, "cutover", "--generation", "2", "--writer", "lambda")
        second_path, _ = request_file(tmp_path)
        run(CLI, "run", "--request", second_path)
        run(CLI, "rollback", "--generation", "1")
        assert all(e["count"] == 1 for e in inspect("effects"))
