import subprocess
import yaml
from pathlib import Path
APP=Path('/app')
POL=APP/'k8s/networkpolicy.yaml'
def sim(dest, proto, port):
    r=subprocess.run(['python3','/app/scripts/simulate_egress.py',dest,proto,str(port)], text=True, capture_output=True, timeout=20)
    assert r.returncode==0, r.stderr
    return r.stdout.strip()
def doc(): return yaml.safe_load(POL.read_text())
def all_to_blocks():
    d = doc()
    for e in d.get('spec',{}).get('egress',[]) or []:
        for t in e.get('to',[]) or []:
            yield t
class TestMilestone2:
    """Ledger egress must be narrow and preserve DNS."""
    def test_ledger_tcp_443_allowed(self):
        assert sim('ledger-api','TCP',443)=='ALLOW'
        assert sim('ledger-api','TCP',80)=='DENY'
    def test_dns_still_allowed_and_proxy_denied(self):
        assert sim('kube-dns','TCP',53)=='ALLOW'
        assert sim('internet-proxy','TCP',443)=='DENY'
