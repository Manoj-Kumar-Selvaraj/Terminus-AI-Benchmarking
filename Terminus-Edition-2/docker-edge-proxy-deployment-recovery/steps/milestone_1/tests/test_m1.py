import json, os, subprocess, tempfile
from pathlib import Path
APP=Path(os.environ.get('APP_DIR','/app'))
TOOL=APP/'tools'/'edge_proxy_deploy.py'
def run(manifest,state=None):
    td=Path(tempfile.mkdtemp())
    mp=td/'m.json'
    sp=td/'s.json'
    out=td/'out'
    mp.write_text(json.dumps(manifest))
    sp.write_text(json.dumps(state or {'active':None,'containers':[]}))
    cp=subprocess.run(['python3',str(TOOL),'deploy','--manifest',str(mp),'--state',str(sp),'--out',str(out)],text=True,capture_output=True)
    return cp,out,sp
class TestMilestone1:
    def test_deploy_promotes_digest_not_tag(self):
        """Deployment identity must be the immutable manifest digest, not mutable tag."""
        cp,out,sp=run({'release_id':'r1','tag':'edge:latest','digest':'sha256:111','config_sha':'cfg','routes':['/'],'health':{'/':'ok'},'edge_host':'gw','cert':{'version':'c1','sni':'gw','valid':True}})
        active=json.loads(sp.read_text())['active']
        assert cp.returncode==0 and active['digest']=='sha256:111' and active['digest']!='edge:latest'
    def test_missing_digest_fails_closed(self):
        """A manifest without immutable digest must not update active release."""
        cp,out,sp=run({'release_id':'r1','tag':'edge:latest','config_sha':'cfg','routes':[]})
        assert cp.returncode!=0 and json.loads(sp.read_text())['active'] is None
    def test_result_preserves_manifest_schema_fields(self):
        """Output evidence must preserve release_id, digest, tag, and config_sha."""
        cp,out,sp=run({'release_id':'r2','tag':'edge:blue','digest':'sha256:abc','config_sha':'cfg2','routes':[],'health':{},'edge_host':'gw','cert':{'version':'c1','sni':'gw','valid':True}})
        active=json.loads((out/'deploy_result.json').read_text())['active']
        assert {k for k in ['release_id','digest','tag','config_sha']} <= set(active)

def test_runtime_has_no_capability_unlock():
    source = Path('/app/tools/edge_proxy_deploy.py').read_text()
    assert 'CAPABILITY' not in source
