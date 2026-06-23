import json, os, subprocess, tempfile
from pathlib import Path
APP=Path(os.environ.get('APP_DIR','/app'))
TOOL=APP/'tools'/'tf_state_sim.py'
def w(p,o): p.write_text(json.dumps(o))
def call(td,state,lock,plan):
    out=td/'out'
    out.mkdir(exist_ok=True)
    return subprocess.run(['python3',str(TOOL),'apply','--state',str(state),'--lock',str(lock),'--plan',str(plan),'--out',str(out),'--workspace','prod','--run-id','r'],text=True,capture_output=True), out
class TestMilestone2:
    def test_stale_plan_serial_rejected_without_mutation(self):
        """Saved plans with old serials must not overwrite newer state."""
        td=Path(tempfile.mkdtemp())
        state=td/'s.json'
        lock=td/'l.json'
        plan=td/'p.json'
        w(state,{'lineage':'L','serial':3,'workspaces':{'prod':{'resources':{'db':'v3'}}}})
        w(lock,{})
        w(plan,{'workspace':'prod','lineage':'L','serial':2,'actions':[{'name':'db','value':'v2'}]})
        cp,out=call(td,state,lock,plan)
        result=json.loads((out/'apply_result.json').read_text())
        assert cp.returncode!=0 and result['status']=='FAILED_CLOSED' and json.loads(state.read_text())['workspaces']['prod']['resources']['db']=='v3'
    def test_lineage_mismatch_rejected(self):
        """Plans from a different state lineage must fail closed."""
        td=Path(tempfile.mkdtemp())
        state=td/'s.json'
        lock=td/'l.json'
        plan=td/'p.json'
        w(state,{'lineage':'L-new','serial':0,'workspaces':{'prod':{'resources':{}}}})
        w(lock,{})
        w(plan,{'workspace':'prod','lineage':'L-old','serial':0,'actions':[{'name':'x','value':'y'}]})
        cp,out=call(td,state,lock,plan)
        assert cp.returncode!=0 and 'lineage' in json.loads((out/'apply_result.json').read_text())['error']
    def test_matching_plan_advances_serial_once(self):
        """A valid plan increments the global state serial exactly once."""
        td=Path(tempfile.mkdtemp())
        state=td/'s.json'
        lock=td/'l.json'
        plan=td/'p.json'
        w(state,{'lineage':'L','serial':5,'workspaces':{'prod':{'resources':{}}}})
        w(lock,{})
        w(plan,{'workspace':'prod','lineage':'L','serial':5,'actions':[{'name':'svc','value':'blue'}]})
        cp,out=call(td,state,lock,plan)
        assert cp.returncode==0 and json.loads(state.read_text())['serial']==6

def test_runtime_has_no_capability_unlock():
    source = Path('/app/tools/tf_state_sim.py').read_text()
    assert 'CAPABILITY' not in source
