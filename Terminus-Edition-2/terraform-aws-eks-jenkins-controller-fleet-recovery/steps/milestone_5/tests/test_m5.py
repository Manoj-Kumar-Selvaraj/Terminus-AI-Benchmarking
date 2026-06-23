import json
import os
from pathlib import Path

APP = Path(os.environ.get("APP_ROOT", "/app"))
TF = APP / "terraform"


def read(name):
    return (TF / name).read_text(encoding="utf-8")


def all_tf():
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(TF.glob("*.tf")))


class TestMilestone5:
    def test_restrictions(self):
        """Final restrictions enforce internal mirror and disable risky features."""
        restrictions = json.loads(read("restrictions.json"))
        assert restrictions.get("plugin_source") == "internal-mirror"
        assert restrictions.get("script_console_enabled") is False
        assert restrictions.get("controller_to_controller_job_trigger") is False
        approved = {
            "configuration-as-code",
            "kubernetes",
            "workflow-aggregator",
            "job-dsl",
            "git",
            "credentials",
            "matrix-auth",
            "cloudbees-casc-client",
        }
        assert approved <= set(restrictions.get("approved_plugin_ids", []))

    def test_plan_outputs_no_replacement(self):
        """Plan fixture keeps outputs and avoids replacing protected resources."""
        plan = json.loads((APP / "fixtures/terraform_plan.json").read_text())
        protected = {
            "module.eks.aws_eks_cluster.this[0]",
            "helm_release.joc",
            "helm_release.payments_controller",
            "helm_release.risk_controller",
            "helm_release.platform_controller",
        }
        present = {change.get("address") for change in plan.get("resource_changes", [])}
        assert protected <= present, "Protected resources missing from plan"
        for change in plan.get("resource_changes", []):
            if change.get("address") not in protected:
                continue
            actions = change.get("change", {}).get("actions", [])
            assert "delete" not in actions
            assert actions != ["delete", "create"]
            assert "create" not in actions
        for output in [
            "joc_hostname",
            "joc_url",
            "controller_names",
            "jenkins_namespace",
            "irsa_role_arns",
        ]:
            assert output in plan.get("output_changes", {})
            assert plan["output_changes"][output].get("actions") != ["delete"]
            assert f'output "{output}"' in read("outputs.tf")
