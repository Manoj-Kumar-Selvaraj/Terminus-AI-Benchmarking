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
    """Return one balanced Terraform block selected by pattern."""
    match = re.search(pattern, text)
    assert match, f"{label} block missing"

    opening = text.find("{", match.start())
    assert opening != -1, f"{label} opening brace missing"

    depth = 0
    for index in range(opening, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                return text[opening + 1 : index]

    raise AssertionError(f"unbalanced braces in {label}")


class TestMilestone1:
    def test_eks_module_has_private_dedicated_controller_node_group(self):
        """EKS module must be private with a three-node dedicated Jenkins group."""
        text = read("eks.tf")

        assert "terraform-aws-modules/eks/aws" in text
        assert re.search(r"cluster_endpoint_public_access\s*=\s*false", text)
        assert re.search(r"cluster_endpoint_private_access\s*=\s*true", text)
        assert re.search(r"subnet_ids\s*=\s*var\.private_subnet_ids", text)
        assert "public_subnet" not in text.lower()

        groups = braced_block(
            text,
            r"eks_managed_node_groups\s*=\s*\{",
            "managed node groups",
        )

        dedicated = braced_block(
            groups,
            r"\bjenkins_controllers\s*=\s*\{",
            "jenkins_controllers",
        )

        assert re.search(r"min_size\s*=\s*3", dedicated)
        assert re.search(r"desired_size\s*=\s*3", dedicated)
        assert re.search(r'workload\s*=\s*"jenkins-controller"', dedicated)
        assert re.search(r'dedicated\s*=\s*"jenkins"', dedicated)
        assert "NO_SCHEDULE" in dedicated or "NoSchedule" in dedicated

    def test_joc_and_three_controllers_with_scheduling_constraints(self):
        """Controllers must use controller-node scheduling constraints."""
        text = read("jenkins.tf")

        releases = {
            "payments_controller": "payments-controller",
            "risk_controller": "risk-controller",
            "platform_controller": "platform-controller",
        }

        for resource_name, release_name in releases.items():
            section = braced_block(
                text,
                rf'resource\s+"helm_release"\s+"{resource_name}"\s*\{{',
                release_name,
            )

            assert re.search(rf'name\s*=\s*"{re.escape(release_name)}"', section)
            assert re.search(rf"controllerName:\s*{re.escape(release_name)}", section)
            assert re.search(
                r'workload:\s*jenkins-controller|workload\s*=\s*"jenkins-controller"',
                section,
            ), f"{release_name} must target jenkins-controller node group"
            assert re.search(
                r"tolerations:\s*\n\s*-\s+key:\s*dedicated[\s\S]*?"
                r"(?:NoSchedule|NO_SCHEDULE)",
                section,
            ), f"{release_name} must tolerate the dedicated Jenkins taint"
            tsc = re.search(r"topologySpreadConstraints:\s*\n\s*-\s", section)
            paa = re.search(r"podAntiAffinity:\s*\n\s+\w", section)
            assert tsc or paa, (
                f"{release_name} needs real topology spread or pod anti-affinity"
            )

        joc = braced_block(
            text,
            r'resource\s+"helm_release"\s+"joc"\s*\{',
            "joc",
        )

        oc_match = re.search(
            r"operationsCenter:[\s\S]*?replicaCount:\s*([0-9]+)",
            joc,
        )

        assert re.search(r"operationsCenter:[\s\S]*?enabled:\s*true", joc)
        assert oc_match and int(oc_match.group(1)) >= 1