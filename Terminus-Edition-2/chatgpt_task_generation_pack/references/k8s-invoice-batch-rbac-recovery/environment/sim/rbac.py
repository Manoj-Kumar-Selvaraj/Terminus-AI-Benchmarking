from __future__ import annotations

from typing import Any


CORE_API_GROUP = ""


def resolve_role_for_service_account(
    sa_name: str,
    sa_namespace: str,
    rolebindings: list[dict[str, Any]],
    roles: list[dict[str, Any]],
) -> dict[str, Any] | None:
    role_name = None
    for binding in rolebindings:
        if binding.get("metadata", {}).get("namespace") != sa_namespace:
            continue
        role_ref = binding.get("roleRef", {})
        if role_ref.get("kind") != "Role":
            continue
        for subject in binding.get("subjects", []):
            if subject.get("kind") != "ServiceAccount":
                continue
            subject_ns = subject.get("namespace", sa_namespace)
            if subject.get("name") == sa_name and subject_ns == sa_namespace:
                role_name = role_ref.get("name")
                break
        if role_name:
            break
    if not role_name:
        return None
    for role in roles:
        meta = role.get("metadata", {})
        if meta.get("name") == role_name and meta.get("namespace") == sa_namespace:
            return role
    return None


def rule_matches(rule: dict[str, Any], api_group: str, resource: str, verb: str) -> bool:
    api_groups = rule.get("apiGroups", [])
    resources = rule.get("resources", [])
    verbs = rule.get("verbs", [])
    group_ok = "*" in api_groups or api_group in api_groups
    resource_ok = "*" in resources or resource in resources
    verb_ok = "*" in verbs or verb in verbs
    return group_ok and resource_ok and verb_ok


def role_allows(role: dict[str, Any] | None, api_group: str, resource: str, verb: str) -> bool:
    if role is None:
        return False
    for rule in role.get("rules", []):
        if rule_matches(rule, api_group, resource, verb):
            return True
    return False


def evaluate_configmap_read(
    sa_name: str,
    sa_namespace: str,
    configmap_name: str,
    bundle: dict[str, Any],
) -> dict[str, Any]:
    role = resolve_role_for_service_account(
        sa_name,
        sa_namespace,
        bundle["rolebindings"],
        bundle["roles"],
    )
    allowed = role_allows(role, CORE_API_GROUP, "configmaps", "get")
    return {
        "service_account": sa_name,
        "namespace": sa_namespace,
        "configmap": configmap_name,
        "authorized": allowed,
        "reason": None if allowed else "Forbidden: cannot get configmaps",
        "bound_role": None if role is None else role.get("metadata", {}).get("name"),
    }


def collect_role_permissions(role: dict[str, Any] | None) -> list[dict[str, Any]]:
    if role is None:
        return []
    normalized: list[dict[str, Any]] = []
    for rule in role.get("rules", []):
        normalized.append(
            {
                "apiGroups": list(rule.get("apiGroups", [])),
                "resources": list(rule.get("resources", [])),
                "verbs": list(rule.get("verbs", [])),
            }
        )
    return normalized


def has_wildcard_permission(permissions: list[dict[str, Any]]) -> bool:
    for rule in permissions:
        if "*" in rule.get("apiGroups", []):
            return True
        if "*" in rule.get("resources", []):
            return True
        if "*" in rule.get("verbs", []):
            return True
    return False


def permissions_cover_workflow(permissions: list[dict[str, Any]]) -> bool:
    needs = [
        (CORE_API_GROUP, "configmaps", "get"),
        (CORE_API_GROUP, "secrets", "create"),
    ]
    for api_group, resource, verb in needs:
        if not any(rule_matches(rule, api_group, resource, verb) for rule in permissions):
            return False
    return True


def permissions_are_minimal(permissions: list[dict[str, Any]]) -> bool:
    allowed_resources = {"configmaps", "secrets"}
    forbidden_verbs = {
        "delete",
        "deletecollection",
        "escalate",
        "bind",
        "impersonate",
        "patch",
        "update",
        "list",
        "watch",
    }
    if has_wildcard_permission(permissions):
        return False
    if not permissions_cover_workflow(permissions):
        return False
    for rule in permissions:
        resources = set(rule.get("resources", []))
        if not resources.issubset(allowed_resources):
            return False
        verbs = set(rule.get("verbs", []))
        if verbs & forbidden_verbs:
            return False
        if "configmaps" in resources and verbs - {"get"}:
            return False
        if "secrets" in resources and not {"create", "get"}.issuperset(verbs):
            return False
    return True
