import json
import os
import subprocess
import sys
from pathlib import Path

from src.iam_simulator import (
    decide,
    has_broad_sqs_grant,
    has_log_permissions,
    required_sqs_decisions,
)

APP = Path(os.environ.get("APP_ROOT", "/app"))
PYTHON = sys.executable

def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)

def run_sim(tmp_path, scenario, batch=None, cycles=1):
    ledger = tmp_path / "ledger.json"
    dlq = tmp_path / "dlq.json"
    ledger.write_text("[]\n", encoding="utf-8")
    dlq.write_text("[]\n", encoding="utf-8")
    result = tmp_path / f"{scenario}_result.json"
    cmd = [PYTHON, str(APP / "scripts" / "run_simulation.py"), "--scenario", scenario, "--result", str(result)]
    if batch:
        cmd += ["--batch", str(batch), "--cycles", str(cycles)]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(APP)
    env["APP_ROOT"] = str(APP)
    env["SIDE_EFFECT_LEDGER"] = str(ledger)
    env["DLQ_STATE"] = str(dlq)
    proc = subprocess.run(cmd, cwd=APP, env=env, text=True, capture_output=True)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    return load_json(result), load_json(ledger), load_json(dlq)

def write_temp_batch(tmp_path, messages, queue_arn=None):
    queues = load_json(APP / "config" / "queues.json")
    path = tmp_path / "dynamic_batch.json"
    path.write_text(json.dumps({"queue_arn": queue_arn or queues["expected_active_queue_arn"], "messages": messages}, indent=2), encoding="utf-8")
    return path

def sqs_message(mid, event_id, amount=100, account="acct-dyn", poison=False, malformed=False, queue_arn=None):
    queues = load_json(APP / "config" / "queues.json")
    body = {"business_event_id": event_id, "account_id": account, "amount_cents": amount, "currency": "USD", "operation": "ledger_credit"}
    if poison:
        body = {"business_event_id": event_id, "poison": True, "failure_reason": "fixture_poison"}
    rendered = "{bad-json" if malformed else json.dumps(body, sort_keys=True)
    return {"messageId": mid, "receiptHandle": f"rh-{mid}", "eventSourceARN": queue_arn or queues["expected_active_queue_arn"], "body": rendered, "attributes": {"ApproximateReceiveCount": "0"}, "messageAttributes": {}}


class TestMilestone2:
    def test_required_sqs_actions_are_allowed_on_migrated_queue(self):
        """Receive, delete, visibility, and attribute reads must allow the migrated queue ARN."""
        queues = load_json(APP / "config" / "queues.json")
        policy = load_json(APP / "config" / "lambda_role_policy.json")
        decisions = required_sqs_decisions(policy, queues["expected_active_queue_arn"])
        assert decisions == {"sqs:ReceiveMessage": "allowed", "sqs:DeleteMessage": "allowed", "sqs:ChangeMessageVisibility": "allowed", "sqs:GetQueueAttributes": "allowed"}

    def test_queue_permissions_are_not_wildcard_broadened(self):
        """The queue fix must not use wildcard action or wildcard resource grants for SQS."""
        policy = load_json(APP / "config" / "lambda_role_policy.json")
        assert not has_broad_sqs_grant(policy)

    def test_old_queue_only_permission_does_not_satisfy_migrated_queue(self):
        """The new queue ARN must be explicitly authorized rather than relying on old-queue scope."""
        queues = load_json(APP / "config" / "queues.json")
        policy = load_json(APP / "config" / "lambda_role_policy.json")
        assert decide(policy, "sqs:ReceiveMessage", queues["expected_active_queue_arn"]) == "allowed"
        assert decide(policy, "sqs:ReceiveMessage", queues["old_queue_arn"]) != "allowed"

    def test_log_permissions_are_preserved(self):
        """Existing CloudWatch Logs permissions must remain after queue policy repair."""
        policy = load_json(APP / "config" / "lambda_role_policy.json")
        assert has_log_permissions(policy)

    def test_batch_simulation_has_no_queue_access_denied(self, tmp_path):
        """The simulator must be able to receive, delete, and manage visibility on the migrated queue."""
        result, _ledger, _dlq = run_sim(tmp_path, "batch", APP / "data" / "sqs_batch_01.json", cycles=1)
        assert result["access_denied"] is False
        assert result["access_denied_actions"] == []
        assert set(result["deleted_message_ids"]) == {"msg-pay-1001", "msg-pay-1002", "msg-pay-1003"}
