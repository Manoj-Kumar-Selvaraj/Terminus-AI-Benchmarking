import json
import os
import re
import subprocess
import sys
from pathlib import Path

APP = Path(os.environ.get("APP_ROOT", "/app"))
TF = APP / "terraform"

PROTECTED_RESOURCES = {
    "module.eks.aws_eks_cluster.this[0]",
    "module.eks.aws_security_group.cluster[0]",
    'module.eks.aws_eks_node_group.this["system"]',
    'module.eks.aws_eks_node_group.this["apps"]',
    'module.eks.aws_eks_node_group.this["batch"]',
}

REQUIRED_OUTPUTS = [
    "cluster_endpoint",
    "cluster_security_group_id",
    "oidc_provider_arn",
    "private_subnet_ids",
    "managed_node_group_names",
    "addon_irsa_role_arns",
]


def read(name):
    return (TF / name).read_text(encoding="utf-8")


def all_tf():
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(TF.glob("*.tf")))


def extract_output_block(outputs_text, name):
    pattern = rf'output\s+"{re.escape(name)}"\s*\{{'
    match = re.search(pattern, outputs_text)
    assert match, f"output block for {name} not found"
    start = match.start()
    depth = 0
    for index in range(match.end() - 1, len(outputs_text)):
        char = outputs_text[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return outputs_text[start : index + 1]
    raise AssertionError(f"unbalanced braces in output {name}")


def output_has_real_value(block):
    value_part = block.split("value", 1)[1] if "value" in block else ""
    return bool(re.search(r"module\.|var\.|keys\(module\.", value_part))


class TestMilestone5:
    def test_terraform_recovery_state(self):
        """Terraform reflects cumulative recovery; plan.json edits alone cannot pass."""
        eks = read("eks.tf")
        assert re.search(r"cluster_endpoint_public_access\s*=\s*false", eks)
        assert re.search(r"cluster_endpoint_private_access\s*=\s*true", eks)
        assert "subnet_ids = var.private_subnet_ids" in eks or (
            "subnet_ids      = var.private_subnet_ids" in eks
        )
        text = all_tf()
        assert 'resource "aws_iam_role_policy_attachment" "node_addon_admin"' not in text
        assert "AdministratorAccess" not in text
        assert (
            "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
            in text
        )
        outputs = read("outputs.tf")
        for name in REQUIRED_OUTPUTS:
            assert f'output "{name}"' in outputs
            block = extract_output_block(outputs, name)
            assert output_has_real_value(block), (
                f"output {name} must reference module or var"
            )

    def test_plan_guard_passes(self):
        """Offline plan guard accepts the final non-destructive upgrade plan."""
        result = subprocess.run(
            [sys.executable, str(APP / "scripts/plan_guard.py")],
            cwd=APP,
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        assert json.loads(result.stdout)["ok"] is True

    def test_plan_no_admin_or_protected_replacement(self):
        """Plan avoids broad node admin attachments and protected replacements."""
        plan = json.loads((APP / "fixtures/plan.json").read_text())
        seen_protected = set()
        for change in plan.get("resource_changes", []):
            actions = change.get("change", {}).get("actions", [])
            address = change.get("address", "")
            assert not ("node_addon_admin" in address and "create" in actions)
            if address not in PROTECTED_RESOURCES:
                continue
            seen_protected.add(address)
            assert actions
            assert set(actions) <= {"no-op", "read", "update"}
        assert seen_protected == PROTECTED_RESOURCES
        root_outputs = (
            plan.get("configuration", {}).get("root_module", {}).get("outputs", {})
        )
        for output in REQUIRED_OUTPUTS:
            assert output in root_outputs
