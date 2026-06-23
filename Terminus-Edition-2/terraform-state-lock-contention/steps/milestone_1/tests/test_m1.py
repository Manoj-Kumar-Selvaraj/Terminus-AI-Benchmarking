import json, os, subprocess, tempfile
from pathlib import Path
APP=Path(os.environ.get('APP_DIR','/app'))
TOOL=APP/'tools'/'tf_state_sim.py'
def w(p,o): p.write_text(json.dumps(o))
def apply(td, state, lock, plan, **kw):
    out=td/'out'
    out.mkdir(exist_ok=True)
    cmd=['python3',str(TOOL),'apply','--state',str(state),'--lock',str(lock),'--plan',str(plan),'--out',str(out),'--workspace',kw.get('workspace','prod'),'--run-id',kw.get('run_id','run2')]
    return subprocess.run(cmd,text=True,capture_output=True), out
class TestMilestone1:
    def test_active_lock_from_other_holder_blocks_apply(self):
        """An unexpired lock owned by a different run must block state mutation."""
        td=Path(tempfile.mkdtemp())
        state=td/'state.json'
        lock=td/'lock.json'
        plan=td/'plan.json'
        w(state,{'lineage':'L','serial':4,'workspaces':{'prod':{'resources':{'a':'old'}}}})
        w(lock,{'active':{'workspace':'prod','holder':'run1','expires_at':1200}})
        w(plan,{'workspace':'prod','lineage':'L','serial':4,'actions':[{'name':'a','value':'new'}]})
        cp,out=apply(td,state,lock,plan)
        assert cp.returncode!=0 and json.loads(state.read_text())['workspaces']['prod']['resources']['a']=='old'
    def test_expired_lock_can_be_replaced(self):
        """Expired lock records may be replaced by the applying run."""
        td=Path(tempfile.mkdtemp())
        state=td/'state.json'
        lock=td/'lock.json'
        plan=td/'plan.json'
        w(state,{'lineage':'L','serial':0,'workspaces':{}})
        w(lock,{'active':{'workspace':'prod','holder':'old','expires_at':1}})
        w(plan,{'workspace':'prod','lineage':'L','serial':0,'actions':[{'name':'svc','value':'v1'}]})
        cp,out=apply(td,state,lock,plan)
        assert cp.returncode==0 and 'active' not in json.loads(lock.read_text())
    def test_reject_is_audited(self):
        """Lock contention must leave operator evidence in the lock audit."""
        td=Path(tempfile.mkdtemp())
        state=td/'state.json'
        lock=td/'lock.json'
        plan=td/'plan.json'
        w(state,{'lineage':'L','serial':1,'workspaces':{'prod':{'resources':{}}}})
        w(lock,{'active':{'workspace':'prod','holder':'other','expires_at':1200}})
        w(plan,{'workspace':'prod','lineage':'L','serial':1,'actions':[{'name':'x','value':'y'}]})
        cp,out=apply(td,state,lock,plan)
        assert 'active lock held' in (out/'lock_audit.jsonl').read_text()

def test_runtime_has_no_capability_unlock():
    source = Path('/app/tools/tf_state_sim.py').read_text()
    assert 'CAPABILITY' not in source
