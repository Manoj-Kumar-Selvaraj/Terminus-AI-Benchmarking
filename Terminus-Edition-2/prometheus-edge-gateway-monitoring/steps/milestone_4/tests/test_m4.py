import json, os, subprocess, tempfile
from pathlib import Path
APP=Path(os.environ.get('APP_DIR','/app'))
TOOL=APP/'tools'/'edge_metrics.py'
def run_case(files,state=None):
    td=Path(tempfile.mkdtemp())
    inp=td/'in'
    out=td/'out'
    st=td/'state'
    inp.mkdir()
    st.mkdir()
    for n,d in files.items(): (inp/n).write_text(d if isinstance(d,str) else json.dumps(d))
    if state: (st/'series_index.json').write_text(json.dumps(state))
    cp=subprocess.run(['python3',str(TOOL),'run','--input',str(inp),'--out',str(out),'--state',str(st)],text=True,capture_output=True)
    return cp,out
class TestMilestone4:
    def test_missing_scrape_for_known_prod_route_pages(self):
        """Known prod routes absent from a scrape must emit ScrapeMissing instead of green status."""
        cp,out=run_case({'scrape.prom':'','environment.json':{'routes':[{'tenant':'acme','route':'/pay','env':'prod'}]}})
        alerts=json.loads((out/'alerts.json').read_text())
        assert any(a['name']=='ScrapeMissing' and a['route']=='/pay' for a in alerts)
    def test_malformed_environment_fails_closed(self):
        """A malformed environment map must fail closed and mark the run non-promotable."""
        cp,out=run_case({'scrape.prom':'edge_gateway_requests_total 1 1\n','environment.json':'{"routes":'})
        summary=json.loads((out/'summary.json').read_text())
        assert cp.returncode!=0 and summary['status']=='FAILED_CLOSED' and summary['promotable'] is False
    def test_stale_samples_do_not_override_newer_state(self):
        """Older scrape timestamps should be reported as stale and not regress persisted state."""
        old={'series':[{'id':'edge_gateway_requests_total|code=200,route=/pay,tenant=acme','name':'edge_gateway_requests_total','labels':{'tenant':'acme','route':'/pay','code':'200'},'value':10,'timestamp':50}]}
        cp,out=run_case({'scrape.prom':'edge_gateway_requests_total{tenant="acme",route="/pay",code="200"} 11 40\n','environment.json':{'routes':[{'tenant':'acme','route':'/pay','env':'prod'}]}},old)
        alerts=json.loads((out/'alerts.json').read_text())
        assert any(a['name']=='StaleSample' for a in alerts)

def test_runtime_has_no_capability_unlock():
    source = Path('/app/tools/edge_metrics.py').read_text()
    assert 'CAPABILITY' not in source
