import os
import re
from pathlib import Path

APP = Path(os.environ.get("APP_ROOT", "/app"))
TF = APP / "terraform"


def read(name):
    return (TF / name).read_text(encoding="utf-8")


def all_tf():
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(TF.glob("*.tf")))


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


class TestMilestone1:
    def test_eks_module_version_and_identity_preserved(self):
        """EKS module keeps its pinned version and cluster_name reference."""
        text = read("eks.tf")
        assert re.search(r'version\s*=\s*"20\.0\.0"', text), (
            "EKS module version pin must be preserved"
        )
        assert re.search(r"cluster_name\s*=\s*var\.cluster_name", text), (
            "cluster_name must reference var.cluster_name"
        )

    def test_unrelated_terraform_files_preserved(self):
        """Later-milestone Terraform files must remain present."""
        for filename in ["addons.tf", "karpenter.tf", "outputs.tf", "variables.tf"]:
            assert (TF / filename).is_file(), f"{filename} must be preserved"

    def test_private_endpoint_private_subnets(self):
        """EKS module stays private and uses private subnets."""
        text = read("eks.tf")
        assert "terraform-aws-modules/eks/aws" in text
        assert re.search(r"cluster_endpoint_public_access\s*=\s*false", text)
        assert re.search(r"cluster_endpoint_private_access\s*=\s*true", text)
        assert re.search(r"subnet_ids\s*=\s*var\.private_subnet_ids", text)

    def test_split_node_groups(self):
        """Node groups are split into system, apps, and batch with system tainting."""
        text = read("eks.tf")
        node_groups = braced_assignment(text, "eks_managed_node_groups")
        for group in ["system", "apps", "batch"]:
            group_block = braced_assignment(node_groups, group)
            assert re.search(rf'nodepool\s*=\s*"{group}"', group_block), (
                f"nodepool label missing for {group}"
            )
        system = braced_assignment(node_groups, "system")
        assert re.search(r'key\s*=\s*"CriticalAddonsOnly"', system)
        assert re.search(r'value\s*=\s*"true"', system)
        assert re.search(r'effect\s*=\s*"(?:NO_SCHEDULE|NoSchedule)"', system)
        assert not re.search(r"\bdefault\s*=\s*\{", node_groups)
