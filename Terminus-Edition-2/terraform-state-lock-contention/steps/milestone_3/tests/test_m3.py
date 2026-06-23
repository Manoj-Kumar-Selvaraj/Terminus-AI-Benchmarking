import json, os, subprocess, tempfile
from pathlib import Path
APP=Path(os.environ.get('APP_DIR','/app'))
TOOL=APP/'tools'/'tf_state_sim.py'
def w(p,o): p.write_text(json.dumps(o))
def run(td,state,lock,plan,crash=0):
    out=td/f'out{crash}'
    out.mkdir(exist_ok=True)
    cp=td/'cp.json'
    cmd=['python3',str(TOOL),'apply','--state',str(state),'--lock',str(lock),'--plan',str(plan),'--out',str(out),'--workspace','prod','--run-id','r','--checkpoint',str(cp)]
    if crash: cmd += ['--crash-after',str(crash)]
    return subprocess.run(cmd,text=True,capture_output=True), out, cp
class TestMilestone3:
    def test_crash_resume_does_not_duplicate_serial(self):
        """A crash after a partial apply must resume from checkpoint and commit one serial increment."""
        td=Path(tempfile.mkdtemp())
        state=td/'s.json'
        lock=td/'l.json'
        plan=td/'p.json'
        w(state,{'lineage':'L','serial':7,'workspaces':{'prod':{'resources':{}}}})
        w(lock,{})
        w(plan,{'workspace':'prod','lineage':'L','serial':7,'actions':[{'name':'a','value':'1'},{'name':'b','value':'2'}]})
        cp1,_,checkpoint=run(td,state,lock,plan,crash=1)
        assert cp1.returncode==66 and checkpoint.exists()
        cp2,out,_=run(td,state,lock,plan)
        s=json.loads(state.read_text())
        assert cp2.returncode==0 and s['serial']==8 and s['workspaces']['prod']['resources']=={'a':'1','b':'2'} and not checkpoint.exists()
    def test_foreign_checkpoint_is_rejected(self):
        """Checkpoint files from another run holder must not be replayed blindly."""
        td=Path(tempfile.mkdtemp())
        state=td/'s.json'
        lock=td/'l.json'
        plan=td/'p.json'
        cp=td/'cp.json'
        w(state,{'lineage':'L','serial':1,'workspaces':{'prod':{'resources':{}}}})
        w(lock,{})
        w(plan,{'workspace':'prod','lineage':'L','serial':1,'actions':[{'name':'a','value':'x'}]})
        w(cp,{'run_id':'other','workspace':'prod','applied':['1:a']})
        out=td/'out'
        out.mkdir()
        result=subprocess.run(['python3',str(TOOL),'apply','--state',str(state),'--lock',str(lock),'--plan',str(plan),'--out',str(out),'--workspace','prod','--run-id','r','--checkpoint',str(cp)],text=True,capture_output=True)
        assert result.returncode!=0 and 'another run' in json.loads((out/'apply_result.json').read_text())['error']
    def test_failure_keeps_lock_evidence(self):
        """A simulated crash must persist state and lock evidence for operator recovery."""
        td=Path(tempfile.mkdtemp())
        state=td/'s.json'
        lock=td/'l.json'
        plan=td/'p.json'
        w(state,{'lineage':'L','serial':2,'workspaces':{'prod':{'resources':{}}}})
        w(lock,{})
        w(plan,{'workspace':'prod','lineage':'L','serial':2,'actions':[{'name':'a','value':'x'}]})
        cp,out,checkpoint=run(td,state,lock,plan,crash=1)
        assert json.loads(lock.read_text())['active']['holder']=='r' and checkpoint.exists()

def test_runtime_has_no_capability_unlock():
    source = Path('/app/tools/tf_state_sim.py').read_text()
    assert 'CAPABILITY' not in source
