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


class TestMilestone1:
  """DNS egress must support kube-dns over UDP and TCP without public egress."""

  def test_dns_udp_and_tcp_allowed(self):
    assert sim("kube-dns", "UDP", 53) == "ALLOW"
    assert sim("kube-dns", "TCP", 53) == "ALLOW"

  def test_no_general_external_egress(self):
    assert sim("external", "TCP", 443) == "DENY"
    assert sim("ledger-api", "TCP", 443) == "DENY"
    assert sim("token-service", "TCP", 443) == "DENY"
