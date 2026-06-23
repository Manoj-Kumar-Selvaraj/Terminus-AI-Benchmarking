import os
import re
from pathlib import Path

APP = Path(os.environ.get("APP_ROOT", "/app"))
TF = APP / "terraform"


def read(name):
    return (TF / name).read_text(encoding="utf-8")


def all_tf():
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(TF.glob("*.tf")))


def braced_block(text, pattern, label):
    """Return the balanced HCL block beginning at pattern."""
    match = re.search(pattern, text)
    assert match, f"{label} block not found"
    opening = text.find("{", match.start())
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[opening + 1 : index]
    raise AssertionError(f"unbalanced braces in {label}")


class TestMilestone2:
    def test_addons_pinned(self):
        """Core add-ons are declared with pinned versions and conflict handling."""
        text = read("addons.tf") + "\n" + read("eks.tf")
        addons = braced_block(text, r"\bcluster_addons\s*=\s*\{", "cluster_addons")
        for addon in ["vpc-cni", "coredns", "kube-proxy", "aws-ebs-csi-driver"]:
            block = braced_block(
                addons,
                rf"(?:\b{re.escape(addon)}|\"{re.escape(addon)}\")\s*=\s*\{{",
                addon,
            )
            assert re.search(r'addon_version\s*=\s*"(?!latest)[^"]+"', block, re.I)
            assert re.search(
                r'resolve_conflicts_on_update\s*=\s*"PRESERVE"', block
            )

    def test_irsa_not_node_admin(self):
        """EBS CSI and ALB Controller use IRSA, not node administrator policy."""
        text = all_tf()
        assert "AdministratorAccess" not in text
        assert "node_addon_admin" not in text
        expected_roles = {
            "ebs_csi_irsa": "kube-system:ebs-csi-controller-sa",
            "alb_controller_irsa": "kube-system:aws-load-balancer-controller",
        }
        for module, service_account in expected_roles.items():
            block = braced_block(
                text,
                rf'module\s+"{module}"\s*\{{',
                module,
            )
            assert (
                "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
                in block
            )
            assert service_account in block
        assert text.count("eks.amazonaws.com/role-arn") >= 2
        assert 'Resource = "*"' not in text
        assert 'Action = "*"' not in text
