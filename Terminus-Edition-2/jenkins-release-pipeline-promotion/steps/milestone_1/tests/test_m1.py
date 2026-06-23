import json, subprocess
from pathlib import Path
APP=Path('/app')
OUT=APP/'out'
CI=APP/'ci'
def run():
    OUT.mkdir(exist_ok=True)
    r=subprocess.run(['python3','/app/ci/simulate_pipeline.py'], cwd=APP, text=True, capture_output=True, timeout=30)
    assert r.returncode==0, r.stdout+r.stderr
def j(path): return json.loads(path.read_text())
class TestMilestone1:
    """Production deploy must use the production credential while staging remains scoped."""
    def test_production_credential_binding(self):
        run()
        result=j(OUT/'pipeline_result.json')
        assert result['stages']['PromoteCredentials']=='PASS'
        cfg=j(CI/'pipeline_config.json')
        assert cfg['credentialBindings']['staging']=='cred-staging'
        assert cfg['credentialBindings']['production']=='cred-production'
    def test_stage_names_preserved(self):
        cfg=j(CI/'pipeline_config.json')
        assert cfg['compat']['stageNames']==['Build','Integration','Quality Gate','Promote','Rollback']
