import json, os, subprocess, tempfile
from pathlib import Path
APP=Path(os.environ.get('APP_DIR','/app'))
TOOL=APP/'tools'/'edge_proxy_deploy.py'
def call(td,m,state):
    mp=td/'m.json'
    sp=td/'s.json'
    out=td/'out'
    mp.write_text(json.dumps(m))
    sp.write_text(json.dumps(state))
    out.mkdir(exist_ok=True)
    cp=subprocess.run(['python3',str(TOOL),'deploy','--manifest',str(mp),'--state',str(sp),'--out',str(out)],text=True,capture_output=True)
    return cp,out,sp
MAN={'release_id':'r','tag':'t','digest':'sha256:new','config_sha':'cfg','routes':['/'],'health':{'/':'ok'},'edge_host':'gw','cert':{'version':'c','sni':'gw','valid':True}}
class TestMilestone3:
    def test_stale_stopped_container_removed(self):
        """Stopped containers holding the proxy port should be cleaned before promotion."""
        td=Path(tempfile.mkdtemp())
        state={'active':None,'containers':[{'name':'old','digest':'old','port':443,'status':'exited'}]}
        cp,out,sp=call(td,MAN,state)
        containers=json.loads(sp.read_text())['containers']
        assert cp.returncode==0 and len([c for c in containers if c['port']==443])==1 and containers[0]['digest']=='sha256:new'
    def test_idempotent_deploy_does_not_duplicate_container(self):
        """Re-running the same manifest should be a NOOP with one active proxy container."""
        td=Path(tempfile.mkdtemp())
        state={'active':None,'containers':[]}
        cp,out,sp=call(td,MAN,state)
        cp2,out2,sp=call(td,MAN,json.loads(sp.read_text()))
        assert cp2.returncode==0 and len(json.loads(sp.read_text())['containers'])==1
    def test_ambiguous_running_port_conflict_fails_closed(self):
        """Two running containers on 443 must not be guessed around."""
        td=Path(tempfile.mkdtemp())
        state={'active':None,'containers':[{'name':'a','digest':'a','port':443,'status':'running'},{'name':'b','digest':'b','port':443,'status':'running'}]}
        cp,out,sp=call(td,MAN,state)
        assert cp.returncode!=0 and 'ambiguous' in json.loads((out/'deploy_result.json').read_text())['error']

def test_runtime_has_no_capability_unlock():
    source = Path('/app/tools/edge_proxy_deploy.py').read_text()
    assert 'CAPABILITY' not in source
