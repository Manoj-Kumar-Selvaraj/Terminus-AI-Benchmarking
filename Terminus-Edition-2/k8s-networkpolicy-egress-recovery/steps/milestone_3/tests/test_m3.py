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
class TestMilestone3:
    """Identity token service path must be allowed without broad egress."""
    def test_identity_8443_allowed(self):
        assert sim('token-service','TCP',8443)=='ALLOW'
        assert sim('token-service','TCP',443)=='DENY'
    def test_no_wildcard_ipblock_or_empty_selector_escape(self):
        for block in all_to_blocks():
            assert block.get('ipBlock',{}).get('cidr')!='0.0.0.0/0'
            assert block.get('namespaceSelector')!={}
            assert block.get('podSelector')!={}
