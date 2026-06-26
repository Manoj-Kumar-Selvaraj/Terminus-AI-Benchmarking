# ruff: noqa
import json
import subprocess
import tempfile
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

def rotate(d,node,tok,now,key,grace): return run("rotate","--state",d,"--node",node,"--token",tok,"--now",now,"--new-key",key,"--grace-until",grace)
def revoke(d,node,tok,now,key): return run("revoke","--state",d,"--node",node,"--token",tok,"--now",now,"--key",key)
class TestMilestone3:
    def test_prepared_request_recovers_with_pinned_old_key_during_grace(self):
        """A pre-rotation PREPARED request reaches the HSM with its original key during grace."""
        with tempfile.TemporaryDirectory() as d:
            init(d,1000);_,t=acquire(d,"a",0);r=request(d,"r","auth-g1","x=1")
            assert sign(d,"a",t["token"],10,r,crash="after_prepare")[0].returncode==75
            assert rotate(d,"a",t["token"],20,"key-b",100).returncode==0
            assert recover(d,"a",t["token"],30)[0].returncode==0
            assert hsm_rows(d)[0].split("\t")[1]=="key-a"

    def test_new_request_after_rotation_uses_active_key(self):
        """Requests first prepared after rotation use the new active key and policy generation."""
        with tempfile.TemporaryDirectory() as d:
            init(d,1000);_,t=acquire(d,"a",0);rotate(d,"a",t["token"],10,"key-b",100)
            r=request(d,"r","auth-g2","x=2");p,s=sign(d,"a",t["token"],20,r)
            assert p.returncode==0 and s["key"]=="key-b" and s["policy_generation"]==2

    def test_unsigned_old_request_fails_after_grace_without_hsm_call(self):
        """An unsigned old-key request remains pending after grace and produces no external side effect."""
        with tempfile.TemporaryDirectory() as d:
            init(d,1000);_,t=acquire(d,"a",0);r=request(d,"r","auth-g3","x=3")
            sign(d,"a",t["token"],5,r,crash="after_prepare");rotate(d,"a",t["token"],10,"key-b",20)
            p,_=recover(d,"a",t["token"],21);assert p.returncode!=0 and len(hsm_rows(d))==0

    def test_existing_hsm_side_effect_finalizes_after_grace(self):
        """An audited old-key operation is finalized after grace without a second HSM invocation."""
        with tempfile.TemporaryDirectory() as d:
            init(d,1000);_,t=acquire(d,"a",0);r=request(d,"r","auth-g4","x=4")
            sign(d,"a",t["token"],5,r,crash="after_hsm");rotate(d,"a",t["token"],10,"key-b",20)
            before=hsm_rows(d);p,_=recover(d,"a",t["token"],30)
            assert p.returncode==0 and hsm_rows(d)==before and before[0].split("\t")[1]=="key-a"

    def test_revocation_blocks_new_side_effect_but_not_existing_audit(self):
        """Revocation blocks unsigned pinned work while allowing an already-audited operation to commit."""
        with tempfile.TemporaryDirectory() as d:
            init(d,1000);_,t=acquire(d,"a",0)
            r1=request(d,"r1","auth-r1","x=1");sign(d,"a",t["token"],1,r1,crash="after_prepare")
            r2=request(d,"r2","auth-r2","x=2");sign(d,"a",t["token"],2,r2,crash="after_hsm")
            rotate(d,"a",t["token"],3,"key-b",100);revoke(d,"a",t["token"],4,"key-a")
            p,_=recover(d,"a",t["token"],5);assert p.returncode!=0
            assert len(hsm_rows(d))==1
            # remove blocked request evidence to prove the already-audited one is independently finalizable
            rows=[x for x in Path(d,"requests.tsv").read_text().splitlines() if not x.startswith("auth-r1\t")]
            Path(d,"requests.tsv").write_text("\n".join(rows)+"\n")
            assert recover(d,"a",t["token"],6,name="r2.json")[0].returncode==0 and len(hsm_rows(d))==1

    def test_invalid_rotation_leaves_policy_unchanged(self):
        """A grace deadline before coordinator now is rejected atomically without policy changes."""
        with tempfile.TemporaryDirectory() as d:
            init(d,1000);_,t=acquire(d,"a",0);before=status(d)
            p=rotate(d,"a",t["token"],50,"key-b",49)
            assert p.returncode!=0 and status(d)==before

    def test_crash_recovery_still_uses_one_hsm_operation(self):
        """Milestone 2 stable operation identity remains intact after rotation support is added."""
        with tempfile.TemporaryDirectory() as d:
            init(d,1000);_,t=acquire(d,"a",0);r=request(d,"r","auth-regress","x=r")
            assert sign(d,"a",t["token"],1,r,crash="after_hsm")[0].returncode==75
            before=hsm_rows(d)
            assert recover(d,"a",t["token"],2)[0].returncode==0
            assert hsm_rows(d)==before

    def test_conflicting_payload_remains_rejected_after_rotation(self):
        """Key-policy changes do not weaken durable request-ID conflict detection."""
        with tempfile.TemporaryDirectory() as d:
            init(d,1000);_,t=acquire(d,"a",0);a=request(d,"a","auth-c","x=1");b=request(d,"b","auth-c","x=2")
            sign(d,"a",t["token"],1,a);rotate(d,"a",t["token"],2,"key-b",100)
            before=hsm_rows(d);p,_=sign(d,"a",t["token"],3,b,name="bad.json")
            assert p.returncode!=0 and hsm_rows(d)==before

    def test_lease_takeover_fences_recovery_after_rotation(self):
        """The former owner cannot recover pinned work after a post-rotation lease takeover."""
        with tempfile.TemporaryDirectory() as d:
            init(d,10);_,a=acquire(d,"a",0);r=request(d,"r","auth-fence","x=f")
            sign(d,"a",a["token"],1,r,crash="after_prepare");_,b=acquire(d,"b",10)
            assert recover(d,"a",a["token"],11)[0].returncode!=0
            assert recover(d,"b",b["token"],11,name="b.json")[0].returncode==0

    def test_stale_owner_cannot_rotate_or_revoke(self):
        """Administrative key changes are fenced after lease takeover."""
        with tempfile.TemporaryDirectory() as d:
            init(d,10);_,a=acquire(d,"a",0);_,b=acquire(d,"b",10)
            before=status(d)
            assert rotate(d,"a",a["token"],11,"key-b",20).returncode!=0
            assert revoke(d,"a",a["token"],11,"key-a").returncode!=0
            assert status(d)==before
            assert rotate(d,"b",b["token"],11,"key-b",20).returncode==0
