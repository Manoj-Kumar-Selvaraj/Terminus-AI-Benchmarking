import json, os, subprocess, tempfile
from pathlib import Path
APP=Path(os.environ.get('APP_DIR','/app'))
TOOL=APP/'tools'/'edge_metrics.py'
def call(inp, out, st):
    return subprocess.run(['python3',str(TOOL),'run','--input',str(inp),'--out',str(out),'--state',str(st)],text=True,capture_output=True)
class TestMilestone3:
    def test_counter_reset_uses_current_delta(self):
        """A counter reset after restart must still produce a high error-rate alert from current deltas."""
        td=Path(tempfile.mkdtemp())
        inp=td/'in'
        out=td/'out'
        st=td/'state'
        inp.mkdir()
        st.mkdir()
        (inp/'environment.json').write_text(json.dumps({'routes':[{'tenant':'acme','route':'/pay','env':'prod'}]}))
        (st/'series_index.json').write_text(json.dumps({'series':[{'id':'edge_gateway_requests_total|code=500,route=/pay,tenant=acme','name':'edge_gateway_requests_total','labels':{'tenant':'acme','route':'/pay','code':'500'},'value':1000,'timestamp':100},{'id':'edge_gateway_requests_total|code=200,route=/pay,tenant=acme','name':'edge_gateway_requests_total','labels':{'tenant':'acme','route':'/pay','code':'200'},'value':2000,'timestamp':100}]}))
        (inp/'scrape.prom').write_text('edge_gateway_requests_total{tenant="acme",route="/pay",code="500"} 8 200\nedge_gateway_requests_total{tenant="acme",route="/pay",code="200"} 92 200\n')
        cp=call(inp,out,st)
        alerts=json.loads((out/'alerts.json').read_text())
        assert cp.returncode==0 and any(a['name']=='High5xxRate' for a in alerts)
    def test_duplicate_timestamp_is_idempotent(self):
        """Replaying the same scrape timestamp/value should not create a fresh alert from old data."""
        td=Path(tempfile.mkdtemp())
        inp=td/'in'
        out=td/'out'
        st=td/'state'
        inp.mkdir()
        st.mkdir()
        env={'routes':[{'tenant':'acme','route':'/pay','env':'prod'}]}
        (inp/'environment.json').write_text(json.dumps(env))
        sample='edge_gateway_requests_total{tenant="acme",route="/pay",code="500"} 9 200\nedge_gateway_requests_total{tenant="acme",route="/pay",code="200"} 91 200\n'
        (inp/'scrape.prom').write_text(sample)
        assert call(inp,out,st).returncode==0
        out2=td/'out2'
        assert call(inp,out2,st).returncode==0
        assert json.loads((out2/'alerts.json').read_text())==[]
    def test_series_state_advances_after_success(self):
        """Successful runs must persist the latest sample values for the next rate window."""
        td=Path(tempfile.mkdtemp())
        inp=td/'in'
        out=td/'out'
        st=td/'state'
        inp.mkdir()
        st.mkdir()
        (inp/'environment.json').write_text(json.dumps({'routes':[{'tenant':'a','route':'/r','env':'prod'}]}))
        (inp/'scrape.prom').write_text('edge_gateway_requests_total{tenant="a",route="/r",code="200"} 5 7\n')
        call(inp,out,st)
        series=json.loads((st/'series_index.json').read_text())['series']
        assert series[0]['value']==5 and series[0]['timestamp']==7

def test_runtime_has_no_capability_unlock():
    source = Path('/app/tools/edge_metrics.py').read_text()
    assert 'CAPABILITY' not in source
