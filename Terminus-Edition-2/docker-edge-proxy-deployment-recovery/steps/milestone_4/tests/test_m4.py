import json, os, subprocess, tempfile
from pathlib import Path
APP=Path(os.environ.get('APP_DIR','/app'))
TOOL=APP/'tools'/'edge_proxy_deploy.py'
def run(m,state):
    td=Path(tempfile.mkdtemp())
    mp=td/'m.json'
    sp=td/'s.json'
    out=td/'out'
    mp.write_text(json.dumps(m))
    sp.write_text(json.dumps(state))
    cp=subprocess.run(['python3',str(TOOL),'deploy','--manifest',str(mp),'--state',str(sp),'--out',str(out)],text=True,capture_output=True)
    return cp,out,sp
BASE={'active':{'digest':'old','config_sha':'old','cert_version':'c0'},'containers':[],'cert_history':['c0']}
class TestMilestone4:
    def test_cert_sni_mismatch_blocks_promotion(self):
        """A cert bundle for the wrong SNI must not replace the active proxy."""
        cp,out,sp=run({'release_id':'r','tag':'t','digest':'sha256:n','config_sha':'c','routes':['/'],'health':{'/':'ok'},'edge_host':'gw.prod','cert':{'version':'c1','sni':'other','valid':True}},BASE)
        assert cp.returncode!=0 and json.loads(sp.read_text())['active']['digest']=='old'
    def test_invalid_cert_does_not_append_history(self):
        """Failed cert rotation must not contaminate certificate history."""
        cp,out,sp=run({'release_id':'r','tag':'t','digest':'sha256:n','config_sha':'c','routes':['/'],'health':{'/':'ok'},'edge_host':'gw','cert':{'version':'bad','sni':'gw','valid':False}},BASE)
        assert json.loads(sp.read_text())['cert_history']==['c0']
    def test_valid_cert_rotation_promotes_atomically(self):
        """A healthy manifest with matching cert updates active release and cert history together."""
        cp,out,sp=run({'release_id':'r','tag':'t','digest':'sha256:n','config_sha':'c','routes':['/'],'health':{'/':'ok'},'edge_host':'gw','cert':{'version':'c1','sni':'gw','valid':True}},BASE)
        s=json.loads(sp.read_text())
        assert cp.returncode==0 and s['active']['cert_version']=='c1' and 'c1' in s['cert_history']

def test_runtime_has_no_capability_unlock():
    source = Path('/app/tools/edge_proxy_deploy.py').read_text()
    assert 'CAPABILITY' not in source
