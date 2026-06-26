import subprocess
from pathlib import Path

import yaml

APP = Path("/app")
POL = APP / "k8s/networkpolicy.yaml"


def sim(dest, proto, port):
    result = subprocess.run(
        ["python3", "/app/scripts/simulate_egress.py", dest, proto, str(port)],
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def doc():
    return yaml.safe_load(POL.read_text())


def all_to_blocks():
    policy = doc()
    for rule in policy.get("spec", {}).get("egress", []) or []:
        for block in rule.get("to", []) or []:
            yield block


def assert_no_broad_selectors():
    for block in all_to_blocks():
        if "ipBlock" in block:
            assert block.get("ipBlock", {}).get("cidr") != "0.0.0.0/0"
            continue
        assert block.get("namespaceSelector") != {}
        assert block.get("podSelector") != {}


class TestMilestone3:
  """Identity token service path must be allowed without broad egress."""

  def test_identity_8443_allowed(self):
    assert sim("token-service", "TCP", 8443) == "ALLOW"
    assert sim("token-service", "TCP", 443) == "DENY"

  def test_no_wildcard_ipblock_or_empty_selector_escape(self):
    assert_no_broad_selectors()
