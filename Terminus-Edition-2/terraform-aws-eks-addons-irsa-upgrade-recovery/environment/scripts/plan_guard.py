#!/usr/bin/env python3
import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
plan = json.loads((root / "fixtures/plan.json").read_text())
protected = {
    "module.eks.aws_eks_cluster.this[0]",
    "module.eks.aws_security_group.cluster[0]",
    'module.eks.aws_eks_node_group.this["system"]',
    'module.eks.aws_eks_node_group.this["apps"]',
    'module.eks.aws_eks_node_group.this["batch"]',
}
violations = []
seen_protected = set()
admin_creates = []
for change in plan.get("resource_changes", []):
    actions = change.get("change", {}).get("actions", [])
    address = change.get("address", "")
    if "node_addon_admin" in address and "create" in actions:
        admin_creates.append(change)
    if address not in protected:
        continue
    seen_protected.add(address)
    if not isinstance(actions, list) or not actions or not set(actions) <= {
        "no-op",
        "read",
        "update",
    }:
        violations.append(change)

missing_protected = sorted(protected - seen_protected)
if violations or admin_creates or missing_protected:
    print(
        json.dumps(
            {
                "ok": False,
                "violations": violations,
                "admin_creates": admin_creates,
                "missing_protected": missing_protected,
            }
        ),
        file=sys.stderr,
    )
    sys.exit(2)

outputs = plan.get("configuration", {}).get("root_module", {}).get("outputs", {})
required = {
    "cluster_endpoint",
    "cluster_security_group_id",
    "oidc_provider_arn",
    "private_subnet_ids",
    "managed_node_group_names",
    "addon_irsa_role_arns",
}
missing = sorted(required - set(outputs))
if missing:
    print(json.dumps({"ok": False, "missing_outputs": missing}), file=sys.stderr)
    sys.exit(3)

print(json.dumps({"ok": True}))
