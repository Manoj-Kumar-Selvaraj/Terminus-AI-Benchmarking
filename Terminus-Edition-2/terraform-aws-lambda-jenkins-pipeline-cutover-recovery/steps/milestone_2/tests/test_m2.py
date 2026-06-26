# ruff: noqa: E501
import hashlib
import json
import re
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
                            timeout=120)
    if check and result.returncode != 0:
        raise AssertionError(result.stdout)
    return result


def inspect(section):
    return json.loads(run(RUNTIME, "inspect", section).stdout)


def make_request(tmp_path, execution=None, batch=None, items=2):
    token = uuid.uuid4().hex
    data = {
        "protocol_version": 2,
        "execution_id": execution or f"exec-{token}",
        "batch_id": batch or f"batch-{token}",
        "artifact_digest": f"sha256:{hashlib.sha256(token.encode()).hexdigest()}",
        "owner": f"owner-{token[:8]}",
        "items": [{"id": f"item-{i}-{token[:6]}", "amount": 5000+i, "tenant": "merchant-a"} for i in range(items)],
        "metadata": {"trace": token},
    }
    path = tmp_path / f"{token}.json"
    path.write_text(json.dumps(data))
    return path, data


@pytest.fixture(scope="session", autouse=True)
def build_once():
    """Compile the application under test before exercising retry behavior."""
    run("/usr/local/go/bin/go", "build", "-o", CLI, "./cmd/pipelinectl")


@pytest.fixture(autouse=True)
def fresh_deployment():
    """Reset persistent state and deploy the repaired stage fleet for each case."""
    shutil.rmtree(APP / "state", ignore_errors=True)
    (APP / "state").mkdir()
    run(RUNTIME, "reset")
    run(CLI, "deploy", "--infra", APP / "infra")


class TestMilestone2:
    def test_transient_stage_failure_retries_within_budget(self, tmp_path):
        """A transient Lambda failure is retried without restarting the pipeline."""
        path, _ = make_request(tmp_path)
        run(RUNTIME, "inject", "BEFORE_STAGE:write_ledger", "2")
        checkpoint = json.loads(run(CLI, "run", "--request", path).stdout)
        assert checkpoint["status"] == "SUCCEEDED"
        assert max(v for k, v in checkpoint["attempts"].items() if k.startswith("write_ledger/")) == 3
        assert len([i for i in inspect("invocations") if i["stage"] == "intake"]) == 1

    def test_lost_response_after_ledger_commit_is_idempotent(self, tmp_path):
        """Retrying an uncertain ledger response does not create a second ledger effect."""
        path, request = make_request(tmp_path, items=1)
        run(RUNTIME, "inject", "AFTER_EFFECT:write_ledger", "1")
        checkpoint = json.loads(run(CLI, "run", "--request", path).stdout)
        assert checkpoint["status"] == "SUCCEEDED"
        ledger = [e for e in inspect("effects") if e["stage"] == "write_ledger"]
        assert len(ledger) == 1 and ledger[0]["count"] == 1
        assert ledger[0]["idempotency_key"].startswith(request["execution_id"] + "/write_ledger/")

    def test_lost_downstream_responses_do_not_duplicate_effects(self, tmp_path):
        """Report, notification, and archive operations retain stable identities across retries."""
        path, _ = make_request(tmp_path)
        for stage in ("build_report", "notify_partner", "archive_batch"):
            run(RUNTIME, "inject", f"AFTER_EFFECT:{stage}", "1")
        run(CLI, "run", "--request", path)
        effects = inspect("effects")
        for stage in ("build_report", "notify_partner", "archive_batch"):
            rows = [e for e in effects if e["stage"] == stage]
            assert len(rows) == 1 and rows[0]["count"] == 1

    def test_retry_budget_exhaustion_persists_recovery_point(self, tmp_path):
        """Exhausted retries leave a durable retry-pending checkpoint at the failed stage."""
        path, request = make_request(tmp_path, items=1)
        run(RUNTIME, "inject", "BEFORE_STAGE:write_ledger", "3")
        result = run(CLI, "run", "--request", path, check=False)
        assert result.returncode != 0
        checkpoint = json.loads(run(CLI, "inspect", "--what", "execution", "--execution", request["execution_id"]).stdout)
        assert checkpoint["status"] == "RETRY_PENDING"
        assert checkpoint["next_stage"] == 7

    def test_resume_starts_at_first_unfinished_stage(self, tmp_path):
        """After recovery, completed stages are not replayed from intake."""
        path, request = make_request(tmp_path, items=1)
        run(RUNTIME, "inject", "BEFORE_STAGE:write_ledger", "3")
        run(CLI, "run", "--request", path, check=False)
        before = inspect("invocations")
        early_counts = {s: len([i for i in before if i["stage"] == s]) for s in ("intake", "verify_manifest", "fetch_inputs")}
        run(RUNTIME, "clear-failures")
        checkpoint = json.loads(run(CLI, "resume", "--execution", request["execution_id"]).stdout)
        assert checkpoint["status"] == "SUCCEEDED"
        after = inspect("invocations")
        for stage, count in early_counts.items():
            assert len([i for i in after if i["stage"] == stage]) == count

    def test_process_rebuild_does_not_lose_checkpoint(self, tmp_path):
        """Rebuilding the controller simulates restart while preserving durable progress."""
        path, request = make_request(tmp_path, items=1)
        run(RUNTIME, "inject", "BEFORE_STAGE:notify_partner", "3")
        run(CLI, "run", "--request", path, check=False)
        run("/usr/local/go/bin/go", "build", "-o", CLI, "./cmd/pipelinectl")
        run(RUNTIME, "clear-failures")
        checkpoint = json.loads(run(CLI, "resume", "--execution", request["execution_id"]).stdout)
        assert checkpoint["status"] == "SUCCEEDED"
        assert len([e for e in inspect("effects") if e["stage"] == "write_ledger"]) == 1

    def test_completed_execution_rerun_is_noop(self, tmp_path):
        """Submitting an identical completed request causes no additional invocations or effects."""
        path, _ = make_request(tmp_path)
        first = json.loads(run(CLI, "run", "--request", path).stdout)
        invocations = len(inspect("invocations"))
        effects = list(inspect("effects"))
        second = json.loads(run(CLI, "run", "--request", path).stdout)
        assert first["status"] == second["status"] == "SUCCEEDED"
        assert len(inspect("invocations")) == invocations
        assert inspect("effects") == effects

    def test_conflicting_execution_reuse_is_rejected(self, tmp_path):
        """One execution ID cannot be rebound to a different settlement batch."""
        execution = f"exec-{uuid.uuid4().hex}"
        first_path, _ = make_request(tmp_path, execution=execution)
        run(CLI, "run", "--request", first_path)
        second_path, _ = make_request(tmp_path, execution=execution, batch=f"batch-{uuid.uuid4().hex}")
        result = run(CLI, "run", "--request", second_path, check=False)
        assert result.returncode != 0
        assert "conflicting" in result.stdout.lower()

    def test_checkpoint_uses_trusted_deterministic_clock(self, tmp_path):
        """Persisted recovery timestamps follow the simulator clock rather than host time."""
        run(RUNTIME, "clock", "set", "2026-06-23T12:34:56Z")
        path, _ = make_request(tmp_path)
        checkpoint = json.loads(run(CLI, "run", "--request", path).stdout)
        assert checkpoint["updated_at"] == "2026-06-23T12:34:56Z"

    def test_no_sleep_or_unbounded_retry_implementation(self):
        """Retry logic does not block a Lambda worker using wall-clock sleeps."""
        source = (APP / "internal/fanout/fanout.go").read_text() + (APP / "internal/engine/runner.go").read_text()
        assert "time.Sleep" not in source
        assert "for {" not in source
        assert re.search(r"const\s+MaxAttempts\s*=\s*3\b", source)

    def test_journal_contains_stable_started_and_committed_records(self, tmp_path):
        """Durable operation records bracket side effects with the same operation identity."""
        path, request = make_request(tmp_path, items=1)
        run(CLI, "run", "--request", path)
        records = [json.loads(line) for line in (APP / "state/operations.journal.jsonl").read_text().splitlines()]
        ledger = [r for r in records if r["stage"] == "write_ledger"]
        assert [r["status"] for r in ledger] == ["STARTED", "COMMITTED"]
        assert len({r["operation_id"] for r in ledger}) == 1
        assert ledger[0]["operation_id"].startswith(request["execution_id"])
