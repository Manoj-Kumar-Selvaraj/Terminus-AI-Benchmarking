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


class TestMilestone2:
  """Ledger egress must be narrow and preserve DNS."""

  def test_ledger_tcp_443_allowed(self):
    assert sim("ledger-api", "TCP", 443) == "ALLOW"
    assert sim("ledger-api", "TCP", 80) == "DENY"

  def test_ledger_namespace_not_broad(self):
    assert sim("ledger-internal", "TCP", 443) == "DENY"

  def test_dns_still_allowed_and_proxy_denied(self):
    assert sim("kube-dns", "UDP", 53) == "ALLOW"
    assert sim("kube-dns", "TCP", 53) == "ALLOW"
    assert sim("internet-proxy", "TCP", 443) == "DENY"

  def test_no_broad_namespace_access(self):
    for block in all_to_blocks():
      if "namespaceSelector" in block:
        assert "podSelector" in block, "Every namespaceSelector must be paired with podSelector"
