import json, os, subprocess, tempfile
from pathlib import Path
APP=Path(os.environ.get('APP_DIR','/app'))
TOOL=APP/'tools'/'tf_state_sim.py'
def w(p,o): p.write_text(json.dumps(o))
def call(td, plan_hash, lock_hash, cache_hashes):
    state=td/'s.json'
    lock=td/'l.json'
    plan=td/'p.json'
    lf=td/'provider.lock.json'
    cache=td/'cache.json'
    out=td/'out'
    out.mkdir(exist_ok=True)
    w(state,{'lineage':'L','serial':0,'workspaces':{'prod':{'resources':{}}}})
    w(lock,{})
    w(plan,{'workspace':'prod','lineage':'L','serial':0,'provider_hash':plan_hash,'actions':[{'name':'svc','value':'v'}]})
    w(lf,{'provider_hash':lock_hash})
    w(cache,{'providers':cache_hashes})
    cp=subprocess.run(['python3',str(TOOL),'apply','--state',str(state),'--lock',str(lock),'--plan',str(plan),'--out',str(out),'--workspace','prod','--run-id','r','--lock-file',str(lf),'--provider-cache',str(cache)],text=True,capture_output=True)
    return cp,out,state
class TestMilestone5:
    def test_provider_hash_mismatch_fails_closed(self):
        """Plans must not run when .terraform lock hash disagrees with the saved plan."""
        cp,out,state=call(Path(tempfile.mkdtemp()),'h-new','h-old',['h-new'])
        assert cp.returncode!=0 and json.loads(state.read_text())['serial']==0
    def test_missing_provider_mirror_fails_closed(self):
        """The offline provider mirror must contain the exact provider hash used by the plan."""
        cp,out,state=call(Path(tempfile.mkdtemp()),'h1','h1',['other'])
        assert cp.returncode!=0 and 'mirror missing' in json.loads((out/'apply_result.json').read_text())['error']
    def test_matching_provider_hash_applies(self):
        """A plan with matching lock and mirror hashes may apply normally."""
        cp,out,state=call(Path(tempfile.mkdtemp()),'h1','h1',['h1'])
        assert cp.returncode==0 and json.loads(state.read_text())['workspaces']['prod']['resources']['svc']=='v'

def test_runtime_has_no_capability_unlock():
    source = Path('/app/tools/tf_state_sim.py').read_text()
    assert 'CAPABILITY' not in source
