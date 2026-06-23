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
class TestMilestone4:
    """Private audit endpoint must be allowed with an explicit exception."""
    def test_private_audit_allowed_but_blocked_exception_denied(self):
        assert sim('audit-endpoint','TCP',9443)=='ALLOW'
        assert sim('blocked-audit','TCP',9443)=='DENY'
    def test_all_previous_paths_preserved_and_external_denied(self):
        assert sim('kube-dns','UDP',53)=='ALLOW'
        assert sim('ledger-api','TCP',443)=='ALLOW'
        assert sim('token-service','TCP',8443)=='ALLOW'
        assert sim('external','TCP',9443)=='DENY'
