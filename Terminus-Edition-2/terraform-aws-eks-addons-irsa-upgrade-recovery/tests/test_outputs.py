import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import yaml

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

CORE_ADDONS = ["vpc-cni", "coredns", "kube-proxy", "aws-ebs-csi-driver"]


def strip_hcl_comments(text):
    cleaned = []
    in_heredoc = False
    marker = None
    for line in text.splitlines():
        if in_heredoc:
            cleaned.append(line)
            if line.strip() == marker:
                in_heredoc = False
                marker = None
            continue
        match = re.search(r"<<-?(\w+)", line)
        if match:
            in_heredoc = True
            marker = match.group(1)
            cleaned.append(line)
            continue
        stripped = line.strip()
        if stripped.startswith("#") or stripped.startswith("//"):
            continue
        cleaned.append(re.sub(r"\s+#.*$", "", re.sub(r"\s+//.*$", "", line)))
    return "\n".join(cleaned)


def read(name):
    return strip_hcl_comments((TF / name).read_text(encoding="utf-8"))


def all_tf():
    return "\n".join(read(p.name) for p in sorted(TF.glob("*.tf")))


def assert_balanced_hcl(text, filename):
    depth = 0
    for char in text:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            assert depth >= 0, f"unexpected closing brace in {filename}"
    assert depth == 0, f"unbalanced braces in {filename}"


def extract_braced_block(text, opener_pattern, label):
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
                return text[opening:index + 1]
    raise AssertionError(f"unbalanced braces in {label}")


def braced_assignment(text, name):
    key_pattern = rf'(?:("{re.escape(name)}")|{re.escape(name)})\s*=\s*\{{'
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
                return text[opening + 1:index]
    raise AssertionError(f"unbalanced braces in {name} map entry")


def cluster_addons_block(text):
    eks_block = extract_braced_block(text, r'module\s+"eks"\s*\{', "eks module")
    assert re.search(r"cluster_addons\s*=", eks_block), (
        "cluster_addons must be connected to the EKS module"
    )
    if re.search(r"cluster_addons\s*=\s*local\.cluster_addons", eks_block):
        locals_block = extract_braced_block(text, r"\blocals\s*\{", "locals")
        return braced_assignment(locals_block, "cluster_addons")
    return braced_assignment(eks_block, "cluster_addons")


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
                return outputs_text[start:index + 1]
    raise AssertionError(f"unbalanced braces in output {name}")


def output_has_real_value(block):
    value_part = block.split("value", 1)[1] if "value" in block else ""
    return bool(re.search(r"module\.|var\.|keys\(module\.", value_part))


def role_arn_values(text):
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
    addons = cluster_addons_block(text)
    block = braced_assignment(addons, addon_name)
    match = re.search(r"service_account_role_arn\s*=\s*(\S+)", block)
    return match.group(1).strip('"') if match else None


def helm_release_role_arn(text, release_name):
    block = extract_braced_block(
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


def regulated_manifest_block(text):
    pattern = r'resource\s+"kubectl_manifest"\s+"karpenter_regulated_nodepool"\s*\{'
    match = re.search(pattern, text)
    assert match, "regulated Karpenter manifest resource not found"
    end_match = re.search(r"\n\s*YAML\b", text[match.end():])
    assert end_match, "regulated Karpenter YAML heredoc not found"
    end = match.end() + end_match.end()
    return text[match.start():end]


def parse_regulated_documents(text):
    block = regulated_manifest_block(text)
    yaml_match = re.search(r"<<-?YAML\n(.*?)\n\s*YAML\b", block, re.DOTALL)
    assert yaml_match, "regulated Karpenter YAML heredoc not found"
    documents = []
    for doc in yaml.safe_load_all(yaml_match.group(1)):
        if not doc:
            continue
        if isinstance(doc, list):
            documents.extend(doc)
        elif doc.get("kind") == "List":
            documents.extend(doc.get("items", []))
        else:
            documents.append(doc)
    return documents


class TestEksAddonsIrsaUpgradeRecovery:
    def test_hcl_syntax_is_valid(self):
        env = os.environ.copy()
        env.setdefault("APP_ROOT", "/app")
        if not shutil.which("terraform"):
            for path in sorted((Path(env["APP_ROOT"]) / "terraform").glob("*.tf")):
                assert_balanced_hcl(path.read_text(encoding="utf-8"), path.name)
            return
        result = subprocess.run(
            ["terraform", "fmt", "-recursive", "-write=false", "-list=false"],
            cwd=Path(env["APP_ROOT"]) / "terraform",
            text=True,
            capture_output=True,
            env=env,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    def test_private_cluster_and_node_groups_are_recovered(self):
        eks = read("eks.tf")
        assert re.search(r'version\s*=\s*"20\.0\.0"', eks)
        assert re.search(r"cluster_name\s*=\s*var\.cluster_name", eks)
        assert re.search(r"cluster_endpoint_public_access\s*=\s*false", eks)
        assert re.search(r"cluster_endpoint_private_access\s*=\s*true", eks)
        assert re.search(r"subnet_ids\s*=\s*var\.private_subnet_ids", eks)
        node_groups = braced_assignment(eks, "eks_managed_node_groups")
        for group in ["system", "apps", "batch"]:
            group_block = braced_assignment(node_groups, group)
            assert re.search(rf'nodepool\s*=\s*"{group}"', group_block)
        system = braced_assignment(node_groups, "system")
        assert re.search(r'key\s*=\s*"CriticalAddonsOnly"', system)
        assert re.search(r'value\s*=\s*"true"', system)
        assert re.search(r'effect\s*=\s*"(?:NO_SCHEDULE|NoSchedule)"', system)
        assert not re.search(r"\bdefault\s*=\s*\{", node_groups)

    def test_addon_irsa_boundaries_are_recovered(self):
        text = all_tf()
        addons = cluster_addons_block(text)
        for addon in CORE_ADDONS:
            block = braced_assignment(addons, addon)
            assert re.search(r'addon_version\s*=\s*"(?!latest)[^"]+"', block, re.I)
            assert re.search(r'resolve_conflicts_on_update\s*=\s*"PRESERVE"', block)

        expected_roles = {
            "ebs_csi_irsa": "kube-system:ebs-csi-controller-sa",
            "alb_controller_irsa": "kube-system:aws-load-balancer-controller",
        }
        for module, service_account in expected_roles.items():
            block = extract_braced_block(text, rf'module\s+"{module}"\s*\{{', module)
            assert "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks" in block
            assert re.search(r'version\s*=\s*"[^"]+"', block)
            assert service_account in block

        role_arns = role_arn_values(text)
        for value in role_arns:
            assert value and value not in {'""', "''"}
            assert "module." in value or "aws_iam_role." in value
        ebs_role_arn = addon_service_account_role_arn(text, "aws-ebs-csi-driver")
        if not ebs_role_arn:
            ebs_role_arn = next((value for value in role_arns if "ebs_csi_irsa" in value), None)
        alb_role_arn = helm_release_role_arn(text, "aws_load_balancer_controller")
        if not alb_role_arn:
            alb_role_arn = next((value for value in role_arns if "alb_controller_irsa" in value), None)
        assert ebs_role_arn and "module.ebs_csi_irsa" in ebs_role_arn
        assert alb_role_arn and "module.alb_controller_irsa" in alb_role_arn
        assert "AdministratorAccess" not in text
        assert "node_addon_admin" not in read("addons.tf")
        assert 'resource "aws_iam_role_policy_attachment" "node_addon_admin"' not in text
        assert not re.search(r'Resource\s*=\s*"\*"', text)
        assert not re.search(r'Action\s*=\s*"\*"', text)
        assert not re.search(r'["\']Resource["\']\s*[:=]\s*["\']\*', text)
        assert not re.search(r'["\']Action["\']\s*[:=]\s*["\']\*', text)

    def test_regulated_karpenter_placement_is_recovered(self):
        text = read("karpenter.tf")
        sqs_block = extract_braced_block(text, r'resource\s+"aws_sqs_queue"\s+"[^"]+"\s*\{', "aws_sqs_queue")
        assert re.search(r"\bname(?:_prefix)?\s*=", sqs_block)
        karpenter_irsa = extract_braced_block(text, r'module\s+"karpenter_irsa"\s*\{', "karpenter_irsa")
        assert "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks" in karpenter_irsa
        assert re.search(r'role_name\s*=\s*"[^"]+"', karpenter_irsa)
        assert "karpenter:karpenter" in karpenter_irsa

        documents = parse_regulated_documents(text)
        nodepool = next(doc for doc in documents if doc.get("kind") == "NodePool")
        node_class = next(doc for doc in documents if doc.get("kind") == "EC2NodeClass")
        assert nodepool["metadata"]["name"] == "regulated-on-demand"
        assert "subnetSelectorTerms" in node_class["spec"]
        assert "securityGroupSelectorTerms" in node_class["spec"]
        for term_key in ("subnetSelectorTerms", "securityGroupSelectorTerms"):
            terms = node_class["spec"][term_key]
            tags = [term.get("tags", {}) for term in terms]
            assert any("karpenter.sh/discovery" in tag_map for tag_map in tags)
        assert "subnet-public" not in json.dumps(node_class["spec"]).lower()

        node_class_ref = nodepool["spec"]["template"]["spec"]["nodeClassRef"]
        assert node_class_ref["name"] != "default"
        assert node_class_ref["name"] == node_class["metadata"]["name"]
        requirements = nodepool["spec"]["template"]["spec"]["requirements"]
        cap_req = [req for req in requirements if req["key"] == "karpenter.sh/capacity-type"]
        assert len(cap_req) == 1
        assert cap_req[0]["operator"] == "In"
        assert cap_req[0]["values"] == ["on-demand"]
        assert "spot" not in regulated_manifest_block(text).lower()

    def test_scheduling_report_preserves_regulated_evidence(self):
        report = json.loads((APP / "fixtures/scheduling_report.json").read_text())
        assert isinstance(report, dict)
        workloads = report.get("regulated_workloads", [])
        assert isinstance(workloads, list)
        assert workloads, "regulated workload evidence deleted"
        workload_names = []
        for workload in workloads:
            assert isinstance(workload, dict)
            assert isinstance(workload.get("name"), str) and workload["name"].strip()
            workload_names.append(workload["name"])
            assert workload.get("capacity_type") == "on-demand"
            assert workload.get("nodepool") == "regulated-on-demand"
        assert "settlement-ledger" in workload_names
        assert isinstance(report.get("addon_pods"), list)

    def test_outputs_and_moved_metadata_are_recovered(self):
        text = all_tf()
        assert re.search(r'version\s*=\s*"20\.0\.0"', text)
        outputs = read("outputs.tf")
        addons = read("addons.tf")
        assert not re.search(r"\bmoved\s*\{", addons)
        assert "cluster_endpoint_url" not in outputs
        for name in REQUIRED_OUTPUTS:
            block = extract_output_block(outputs, name)
            assert output_has_real_value(block), f"output {name} must reference module or var"
            assert 'value = ""' not in block and "value = ''" not in block
        role_block = extract_output_block(outputs, "addon_irsa_role_arns")
        value_part = role_block.split("value", 1)[1]
        for role in ["ebs_csi", "load_balancer", "karpenter"]:
            assert re.search(rf"{role}\s*=\s*module\.\w+", value_part, re.I)
        moved = extract_braced_block(outputs, r"moved\s*\{", "moved")
        assert "from = aws_iam_role_policy_attachment.node_addon_admin" in moved
        assert re.search(r"to\s*=\s*module\.ebs_csi_irsa", moved)

    def test_plan_guard_passes(self):
        result = subprocess.run(
            [str(APP / "scripts/plan_guard")],
            cwd=APP,
            text=True,
            capture_output=True,
        )
        assert result.returncode == 0, result.stderr + result.stdout
        assert json.loads(result.stdout)["ok"] is True

    def test_plan_no_admin_or_protected_replacement(self):
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
        root_outputs = plan.get("configuration", {}).get("root_module", {}).get("outputs", {})
        for output in REQUIRED_OUTPUTS:
            assert output in root_outputs
