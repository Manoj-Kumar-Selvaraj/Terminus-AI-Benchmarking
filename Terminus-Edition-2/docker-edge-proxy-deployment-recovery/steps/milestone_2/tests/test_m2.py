import json, os, subprocess, tempfile
from pathlib import Path
APP=Path(os.environ.get('APP_DIR','/app'))
TOOL=APP/'tools'/'edge_proxy_deploy.py'
def run(m,state=None):
    td=Path(tempfile.mkdtemp())
    mp=td/'m.json'
    sp=td/'s.json'
    out=td/'out'
    mp.write_text(json.dumps(m))
    sp.write_text(json.dumps(state or {'active':{'digest':'old','config_sha':'old'},'containers':[]}))
    cp=subprocess.run(['python3',str(TOOL),'deploy','--manifest',str(mp),'--state',str(sp),'--out',str(out)],text=True,capture_output=True)
    return cp,out,sp
class TestMilestone2:
    def test_failed_route_health_blocks_promotion(self):
        """All manifest routes must pass health before promotion."""
        cp,out,sp=run({'release_id':'r','tag':'t','digest':'sha256:new','config_sha':'cfg','routes':['/pay','/cart'],'health':{'/pay':'ok','/cart':'fail'},'edge_host':'gw','cert':{'version':'c','sni':'gw','valid':True}})
        assert cp.returncode!=0 and json.loads(sp.read_text())['active']['digest']=='old'
    def test_missing_route_health_blocks_promotion(self):
        """Missing route health evidence must fail closed."""
        cp,out,sp=run({'release_id':'r','tag':'t','digest':'sha256:new','config_sha':'cfg','routes':['/pay'],'health':{},'edge_host':'gw','cert':{'version':'c','sni':'gw','valid':True}})
        assert cp.returncode!=0
    def test_all_routes_healthy_promotes(self):
        """A manifest with complete healthy route evidence may promote."""
        cp,out,sp=run({'release_id':'r','tag':'t','digest':'sha256:new','config_sha':'cfg','routes':['/pay'],'health':{'/pay':'ok'},'edge_host':'gw','cert':{'version':'c','sni':'gw','valid':True}})
        assert cp.returncode==0 and json.loads(sp.read_text())['active']['digest']=='sha256:new'

def test_runtime_has_no_capability_unlock():
    source = Path('/app/tools/edge_proxy_deploy.py').read_text()
    assert 'CAPABILITY' not in source
