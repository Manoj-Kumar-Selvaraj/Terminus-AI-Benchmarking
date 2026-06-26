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

class TestMilestone1:
    def test_active_lease_cannot_be_stolen_before_expiry(self):
        """A different node is rejected while the coordinator-time lease remains active."""
        with tempfile.TemporaryDirectory() as d:
            init(d);p,a=acquire(d,"a",1000);assert p.returncode==0
            p2,b=acquire(d,"b",1050);assert p2.returncode!=0 and b is None
            assert status(d)["owner"]=="a" and status(d)["epoch"]==1

    def test_takeover_increments_epoch_and_fences_former_owner(self):
        """Post-expiry takeover increments the epoch and invalidates the former owner's token."""
        with tempfile.TemporaryDirectory() as d:
            init(d);_,a=acquire(d,"a",1000);_,b=acquire(d,"b",1100)
            assert b["epoch"]==2
            p=run("check-lease","--state",d,"--node","a","--token",a["token"],"--now",1101)
            assert p.returncode!=0
            assert run("check-lease","--state",d,"--node","b","--token",b["token"],"--now",1101).returncode==0

    def test_same_owner_reacquire_is_idempotent(self):
        """An active owner reacquiring does not bump its epoch or extend expiration."""
        with tempfile.TemporaryDirectory() as d:
            init(d);_,a=acquire(d,"a",50);_,again=acquire(d,"a",80)
            assert again==a and status(d)["epoch"]==1

    def test_renew_preserves_epoch_and_uses_coordinator_time(self):
        """Renewal keeps the fencing epoch and computes expiry from the supplied coordinator time."""
        with tempfile.TemporaryDirectory() as d:
            init(d,200);_,a=acquire(d,"a",100)
            out=Path(d)/"renew.json";p=run("renew","--state",d,"--node","a","--token",a["token"],"--now",250,"--out",out)
            assert p.returncode==0
            r=json.loads(out.read_text());assert r["token"]==a["token"] and r["expires"]==450
            assert status(d)["epoch"]==1

    def test_tampered_or_expired_token_is_rejected(self):
        """Owner-name matches are insufficient: epoch tampering and expiry both fail validation."""
        with tempfile.TemporaryDirectory() as d:
            init(d,50);_,a=acquire(d,"a",10)
            assert run("check-lease","--state",d,"--node","a","--token","a:999","--now",20).returncode!=0
            assert run("check-lease","--state",d,"--node","a","--token",a["token"],"--now",60).returncode!=0

    def test_concurrent_acquisition_has_one_winner(self):
        """Two simultaneous acquisitions at one coordinator time yield exactly one owner and one epoch."""
        with tempfile.TemporaryDirectory() as d:
            init(d)
            def one(n): return acquire(d,n,500)[0].returncode
            with ThreadPoolExecutor(max_workers=2) as ex: codes=list(ex.map(one,["a","b"]))
            assert sorted(codes)==[0,2]
            assert status(d)["epoch"]==1 and status(d)["owner"] in {"a","b"}
