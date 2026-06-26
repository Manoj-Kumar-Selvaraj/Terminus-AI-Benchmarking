import json
import os
import re
from pathlib import Path

import yaml

APP = Path(os.environ.get("APP_ROOT", "/app"))
TF = APP / "terraform"


def read(name):
    return (TF / name).read_text(encoding="utf-8")


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


REGULATED_NODEPOOL_RESOURCE = "karpenter_regulated_nodepool"


def kubectl_manifest_blocks(text):
    """Return (resource_name, block) pairs for kubectl_manifest resources."""
    blocks = []
    pattern = r'resource\s+"kubectl_manifest"\s+"([^"]+)"\s*\{'
    for match in re.finditer(pattern, text):
        end = text.find("\nYAML", match.end())
        if end == -1:
            continue
        blocks.append(
            (match.group(1), text[match.start() : end + len("\nYAML")])
        )
    return blocks


def regulated_manifest_block(text):
    """Return the complete regulated Karpenter manifest resource."""
    for resource_name, block in kubectl_manifest_blocks(text):
        if resource_name == REGULATED_NODEPOOL_RESOURCE:
            return block
    assert False, (
        'resource label must be karpenter_regulated_nodepool'
    )


def parse_manifest_documents(text, resource_name=REGULATED_NODEPOOL_RESOURCE):
    """Parse YAML documents from the regulated kubectl_manifest heredoc."""
    block = regulated_manifest_block(text)
    yaml_match = re.search(r"<<-?YAML\n(.*?)\nYAML", block, re.DOTALL)
    assert yaml_match, f"{resource_name} YAML heredoc not found"
    return list(yaml.safe_load_all(yaml_match.group(1)))


class TestMilestone3:
    def test_karpenter_private_interruption_selectors(self):
        """Karpenter uses an interruption queue and private cluster-owned selectors."""
        text = read("karpenter.tf")
        sqs_block = braced_block(
            text,
            r'resource\s+"aws_sqs_queue"\s+"[^"]+"\s*\{',
            "aws_sqs_queue",
        )
        assert "karpenter-interruption" in sqs_block
        karpenter_irsa = braced_block(
            text,
            r'module\s+"karpenter_irsa"\s*\{',
            "karpenter_irsa",
        )
        assert (
            "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
            in karpenter_irsa
        )
        assert re.search(r'version\s*=\s*"[^"]+"', karpenter_irsa), (
            "karpenter_irsa must have a pinned version"
        )

        documents = parse_manifest_documents(text)
        nodepool = next(doc for doc in documents if doc.get("kind") == "NodePool")
        node_class = next(doc for doc in documents if doc.get("kind") == "EC2NodeClass")
        assert nodepool["metadata"]["name"] == "regulated-on-demand"
        assert "subnetSelectorTerms" in node_class["spec"]
        assert "securityGroupSelectorTerms" in node_class["spec"]
        for term_key in ("subnetSelectorTerms", "securityGroupSelectorTerms"):
            terms = node_class["spec"][term_key]
            tags = [term.get("tags", {}) for term in terms]
            assert any("karpenter.sh/discovery" in tag_map for tag_map in tags), (
                f"node class {term_key} must include karpenter.sh/discovery tag"
            )
        node_class_spec = json.dumps(node_class["spec"])
        assert "subnet-public" not in node_class_spec.lower()

        node_class_ref = nodepool["spec"]["template"]["spec"]["nodeClassRef"]
        assert node_class_ref["name"] != "default"
        assert node_class_ref["name"] == node_class["metadata"]["name"]

    def test_regulated_on_demand_only(self):
        """Regulated workloads use regulated-on-demand and never spot/default."""
        text = read("karpenter.tf")
        documents = parse_manifest_documents(text)
        nodepool = next(doc for doc in documents if doc.get("kind") == "NodePool")
        requirements = nodepool["spec"]["template"]["spec"]["requirements"]
        cap_req = [
            req
            for req in requirements
            if req["key"] == "karpenter.sh/capacity-type"
        ]
        assert len(cap_req) == 1
        assert cap_req[0]["operator"] == "In"
        assert cap_req[0]["values"] == ["on-demand"]
        regulated_block = regulated_manifest_block(text)
        assert "spot" not in regulated_block.lower(), (
            "spot must not appear anywhere in the regulated resource"
        )

        report = json.loads((APP / "fixtures/scheduling_report.json").read_text())
        assert isinstance(report, dict)
        workloads = report.get("regulated_workloads", [])
        assert isinstance(workloads, list)
        assert len(workloads) >= 1, "regulated workload evidence deleted"
        workload_names = []
        for workload in workloads:
            assert isinstance(workload, dict)
            assert isinstance(workload.get("name"), str) and workload["name"].strip()
            workload_names.append(workload["name"])
            assert workload.get("capacity_type") == "on-demand"
            assert workload.get("nodepool") == "regulated-on-demand"
        assert "settlement-ledger" in workload_names, (
            "regulated workload evidence renamed or removed"
        )
        assert isinstance(report.get("addon_pods"), list)
