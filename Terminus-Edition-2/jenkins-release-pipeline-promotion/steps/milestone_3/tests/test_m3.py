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
class TestMilestone3:
    """Promotion gate must evaluate the built artifact digest."""
    def test_quality_gate_uses_artifact_scan_not_branch_tip(self):
        run()
        promo=j(OUT/'promotion_manifest.json')
        assert promo['artifactDigest']=='sha256:built-good'
        assert promo['qualityStatus']=='PASS'
        assert promo['promoted'] is True
    def test_legacy_manifest_schema_preserved(self):
        run()
        promo=j(OUT/'promotion_manifest.json')
        assert sorted(promo.keys())==['artifactDigest','buildNumber','commit','promoted','qualityStatus','schema']
        assert promo['schema']=='v1'
