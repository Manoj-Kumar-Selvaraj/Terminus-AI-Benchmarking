import json, os, subprocess, tempfile
from pathlib import Path
APP=Path(os.environ.get('APP_DIR','/app'))
TOOL=APP/'tools'/'edge_metrics.py'
def run_case(files):
    td=Path(tempfile.mkdtemp())
    inp=td/'in'
    out=td/'out'
    st=td/'state'
    inp.mkdir()
    st.mkdir()
    for name,data in files.items(): (inp/name).write_text(data if isinstance(data,str) else json.dumps(data))
    cp=subprocess.run(['python3',str(TOOL),'run','--input',str(inp),'--out',str(out),'--state',str(st)],text=True,capture_output=True)
    return cp,out
class TestMilestone2:
    def test_stage_canary_does_not_page_prod(self):
        """Canary/stage series must not contaminate prod alert calculations."""
        cp,out=run_case({'scrape.prom':'edge_gateway_requests_total{tenant="acme",route="/pay",code="500"} 99 10\nedge_gateway_requests_total{tenant="acme",route="/pay",code="200"} 1 10\nedge_gateway_requests_total{tenant="beta",route="/pay",code="500"} 1 10\nedge_gateway_requests_total{tenant="beta",route="/pay",code="200"} 999 10\n','environment.json':{'routes':[{'tenant':'acme','route':'/pay','env':'stage'},{'tenant':'beta','route':'/pay','env':'prod'}]}})
        alerts=json.loads((out/'alerts.json').read_text())
        assert cp.returncode==0
        assert not any(a.get('tenant')=='acme' for a in alerts)
        assert not any(a.get('tenant')=='beta' and a['name']=='High5xxRate' for a in alerts)
    def test_unmapped_series_warns_not_pages(self):
        """Unknown tenant/route labels should be warning evidence, not prod alerts."""
        cp,out=run_case({'scrape.prom':'edge_gateway_requests_total{tenant="ghost",route="/x",code="500"} 20 10\n','environment.json':{'routes':[]}})
        warnings=json.loads((out/'warnings.json').read_text())
        alerts=json.loads((out/'alerts.json').read_text())
        assert any(w['name']=='UnmappedSeries' for w in warnings)
        assert not alerts
    def test_alerts_preserve_tenant_route_labels(self):
        """Prod alerts must carry tenant and route labels needed by the routing system."""
        cp,out=run_case({'scrape.prom':'edge_gateway_requests_total{tenant="east",route="/settle",code="500"} 6 10\nedge_gateway_requests_total{tenant="east",route="/settle",code="200"} 94 10\n','environment.json':{'routes':[{'tenant':'east','route':'/settle','env':'prod'}]}})
        alert=json.loads((out/'alerts.json').read_text())[0]
        assert alert['tenant']=='east' and alert['route']=='/settle' and alert['labels']['code']=='500'

def test_runtime_has_no_capability_unlock():
    source = Path('/app/tools/edge_metrics.py').read_text()
    assert 'CAPABILITY' not in source
