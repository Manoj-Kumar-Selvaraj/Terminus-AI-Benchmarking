import json
import os
import subprocess
import sys
from pathlib import Path

APP = Path(os.environ.get("APP_ROOT", "/app"))
PYTHON = sys.executable
REQUIRED_SQS_ACTIONS = (
    "sqs:ReceiveMessage",
    "sqs:DeleteMessage",
    "sqs:ChangeMessageVisibility",
    "sqs:GetQueueAttributes",
)
REQUIRED_LOG_ACTIONS = ("logs:CreateLogStream", "logs:PutLogEvents")


def load_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _statement_resources(statement):
    return _as_list(statement.get("Resource"))


def _statement_actions(statement):
    return _as_list(statement.get("Action"))


def _policy_allows(policy, action, resource):
    for statement in policy.get("Statement", []):
        if statement.get("Effect") != "Allow":
            continue
        if action in _statement_actions(statement) and resource in _statement_resources(statement):
            return True
    return False


def _policy_denies_or_missing(policy, action, resource):
    return not _policy_allows(policy, action, resource)


def _has_broad_sqs_grant(policy):
    for statement in policy.get("Statement", []):
        if statement.get("Effect") != "Allow":
            continue
        actions = _statement_actions(statement)
        resources = _statement_resources(statement)
        if any(action in {"*", "sqs:*"} for action in actions):
            return True
        if any(resource == "*" for resource in resources) and any(
            action.startswith("sqs:") or action == "*" for action in actions
        ):
            return True
    return False


def _has_log_permissions(policy):
    return all(
        any(
            statement.get("Effect") == "Allow"
            and action in _statement_actions(statement)
            for statement in policy.get("Statement", [])
        )
        for action in REQUIRED_LOG_ACTIONS
    )


def _statements_for_resource(policy, resource):
    return [
        statement
        for statement in policy.get("Statement", [])
        if resource in _statement_resources(statement)
    ]


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


class TestMilestone2:
    def test_iam_simulator_not_tampered(self):
        """The IAM simulator source must remain intact so policy checks cannot be spoofed."""
        src = (APP / "src" / "iam_simulator.py").read_bytes()
        assert b"def decide(policy" in src
        assert b"fnmatch.fnmatchcase" in src
        assert b"def required_sqs_decisions" in src
        assert b"def has_broad_sqs_grant" in src

    def test_policy_json_has_migrated_queue_statement(self):
        """The role policy JSON must explicitly allow required SQS actions on the migrated queue."""
        queues = load_json(APP / "config" / "queues.json")
        policy = load_json(APP / "config" / "lambda_role_policy.json")
        migrated = queues["expected_active_queue_arn"]
        sqs_stmts = _statements_for_resource(policy, migrated)
        assert sqs_stmts, f"no statement grants access to {migrated}"
        for action in REQUIRED_SQS_ACTIONS:
            assert _policy_allows(policy, action, migrated), action

    def test_required_sqs_actions_are_allowed_on_migrated_queue(self):
        """Receive, delete, visibility, and attribute reads must allow the migrated queue ARN."""
        queues = load_json(APP / "config" / "queues.json")
        policy = load_json(APP / "config" / "lambda_role_policy.json")
        migrated = queues["expected_active_queue_arn"]
        for action in REQUIRED_SQS_ACTIONS:
            assert _policy_allows(policy, action, migrated)

    def test_queue_permissions_are_not_wildcard_broadened(self):
        """The queue fix must not use wildcard action or wildcard resource grants for SQS."""
        policy = load_json(APP / "config" / "lambda_role_policy.json")
        assert not _has_broad_sqs_grant(policy)

    def test_old_queue_only_permission_does_not_satisfy_migrated_queue(self):
        """The new queue ARN must be authorized and old-queue receive access must be removed."""
        queues = load_json(APP / "config" / "queues.json")
        policy = load_json(APP / "config" / "lambda_role_policy.json")
        assert _policy_allows(policy, "sqs:ReceiveMessage", queues["expected_active_queue_arn"])
        assert _policy_denies_or_missing(policy, "sqs:ReceiveMessage", queues["old_queue_arn"])

    def test_log_permissions_are_preserved(self):
        """Existing CloudWatch Logs permissions must remain after queue policy repair."""
        policy = load_json(APP / "config" / "lambda_role_policy.json")
        assert _has_log_permissions(policy)

    def test_batch_simulation_has_no_queue_access_denied(self, tmp_path):
        """The simulator must be able to receive, delete, and manage visibility on the migrated queue."""
        result, _ledger, _dlq = run_sim(tmp_path, "batch", APP / "data" / "sqs_batch_01.json", cycles=1)
        assert result["access_denied"] is False
        assert result["access_denied_actions"] == []
        assert set(result["deleted_message_ids"]) == {"msg-pay-1001", "msg-pay-1002", "msg-pay-1003"}


    def test_migrated_queue_grant_is_exact_and_not_mixed_with_old_queue(self):
        """The polling grant contains only the required actions and migrated resource."""
        queues = load_json(APP / "config" / "queues.json")
        policy = load_json(APP / "config" / "lambda_role_policy.json")
        matches = [st for st in policy["Statement"] if st.get("Effect") == "Allow" and queues["expected_active_queue_arn"] in _statement_resources(st)]
        assert len(matches) == 1
        assert set(_statement_actions(matches[0])) == set(REQUIRED_SQS_ACTIONS)
        assert _statement_resources(matches[0]) == [queues["expected_active_queue_arn"]]

    def test_policy_avoids_notaction_notresource_and_mixed_queue_resources(self):
        """Policy repair fails closed rather than hiding breadth in inverse IAM fields."""
        queues = load_json(APP / "config" / "queues.json")
        policy = load_json(APP / "config" / "lambda_role_policy.json")
        for st in policy["Statement"]:
            assert "NotAction" not in st and "NotResource" not in st
            resources = _statement_resources(st)
            assert not (queues["old_queue_arn"] in resources and queues["expected_active_queue_arn"] in resources)
