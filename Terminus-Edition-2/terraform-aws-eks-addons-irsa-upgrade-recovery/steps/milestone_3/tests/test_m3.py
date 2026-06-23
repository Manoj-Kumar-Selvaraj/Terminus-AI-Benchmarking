import json
import os
import re
from pathlib import Path

APP = Path(os.environ.get("APP_ROOT", "/app"))
TF = APP / "terraform"


def read(name):
    return (TF / name).read_text(encoding="utf-8")


def all_tf():
    return "\n".join(p.read_text(encoding="utf-8") for p in sorted(TF.glob("*.tf")))


def regulated_on_demand_block(text):
    """Return the complete regulated manifest resource, not a YAML fragment."""
    match = re.search(
        r'resource\s+"kubectl_manifest"\s+"karpenter_regulated_nodepool"\s*\{',
        text,
    )
    assert match, "regulated Karpenter manifest resource not found"
    end = text.find("\nYAML", match.end())
    assert end != -1, "regulated Karpenter heredoc terminator not found"
    return text[match.start() : end]


class TestMilestone3:
    def test_karpenter_private_interruption_selectors(self):
        """Karpenter uses an interruption queue and private cluster-owned selectors."""
        text = read("karpenter.tf")
        assert "aws_sqs_queue" in text
        assert "karpenter-interruption" in text
        assert (
            "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
            in text
        )
        assert "karpenter.sh/discovery" in text
        assert "subnetSelectorTerms" in text
        assert "securityGroupSelectorTerms" in text
        assert "subnet-public" not in text.lower()

    def test_regulated_on_demand_only(self):
        """Regulated workloads use regulated-on-demand and never spot/default."""
        text = read("karpenter.tf")
        block = regulated_on_demand_block(text)
        assert "regulated-on-demand" in text
        assert "karpenter.sh/capacity-type" in block
        assert "on-demand" in block
        assert "spot" not in block.lower()
        report = json.loads((APP / "fixtures/scheduling_report.json").read_text())
        assert isinstance(report, dict)
        workloads = report.get("regulated_workloads", [])
        assert isinstance(workloads, list)
        assert len(workloads) >= 1, "regulated workload evidence deleted"
        for workload in workloads:
            assert isinstance(workload, dict)
            assert isinstance(workload.get("name"), str) and workload["name"].strip()
            assert workload.get("capacity_type") == "on-demand"
            assert workload.get("nodepool") == "regulated-on-demand"
        assert isinstance(report.get("addon_pods"), list)
