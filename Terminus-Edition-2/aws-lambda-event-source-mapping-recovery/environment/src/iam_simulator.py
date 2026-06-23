from __future__ import annotations
import fnmatch
from typing import Any

def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]

def _matches(patterns: list[str], value: str) -> bool:
    return any(fnmatch.fnmatchcase(value, pattern) for pattern in patterns)

def decide(policy: dict[str, Any], action: str, resource: str) -> str:
    decision = "implicitDeny"
    for statement in policy.get("Statement", []):
        actions = _as_list(statement.get("Action"))
        resources = _as_list(statement.get("Resource"))
        if _matches(actions, action) and _matches(resources, resource):
            if statement.get("Effect") == "Deny":
                return "explicitDeny"
            if statement.get("Effect") == "Allow":
                decision = "allowed"
    return decision

def required_sqs_decisions(policy: dict[str, Any], queue_arn: str) -> dict[str, str]:
    actions = ["sqs:ReceiveMessage", "sqs:DeleteMessage", "sqs:ChangeMessageVisibility", "sqs:GetQueueAttributes"]
    return {action: decide(policy, action, queue_arn) for action in actions}

def has_broad_sqs_grant(policy: dict[str, Any]) -> bool:
    for statement in policy.get("Statement", []):
        if statement.get("Effect") != "Allow":
            continue
        actions = _as_list(statement.get("Action"))
        resources = _as_list(statement.get("Resource"))
        if any(a in {"*", "sqs:*"} for a in actions):
            return True
        if any(r == "*" for r in resources) and any(a.startswith("sqs:") or a == "*" for a in actions):
            return True
    return False

def has_log_permissions(policy: dict[str, Any]) -> bool:
    needed = ["logs:CreateLogStream", "logs:PutLogEvents"]
    return all(any(statement.get("Effect") == "Allow" and _matches(_as_list(statement.get("Action")), action) for statement in policy.get("Statement", [])) for action in needed)
