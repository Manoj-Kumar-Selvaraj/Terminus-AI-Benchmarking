import os
import re
from pathlib import Path

APP = Path(os.environ.get("APP_ROOT", "/app"))
TF = APP / "terraform"

EXPECTED_OUTPUTS = [
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


def assert_balanced_hcl(text, filename):
    """Reject structurally malformed HCL before checking individual values."""
    depth = 0
    for char in text:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            assert depth >= 0, f"unexpected closing brace in {filename}"
    assert depth == 0, f"unbalanced braces in {filename}"


def output_has_real_value(block):
    value_part = block.split("value", 1)[1] if "value" in block else ""
    return bool(
        re.search(r"module\.|var\.|keys\(module\.", value_part)
    )


class TestMilestone4:
    def test_outputs_preserved(self):
        """Legacy outputs and add-on role output remain for downstream modules."""
        outputs = read("outputs.tf")
        for name in EXPECTED_OUTPUTS:
            assert f'output "{name}"' in outputs
            block = extract_output_block(outputs, name)
            assert output_has_real_value(block), (
                f"output {name} must reference module or var"
            )
            assert 'value = ""' not in block and "value = ''" not in block
        assert "cluster_endpoint_url" not in outputs

    def test_outputs_structurally_valid(self):
        """All Terraform files have balanced structure and complete output blocks."""
        for path in sorted(TF.glob("*.tf")):
            assert_balanced_hcl(path.read_text(encoding="utf-8"), path.name)
        outputs = read("outputs.tf")
        for name in EXPECTED_OUTPUTS:
            block = extract_output_block(outputs, name)
            assert "value" in block

    def test_versions_and_moved_blocks(self):
        """Pinned versions and moved blocks document refactor continuity."""
        text = all_tf()
        assert re.search(r'version\s*=\s*"[0-9]+\.[0-9]+\.[0-9]+"', text)
        moved_match = re.search(
            r"moved\s*\{[^}]+\}",
            text,
            re.DOTALL,
        )
        assert moved_match, "moved block not found"
        moved = moved_match.group(0)
        assert "from = aws_iam_role_policy_attachment.node_addon_admin" in moved
        assert re.search(r"to\s*=\s*module\.ebs_csi_irsa", moved)
