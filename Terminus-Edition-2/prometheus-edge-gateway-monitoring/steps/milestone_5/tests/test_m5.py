import json, os, subprocess, tempfile
from pathlib import Path
APP=Path(os.environ.get('APP_DIR','/app'))
TOOL=APP/'tools'/'edge_metrics.py'
def run_case(gate):
    td=Path(tempfile.mkdtemp())
    inp=td/'in'
    out=td/'out'
    st=td/'state'
    inp.mkdir()
    st.mkdir()
    (inp/'environment.json').write_text(json.dumps({'routes':[{'tenant':'acme','route':'/pay','env':'prod'}]}))
    (inp/'scrape.prom').write_text('edge_gateway_requests_total{tenant="acme",route="/pay",code="200"} 100 10\n')
    (inp/'release.json').write_text(json.dumps({'commit':'abc123','deploy_id':'d-7'}))
    if gate is not None: (inp/'quality_gate.json').write_text(json.dumps(gate))
    cp=subprocess.run(['python3',str(TOOL),'run','--input',str(inp),'--out',str(out),'--state',str(st)],text=True,capture_output=True)
    return cp,out
class TestMilestone5:
    def test_failed_quality_gate_blocks_promotion(self):
        """Promotion must fail closed when the release commit has a failed quality gate."""
        cp,out=run_case({'commit':'abc123','status':'FAIL'})
        alerts=json.loads((out/'alerts.json').read_text())
        summary=json.loads((out/'summary.json').read_text())
        assert any(a['name']=='PromotionBlocked' and a['gate_status']=='FAIL' for a in alerts)
        assert summary['promotable'] is False
    def test_gate_commit_must_match_release_commit(self):
        """A passing gate for a different commit must not authorize this release."""
        cp,out=run_case({'commit':'old999','status':'PASS'})
        alerts=json.loads((out/'alerts.json').read_text())
        assert any(a['name']=='PromotionBlocked' and a['gate_commit']=='old999' for a in alerts)
    def test_matching_pass_gate_is_promotable_when_alerts_clear(self):
        """A clean scrape and matching PASS gate should produce a promotable summary."""
        cp,out=run_case({'commit':'abc123','status':'PASS'})
        summary=json.loads((out/'summary.json').read_text())
        assert cp.returncode==0 and summary['promotable'] is True and summary['alert_count']==0

def test_runtime_has_no_capability_unlock():
    source = Path('/app/tools/edge_metrics.py').read_text()
    assert 'CAPABILITY' not in source
