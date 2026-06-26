# ruff: noqa
import json
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

BIN="/app/bin/signerctl"
def run(*args,check=False):
    p=subprocess.run([BIN,*map(str,args)],text=True,capture_output=True)
    if check and p.returncode!=0: raise AssertionError(f"{p.args}\n{p.stdout}\n{p.stderr}")
    return p
def init(d,lease=100,key="key-a"):
    run("init","--state",d,"--lease-ms",lease,"--key",key,check=True)
def acquire(d,node,now):
    out=Path(d)/f"token-{node}-{now}.json";p=run("acquire","--state",d,"--node",node,"--now",now,"--out",out)
    return p,(json.loads(out.read_text()) if out.exists() else None)
def request(d,name,rid,payload):
    p=Path(d)/name;p.write_text(f"id={rid}\npayload={payload}\n");return p
def sign(d,node,tok,now,req,name="sig.json",crash=None):
    out=Path(d)/name;a=["sign","--state",d,"--node",node,"--token",tok,"--now",now,"--request",req,"--out",out]
    if crash:a += ["--crash",crash]
    p=run(*a);return p,(json.loads(out.read_text()) if out.exists() else None)
def recover(d,node,tok,now,name="recover.json"):
    out=Path(d)/name;p=run("recover","--state",d,"--node",node,"--token",tok,"--now",now,"--out",out)
    return p,(json.loads(out.read_text()) if out.exists() else None)
def status(d):
    out=Path(d)/"status.json";run("status","--state",d,"--out",out,check=True);return json.loads(out.read_text())
def hsm_rows(d):
    p=Path(d)/"hsm.log";return [x for x in p.read_text().splitlines() if x.strip()]

class TestMilestone2:
    def test_crash_after_hsm_recovers_without_second_operation(self):
        """Recovery finalizes the audited signature after an HSM-side-effect crash without another call."""
        with tempfile.TemporaryDirectory() as d:
            init(d);_,t=acquire(d,"a",100);r=request(d,"r.properties","auth-1","amount=10")
            p,_=sign(d,"a",t["token"],110,r,crash="after_hsm");assert p.returncode==75 and len(hsm_rows(d))==1
            p2,s=recover(d,"a",t["token"],120);assert p2.returncode==0 and s["recovered"]==1
            assert len(hsm_rows(d))==1
            p3,sig=sign(d,"a",t["token"],130,r,name="again.json");assert p3.returncode==0 and sig
            assert len(hsm_rows(d))==1

    def test_crash_after_prepare_reuses_operation_identity(self):
        """Retry after PREPARED reuses the durable operation identity and creates one HSM row."""
        with tempfile.TemporaryDirectory() as d:
            init(d);_,t=acquire(d,"a",0);r=request(d,"r","auth-2","x=2")
            assert sign(d,"a",t["token"],1,r,crash="after_prepare")[0].returncode==75
            assert sign(d,"a",t["token"],2,r)[0].returncode==0
            assert len(hsm_rows(d))==1

    def test_committed_retry_returns_original_signature(self):
        """A committed request retry returns the same signature without changing HSM audit."""
        with tempfile.TemporaryDirectory() as d:
            init(d);_,t=acquire(d,"a",0);r=request(d,"r","auth-3","x=3")
            _,s1=sign(d,"a",t["token"],1,r,name="one.json");_,s2=sign(d,"a",t["token"],2,r,name="two.json")
            assert s1["signature"]==s2["signature"] and len(hsm_rows(d))==1

    def test_conflicting_payload_for_request_id_fails_closed(self):
        """The same request ID with a different payload is rejected and does not reach the HSM."""
        with tempfile.TemporaryDirectory() as d:
            init(d);_,t=acquire(d,"a",0);a=request(d,"a","auth-4","x=4");b=request(d,"b","auth-4","x=changed")
            sign(d,"a",t["token"],1,a);before=hsm_rows(d)
            p,_=sign(d,"a",t["token"],2,b,name="bad.json")
            assert p.returncode!=0 and "conflict" in p.stderr.lower() and hsm_rows(d)==before

    def test_concurrent_same_request_creates_one_hsm_row(self):
        """Same-request callers racing through separate processes converge on one operation and signature."""
        with tempfile.TemporaryDirectory() as d:
            init(d);_,t=acquire(d,"a",0);r=request(d,"r","auth-5","x=5")
            def one(i): return sign(d,"a",t["token"],1,r,name=f"s{i}.json")[0].returncode
            with ThreadPoolExecutor(max_workers=4) as ex: codes=list(ex.map(one,range(4)))
            assert codes==[0,0,0,0] and len(hsm_rows(d))==1

    def test_multiple_prepared_requests_recover_independently(self):
        """Recovery completes every independent PREPARED request exactly once."""
        with tempfile.TemporaryDirectory() as d:
            init(d);_,t=acquire(d,"a",0)
            for i in range(3):
                r=request(d,f"r{i}",f"auth-{10+i}",f"x={i}");assert sign(d,"a",t["token"],1,r,crash="after_prepare")[0].returncode==75
            p,s=recover(d,"a",t["token"],2);assert p.returncode==0 and s["recovered"]==3 and len(hsm_rows(d))==3
            p2,s2=recover(d,"a",t["token"],3,name="again.json");assert p2.returncode==0 and s2["recovered"]==0 and len(hsm_rows(d))==3

    def test_preexpiry_takeover_remains_rejected(self):
        """Milestone 1 still prevents another node from stealing an unexpired lease."""
        with tempfile.TemporaryDirectory() as d:
            init(d,100);_,a=acquire(d,"a",100)
            p,b=acquire(d,"b",199)
            assert p.returncode!=0 and b is None
            assert run("check-lease","--state",d,"--node","a","--token",a["token"],"--now",199).returncode==0

    def test_tampered_epoch_cannot_reach_signing_path(self):
        """A matching owner name with a fabricated epoch is rejected before request preparation."""
        with tempfile.TemporaryDirectory() as d:
            init(d);_,t=acquire(d,"a",0);r=request(d,"r","auth-tamper","x=t")
            p,_=sign(d,"a","a:999",1,r)
            assert p.returncode!=0 and status(d)["request_count"]==0 and len(hsm_rows(d))==0

    def test_stale_lease_cannot_sign_or_recover(self):
        """A former owner cannot sign or recover pending work after a fenced takeover."""
        with tempfile.TemporaryDirectory() as d:
            init(d,10);_,a=acquire(d,"a",0);r=request(d,"r","auth-stale","x=s")
            assert sign(d,"a",a["token"],1,r,crash="after_prepare")[0].returncode==75
            _,b=acquire(d,"b",10)
            assert recover(d,"a",a["token"],11)[0].returncode!=0
            assert recover(d,"b",b["token"],11,name="b.json")[0].returncode==0
