import json, os, subprocess, tempfile
from pathlib import Path
APP=Path(os.environ.get('APP_DIR','/app'))
TOOL=APP/'tools'/'tf_state_sim.py'
def w(p,o): p.write_text(json.dumps(o))
def call(td,state,lock,plan,ws):
    out=td/'out'
    out.mkdir(exist_ok=True)
    return subprocess.run(['python3',str(TOOL),'apply','--state',str(state),'--lock',str(lock),'--plan',str(plan),'--out',str(out),'--workspace',ws,'--run-id','r'],text=True,capture_output=True), out
class TestMilestone4:
    def test_workspace_isolation_prevents_stage_clobber(self):
        """Applying a prod plan must not mutate resources in the stage workspace."""
        td=Path(tempfile.mkdtemp())
        state=td/'s.json'
        lock=td/'l.json'
        plan=td/'p.json'
        w(state,{'lineage':'L','serial':1,'workspaces':{'prod':{'resources':{}},'stage':{'resources':{'svc':'stage-v1'}}}})
        w(lock,{})
        w(plan,{'workspace':'prod','lineage':'L','serial':1,'backend_key':'env/prod.tfstate','actions':[{'name':'svc','value':'prod-v2'}]})
        cp,out=call(td,state,lock,plan,'prod')
        s=json.loads(state.read_text())
        assert cp.returncode==0 and s['workspaces']['stage']['resources']['svc']=='stage-v1' and s['workspaces']['prod']['resources']['svc']=='prod-v2'
    def test_backend_key_recorded_per_workspace(self):
        """Backend migration evidence must preserve each workspace key."""
        td=Path(tempfile.mkdtemp())
        state=td/'s.json'
        lock=td/'l.json'
        plan=td/'p.json'
        w(state,{'lineage':'L','serial':0,'workspaces':{'prod':{'resources':{}}}})
        w(lock,{})
        w(plan,{'workspace':'prod','lineage':'L','serial':0,'backend_key':'remote/prod/state','actions':[]})
        cp,out=call(td,state,lock,plan,'prod')
        assert json.loads(state.read_text())['backend_keys']['prod']=='remote/prod/state'
    def test_workspace_lock_does_not_block_other_workspace(self):
        """A lock for stage should not block an independent prod apply."""
        td=Path(tempfile.mkdtemp())
        state=td/'s.json'
        lock=td/'l.json'
        plan=td/'p.json'
        w(state,{'lineage':'L','serial':4,'workspaces':{'prod':{'resources':{}},'stage':{'resources':{}}}})
        w(lock,{'active':{'workspace':'stage','holder':'stage-run','expires_at':1200}})
        w(plan,{'workspace':'prod','lineage':'L','serial':4,'actions':[{'name':'x','value':'y'}]})
        cp,out=call(td,state,lock,plan,'prod')
        assert cp.returncode==0

def test_runtime_has_no_capability_unlock():
    source = Path('/app/tools/tf_state_sim.py').read_text()
    assert 'CAPABILITY' not in source
