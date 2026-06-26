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


def cluster_addons_block(text):
    """Return cluster_addons map content wired into module eks."""
    eks_block = braced_block(text, r'module\s+"eks"\s*\{', "eks module")
    assert re.search(r"cluster_addons\s*=", eks_block), (
        "cluster_addons must be connected to the EKS module"
    )
    if re.search(r"cluster_addons\s*=\s*local\.cluster_addons", eks_block):
        locals_block = braced_block(text, r"\blocals\s*\{", "locals")
        return braced_assignment(locals_block, "cluster_addons")
    return braced_assignment(eks_block, "cluster_addons")


def role_arn_values(text):
    """Collect non-empty eks.amazonaws.com/role-arn annotation values."""
    patterns = [
        r'eks\.amazonaws\.com/role-arn["\s]*=\s*([^\s}]+)',
        r'eks\\.amazonaws\\.com/role-arn"\s+value\s*=\s*([^\s}]+)',
        r'serviceAccount\.annotations\.eks\\.amazonaws\\.com/role-arn"\s+value\s*=\s*([^\s}]+)',
    ]
    values = []
    for pattern in patterns:
        values.extend(re.findall(pattern, text, re.DOTALL))
    for block in re.findall(r"set\s*\{[^}]*\}", text, re.DOTALL):
        if "role-arn" not in block:
            continue
        match = re.search(r"value\s*=\s*([^\s}]+)", block, re.DOTALL)
        if match:
            values.append(match.group(1))
    return [value.strip('"') for value in values if value and value not in {'""', "''"}]


def addon_service_account_role_arn(text, addon_name):
    """Return service_account_role_arn for a cluster addon entry."""
    addons = cluster_addons_block(text)
    block = braced_assignment(addons, addon_name)
    match = re.search(r"service_account_role_arn\s*=\s*(\S+)", block)
    return match.group(1).strip('"') if match else None


def helm_release_role_arn(text, release_name):
    """Return role-arn annotation value from a helm_release set block."""
    block = braced_block(
        text,
        rf'resource\s+"helm_release"\s+"{re.escape(release_name)}"\s*\{{',
        f"helm_release {release_name}",
    )
    for set_block in re.findall(r"set\s*\{[^}]*\}", block, re.DOTALL):
        if "role-arn" not in set_block:
            continue
        match = re.search(r"value\s*=\s*(\S+)", set_block, re.DOTALL)
        if match:
            return match.group(1).strip('"')
    return None


class TestMilestone2:
    def test_addons_pinned(self):
        """Core add-ons are declared with pinned versions and conflict handling."""
        text = all_tf()
        addons = cluster_addons_block(text)
        for addon in ["vpc-cni", "coredns", "kube-proxy", "aws-ebs-csi-driver"]:
            block = braced_assignment(addons, addon)
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
            assert re.search(r'version\s*=\s*"[^"]+"', block), (
                f"module {module} must have a pinned version"
            )
            assert service_account in block
        role_arns = role_arn_values(text)
        assert len(role_arns) >= 2, "role-arn annotations must be present"
        for value in role_arns:
            assert value and value not in {'""', "''"}, "role-arn must not be empty"
            assert "module." in value or "aws_iam_role." in value, (
                "role-arn must reference an actual IAM role resource"
            )
        ebs_role_arn = addon_service_account_role_arn(text, "aws-ebs-csi-driver")
        if not ebs_role_arn:
            for value in role_arns:
                if "ebs_csi_irsa" in value:
                    ebs_role_arn = value
                    break
        alb_role_arn = helm_release_role_arn(text, "aws_load_balancer_controller")
        if not alb_role_arn:
            for value in role_arns:
                if "alb_controller_irsa" in value:
                    alb_role_arn = value
                    break
        assert ebs_role_arn and "module.ebs_csi_irsa" in ebs_role_arn, (
            "EBS CSI must use module.ebs_csi_irsa role ARN"
        )
        assert alb_role_arn and "module.alb_controller_irsa" in alb_role_arn, (
            "ALB controller must use module.alb_controller_irsa role ARN"
        )
        assert not re.search(r'Resource\s*=\s*"\*"', text)
        assert not re.search(r'Action\s*=\s*"\*"', text)
