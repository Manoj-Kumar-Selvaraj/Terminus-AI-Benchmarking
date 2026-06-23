import json, os, subprocess, tempfile
from pathlib import Path
APP=Path(os.environ.get('APP_DIR','/app'))
TOOL=APP/'tools'/'edge_proxy_deploy.py'
def deploy_then_rollback(state):
    td=Path(tempfile.mkdtemp())
    sp=td/'s.json'
    mp=td/'m.json'
    out=td/'out'
    sp.write_text(json.dumps(state))
    mp.write_text(json.dumps({'release_id':'unused','tag':'latest','digest':'sha256:head','config_sha':'head','routes':[],'health':{},'edge_host':'gw','cert':{'version':'c','sni':'gw','valid':True}}))
    cp=subprocess.run(['python3',str(TOOL),'rollback','--manifest',str(mp),'--state',str(sp),'--out',str(out)],text=True,capture_output=True)
    return cp,out,sp
class TestMilestone5:
    def test_rollback_uses_previous_immutable_release_not_head_manifest(self):
        """Rollback must redeploy previous digest/config, not rebuild from the current manifest."""
        state={'active':{'digest':'sha256:bad','config_sha':'bad','cert_version':'c2'},'previous':{'digest':'sha256:good','config_sha':'good','cert_version':'c1'},'containers':[],'connections':7}
        cp,out,sp=deploy_then_rollback(state)
        s=json.loads(sp.read_text())
        assert cp.returncode==0 and s['active']['digest']=='sha256:good' and s['active']['digest']!='sha256:head'
    def test_rollback_drains_connections(self):
        """Rollback should drain active connection count before switching state."""
        cp,out,sp=deploy_then_rollback({'active':{'digest':'bad'},'previous':{'digest':'good','config_sha':'g','cert_version':'c'},'containers':[],'connections':11})
        assert json.loads(sp.read_text())['connections']==0
    def test_rollback_without_history_fails_closed(self):
        """No previous release means rollback must fail without inventing an image."""
        cp,out,sp=deploy_then_rollback({'active':{'digest':'bad'},'previous':None,'containers':[]})
        assert cp.returncode!=0 and json.loads(sp.read_text())['active']['digest']=='bad'

def test_runtime_has_no_capability_unlock():
    source = Path('/app/tools/edge_proxy_deploy.py').read_text()
    assert 'CAPABILITY' not in source
