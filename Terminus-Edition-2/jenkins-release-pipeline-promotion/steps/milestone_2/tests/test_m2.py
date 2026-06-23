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
class TestMilestone2:
    """Parallel integration must not share artifact metadata or cache keys."""
    def test_parallel_axes_get_isolated_workspace_manifest(self):
        run()
        manifest=j(OUT/'integration_workspace_manifest.json')
        assert sorted(manifest['produced'])==['sha256:built-good:linux-jdk21','sha256:built-good:windows-jdk21']
    def test_credential_fix_is_preserved(self):
        run()
        assert j(OUT/'pipeline_result.json')['stages']['PromoteCredentials']=='PASS'
