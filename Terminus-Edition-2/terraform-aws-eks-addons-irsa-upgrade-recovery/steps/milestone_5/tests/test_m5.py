import json
import os
import re
import subprocess
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


def braced_assignment(text, name):
    """Return one named HCL map entry using balanced braces."""
    key_pattern = rf'(?:"{re.escape(name)}"|{re.escape(name)})\s*=\s*\{{'
    match = re.search(key_pattern, text)
    assert match, f"{name} map entry not found"
    opening = text.find("{", match.start())
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[opening + 1 : index]
    raise AssertionError(f"unbalanced braces in {name} map entry")


def extract_braced_block(text, opener_pattern, label):
    """Return one balanced HCL block starting at opener_pattern."""
    match = re.search(opener_pattern, text)
    assert match, f"{label} block not found"
    opening = text.find("{", match.start())
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[opening : index + 1]
    raise AssertionError(f"unbalanced braces in {label}")


class TestMilestone5:
    def test_terraform_recovery_state(self):
        """Terraform reflects cumulative recovery; plan.json edits alone cannot pass."""
        eks = read("eks.tf")
        assert re.search(r"cluster_endpoint_public_access\s*=\s*false", eks)
        assert re.search(r"cluster_endpoint_private_access\s*=\s*true", eks)
        assert re.search(r"subnet_ids\s*=\s*var\.private_subnet_ids", eks)
        node_groups = braced_assignment(eks, "eks_managed_node_groups")
        for group in ["system", "apps", "batch"]:
            assert group in node_groups, f"node group '{group}' missing from eks.tf"
        assert not re.search(r"\bdefault\s*=\s*\{", node_groups)

        text = all_tf()
        assert re.search(r'addon_version\s*=\s*"(?!latest)', text, re.I), (
            "add-on versions must be pinned"
        )
        assert re.search(r'resolve_conflicts_on_update\s*=\s*"PRESERVE"', text), (
            "resolve_conflicts must be PRESERVE"
        )

        assert (
            'resource "aws_iam_role_policy_attachment" "node_addon_admin"'
            not in text
        )
        assert "AdministratorAccess" not in text
        assert (
            "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
            in text
        )
        moved = extract_braced_block(read("outputs.tf"), r"moved\s*\{", "moved")
        assert "from = aws_iam_role_policy_attachment.node_addon_admin" in moved
        assert re.search(r"to\s*=\s*module\.ebs_csi_irsa", moved)
        karpenter = read("karpenter.tf")
        assert re.search(r"name:\s*regulated-on-demand", karpenter)
        assert re.search(
            r'resource\s+"aws_sqs_queue".*karpenter-interruption',
            karpenter,
            re.DOTALL,
        )
        regulated_section = karpenter.split("regulated-on-demand", 1)[1]
        regulated_section = regulated_section.split("NodePool", 1)[0]
        assert "on-demand" in regulated_section
        assert "spot" not in regulated_section.lower()
        outputs = read("outputs.tf")
        for name in REQUIRED_OUTPUTS:
            assert f'output "{name}"' in outputs
            block = extract_output_block(outputs, name)
            assert output_has_real_value(block), (
                f"output {name} must reference module or var"
            )

    def test_plan_guard_passes(self):
        """Run the Go plan guard and verify it accepts the final upgrade plan.

        The guard checks protected resources, broad admin policy removal, and
        all required legacy outputs in the offline Terraform plan fixture.
        """
        result = subprocess.run(
            [str(APP / "scripts/plan_guard")],
            cwd=APP,
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        assert json.loads(result.stdout)["ok"] is True

    def test_plan_no_admin_or_protected_replacement(self):
        """Plan avoids broad node admin attachments and protected replacements."""
        plan_path = APP / "fixtures/plan.json"
        plan_text = plan_path.read_text(encoding="utf-8")
        assert "AdministratorAccess" not in plan_text
        plan = json.loads(plan_text)
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
