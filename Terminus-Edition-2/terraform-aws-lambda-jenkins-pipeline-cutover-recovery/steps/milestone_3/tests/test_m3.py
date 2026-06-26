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


def make_request(tmp_path, *, batch=None, execution=None, item_count=4, poison_indexes=()):
    token = uuid.uuid4().hex
    data = {
        "protocol_version": 2,
        "execution_id": execution or f"exec-{token}",
        "batch_id": batch or f"batch-{token}",
        "artifact_digest": f"sha256:{hashlib.sha256(token.encode()).hexdigest()}",
        "owner": f"owner-{token[:8]}",
        "items": [
            {
                "id": f"item-{i}-{token[:6]}",
                "amount": 10000 + i,
                "tenant": "merchant-a",
                **({"poison": True} if i in poison_indexes else {}),
            }
            for i in range(item_count)
        ],
        "metadata": {"trace": token},
    }
    path = tmp_path / f"{token}.json"
    path.write_text(json.dumps(data))
    return path, data


@pytest.fixture(scope="session", autouse=True)
def build_once():
    """Compile the controller containing the fan-out recovery implementation."""
    run("/usr/local/go/bin/go", "build", "-o", CLI, "./cmd/pipelinectl")


@pytest.fixture(autouse=True)
def fresh_deployment():
    """Reset runtime and application state before each fan-out scenario."""
    shutil.rmtree(APP / "state", ignore_errors=True)
    (APP / "state").mkdir()
    run(RUNTIME, "reset")
    run(CLI, "deploy", "--infra", APP / "infra")


class TestMilestone3:
    def test_poison_item_isolated_to_dlq(self, tmp_path):
        """One permanently invalid item produces a partial batch and one DLQ entry."""
        path, request = make_request(tmp_path, poison_indexes=(1,))
        checkpoint = json.loads(run(CLI, "run", "--request", path).stdout)
        assert checkpoint["status"] == "PARTIAL"
        poison_id = request["items"][1]["id"]
        assert inspect("dlq")[request["batch_id"]] == [poison_id]
        poison_validation_invocations = [
            invocation for invocation in inspect("invocations")
            if invocation["stage"] == "validate_inputs" and invocation.get("item_id") == poison_id
        ]
        assert len(poison_validation_invocations) == 3
        assert [invocation["attempt"] for invocation in poison_validation_invocations] == [1, 2, 3]

    def test_valid_siblings_continue_to_ledger(self, tmp_path):
        """Valid items are committed even when another item is permanently invalid."""
        path, request = make_request(tmp_path, item_count=5, poison_indexes=(2,))
        run(CLI, "run", "--request", path)
        ledger_items = {e["item_id"] for e in inspect("effects") if e["stage"] == "write_ledger"}
        expected = {item["id"] for i, item in enumerate(request["items"]) if i != 2}
        assert ledger_items == expected

    def test_poison_item_never_reaches_external_effect(self, tmp_path):
        """A DLQ item cannot create a ledger effect before or after isolation."""
        path, request = make_request(tmp_path, poison_indexes=(0,))
        run(CLI, "run", "--request", path)
        poison_id = request["items"][0]["id"]
        assert all(e.get("item_id") != poison_id for e in inspect("effects"))

    def test_partial_batch_still_publishes_single_report_and_archive(self, tmp_path):
        """Batch-level completion effects occur once after valid siblings finish."""
        path, _ = make_request(tmp_path, poison_indexes=(1, 3))
        run(CLI, "run", "--request", path)
        effects = inspect("effects")
        for stage in ("build_report", "notify_partner", "archive_batch"):
            assert len([e for e in effects if e["stage"] == stage]) == 1

    def test_dlq_and_effects_are_stable_on_repeated_submission(self, tmp_path):
        """Replaying a completed partial execution does not duplicate DLQ or side effects."""
        path, request = make_request(tmp_path, poison_indexes=(1,))
        run(CLI, "run", "--request", path)
        before_dlq = inspect("dlq")
        before_effects = inspect("effects")
        run(CLI, "run", "--request", path)
        assert inspect("dlq") == before_dlq
        assert inspect("effects") == before_effects
        assert len(before_dlq[request["batch_id"]]) == 1

    def test_same_batch_cannot_be_owned_by_second_execution(self, tmp_path):
        """A completed batch remains fenced from another execution identity."""
        batch = f"batch-{uuid.uuid4().hex}"
        first, _ = make_request(tmp_path, batch=batch, item_count=2)
        second, _ = make_request(tmp_path, batch=batch, item_count=2)
        run(CLI, "run", "--request", first)
        result = run(CLI, "run", "--request", second, check=False)
        assert result.returncode != 0
        assert "owned" in result.stdout.lower() or "conflict" in result.stdout.lower()

    def test_unrelated_batches_progress_independently(self, tmp_path):
        """Failure isolation does not introduce a global serialization lock."""
        first, first_request = make_request(tmp_path, poison_indexes=(0,))
        second, second_request = make_request(tmp_path, item_count=3)
        first_result = json.loads(run(CLI, "run", "--request", first).stdout)
        second_result = json.loads(run(CLI, "run", "--request", second).stdout)
        assert first_result["status"] == "PARTIAL"
        assert second_result["status"] == "SUCCEEDED"
        effects = inspect("effects")
        assert any(e["batch_id"] == second_request["batch_id"] for e in effects)
        assert first_request["batch_id"] != second_request["batch_id"]
        lock_batches = {
            invocation["batch_id"]
            for invocation in inspect("invocations")
            if invocation["stage"] == "acquire_lock"
        }
        assert lock_batches == {first_request["batch_id"], second_request["batch_id"]}

    def test_transient_batch_lock_is_released_after_partial_completion(self, tmp_path):
        """Partial completion does not leave the trusted runtime lock held forever."""
        path, _ = make_request(tmp_path, poison_indexes=(0,))
        run(CLI, "run", "--request", path)
        assert inspect("state")["locks"] == {}

    def test_large_generated_batch_processes_each_valid_item_once(self, tmp_path):
        """Generated item identities prevent fixed-output solutions and exercise fan-out breadth."""
        path, request = make_request(tmp_path, item_count=17, poison_indexes=(5, 12))
        checkpoint = json.loads(run(CLI, "run", "--request", path).stdout)
        assert checkpoint["status"] == "PARTIAL"
        ledger = [e for e in inspect("effects") if e["stage"] == "write_ledger"]
        assert len(ledger) == 15
        assert all(e["count"] == 1 for e in ledger)
        assert len(inspect("dlq")[request["batch_id"]]) == 2

    def test_all_valid_batch_remains_successful(self, tmp_path):
        """Adding partial-failure handling preserves the normal all-valid workflow."""
        path, _ = make_request(tmp_path, item_count=6)
        checkpoint = json.loads(run(CLI, "run", "--request", path).stdout)
        assert checkpoint["status"] == "SUCCEEDED"
        assert not inspect("dlq")
        assert inspect("state")["locks"] == {}
