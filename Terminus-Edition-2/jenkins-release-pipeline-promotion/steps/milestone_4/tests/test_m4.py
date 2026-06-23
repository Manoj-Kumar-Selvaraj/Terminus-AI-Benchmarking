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
class TestMilestone4:
    """Rollback must redeploy the prior production artifact digest without rebuilding."""
    def test_rollback_uses_prior_digest_not_head(self):
        run()
        rb=j(OUT/'rollback_plan.json')
        assert rb['action']=='redeploy'
        assert rb['artifactDigest']=='sha256:prior-prod'
        assert rb['rebuild'] is False
    def test_promotion_contract_still_intact(self):
        run()
        promo=j(OUT/'promotion_manifest.json')
        result=j(OUT/'pipeline_result.json')
        assert promo['promoted'] is True
        assert result['stages']['ParallelIntegration']=='PASS'
