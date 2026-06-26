import os
import re
from pathlib import Path

APP = Path(os.environ.get("APP_ROOT", "/app"))
TF = APP / "terraform"

SA_RESOURCES = {
    "joc": "joc",
    "payments-controller": "payments_controller",
    "risk-controller": "risk_controller",
    "platform-controller": "platform_controller",
}


def read(name):
    return (TF / name).read_text(encoding="utf-8")


def all_tf():
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(TF.glob("*.tf")))


def hcl_has_resource_block(text):
    stripped = "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("#")
    )
    return 'resource "' in stripped


def resource_block(text, resource_type, resource_name):
    """Return one balanced Terraform resource body."""
    match = re.search(
        rf'resource\s+"{re.escape(resource_type)}"\s+"{re.escape(resource_name)}"\s*\{{',
        text,
    )
    assert match, f"{resource_type}.{resource_name} missing"
    opening = text.find("{", match.start())
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[opening + 1 : index]
    raise AssertionError(f"unbalanced resource {resource_type}.{resource_name}")


class TestMilestone2:
    def test_irsa_no_static_aws_keys(self):
        """Controllers use IRSA and no static AWS key secret remains."""
        text = all_tf().lower()
        service_accounts = read("service_accounts.tf")
        assert hcl_has_resource_block(service_accounts)
        assert "aws_access_key_id" not in text
        assert "aws_secret_access_key" not in text
        assert "kubernetes_secret" not in text or "aws_key" not in text
        assert (
            "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
            in service_accounts
        )
        for account_name, resource_name in SA_RESOURCES.items():
            block = resource_block(
                service_accounts, "kubernetes_service_account", resource_name
            )
            assert re.search(rf'name\s*=\s*"{re.escape(account_name)}"', block)
            assert "eks.amazonaws.com/role-arn" in block, (
                f"{account_name} service account missing IRSA annotation in its block"
            )

    def test_efs_persistent_home(self):
        """Jenkins home claims use encrypted EFS CSI storage with Retain."""
        storage = read("storage.tf")
        jenkins = read("jenkins.tf")
        assert hcl_has_resource_block(storage)
        assert "aws_efs_file_system" in storage
        assert re.search(r"encrypted\s*=\s*true", storage)
        assert "efs.csi.aws.com" in storage
        assert re.search(
            r'kubernetes_storage_class[\s\S]*?efs\.csi\.aws\.com[\s\S]*?reclaim_policy\s*=\s*"Retain"',
            storage,
        ), 'EFS CSI storage class must use reclaim_policy = "Retain"'
        claims = {
            "joc": "joc-home",
            "payments_controller": "payments-controller-home",
            "risk_controller": "risk-controller-home",
            "platform_controller": "platform-controller-home",
        }
        for release_name, claim in claims.items():
            assert claim in storage
            release = resource_block(jenkins, "helm_release", release_name)
            assert re.search(rf"existingClaim:\s*{re.escape(claim)}", release), (
                f"{claim} not set as existingClaim in helm release {release_name}"
            )
            account_name = release_name.replace("_", "-")
            assert re.search(
                rf"serviceAccount:\s*\n\s+name:\s*{re.escape(account_name)}|"
                rf"serviceAccountName:\s*{re.escape(account_name)}",
                release,
            ), f"{account_name} service account not bound in matching Helm values"
            if release_name != "joc":
                assert re.search(
                    r"tolerations:\s*\n\s*-\s+key:\s*dedicated[\s\S]*?"
                    r"(?:NoSchedule|NO_SCHEDULE)",
                    release,
                ), f"{release_name} must preserve milestone 1 scheduling tolerations"
        combined = (storage + "\n" + jenkins).lower()
        assert "emptydir" not in combined
        assert "hostpath" not in combined
