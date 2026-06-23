import json, os, subprocess, tempfile
from pathlib import Path
APP=Path(os.environ.get('APP_DIR','/app'))
TOOL=APP/'tools'/'edge_metrics.py'
def run_case(files, state=None):
    td=Path(tempfile.mkdtemp())
    inp=td/'in'
    out=td/'out'
    st=td/'state'
    inp.mkdir()
    st.mkdir()
    for name, data in files.items(): (inp/name).write_text(data if isinstance(data,str) else json.dumps(data))
    if state: (st/'series_index.json').write_text(json.dumps(state))
    cp=subprocess.run(['python3',str(TOOL),'run','--input',str(inp),'--out',str(out),'--state',str(st)],text=True,capture_output=True)
    return cp, out, st
class TestMilestone1:
    def test_route_identity_not_metric_only(self):
        """5xx on one route must not be hidden by successful samples from a different route."""
        cp,out,_=run_case({'scrape.prom':'edge_gateway_requests_total{tenant="acme",route="/pay",code="500"} 10 100\nedge_gateway_requests_total{tenant="acme",route="/pay",code="200"} 90 100\nedge_gateway_requests_total{tenant="acme",route="/cart",code="200"} 1000 100\n','environment.json':{'routes':[{'tenant':'acme','route':'/pay','env':'prod'},{'tenant':'acme','route':'/cart','env':'prod'}]}})
        assert cp.returncode==0
        alerts=json.loads((out/'alerts.json').read_text())
        assert any(a['name']=='High5xxRate' and a['route']=='/pay' for a in alerts)
        assert not any(a.get('route')=='/cart' and a['name']=='High5xxRate' for a in alerts)
    def test_malformed_samples_are_rejected_without_crash(self):
        """Bad sample lines are counted as rejects while valid samples still produce outputs."""
        cp,out,_=run_case({'scrape.prom':'edge_gateway_requests_total{tenant="acme",route="/pay",code="500"} nope 100\nedge_gateway_requests_total{tenant="acme",route="/pay",code="500"} 7 101\n','environment.json':{'routes':[{'tenant':'acme','route':'/pay','env':'prod'}]}})
        summary=json.loads((out/'summary.json').read_text())
        assert cp.returncode==0 and summary['reject_count']==1 and summary['sample_count']==1
    def test_series_index_preserves_labels_and_timestamp(self):
        """Persisted series identity must include labels and timestamps for downstream milestones."""
        cp,out,st=run_case({'scrape.prom':'edge_gateway_requests_total{tenant="t1",route="/r",code="200"} 11 222\n','environment.json':{'routes':[{'tenant':'t1','route':'/r','env':'prod'}]}})
        series=json.loads((st/'series_index.json').read_text())['series']
        assert series[0]['labels']['tenant']=='t1' and series[0]['timestamp']==222

def test_runtime_has_no_capability_unlock():
    source = Path('/app/tools/edge_metrics.py').read_text()
    assert 'CAPABILITY' not in source
