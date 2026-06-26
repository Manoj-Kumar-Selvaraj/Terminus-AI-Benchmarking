# ruff: noqa
from __future__ import annotations
import hashlib
import json
import os
import subprocess
import tempfile
import uuid
from pathlib import Path
APP=Path(os.environ.get("PG_REPL_APP","/app"))
TOOLS=Path(os.environ.get("PG_REPL_TOOLS","/opt/task-tools"))
RUNTIME=os.environ.get("PG_REPL_RUNTIME","/opt/task-tools/pg-repl-runtime")
_EXPECTED_PROTECTED={
    TOOLS/"protected-hashes.json":"f6b8dd5854755fd0278131f56930d7cda2a25eb06fff38e093ebd1a2b5f03fb5",
    TOOLS/"pg-repl-runtime":"83b528933e162b150d613a0dd83b09b4d944ae925f8d7f8e31c331fa0aa560fc",
    TOOLS/"runtime_lib.py":"596b15528053f459e243f508a1e38c3e7c70d9aaa883d552afaab144f9e2a70b",
    APP/"protected-manifest.json":"a1ed9208fff63266ea773d977809ba7ff499584d633209c38a24d40259b74666",
}

def assert_protected_toolchain():
    for path,expected in _EXPECTED_PROTECTED.items():
        if not path.is_file():
            raise AssertionError(f"protected artifact missing: {path}")
        actual=hashlib.sha256(path.read_bytes()).hexdigest()
        if actual!=expected:
            raise AssertionError(f"protected artifact changed: {path}")

def run(*args,check=True):
    assert_protected_toolchain()
    env=os.environ.copy()
    cp=subprocess.run([RUNTIME,*map(str,args)],text=True,capture_output=True,env=env)
    if check and cp.returncode!=0: raise AssertionError(f"command failed: {args}\nstdout={cp.stdout}\nstderr={cp.stderr}")
    data=None
    text=cp.stdout.strip() if cp.returncode==0 else cp.stderr.strip().splitlines()[-1] if cp.stderr.strip() else ""
    if text:
        try: data=json.loads(text)
        except json.JSONDecodeError: data={"raw":text}
    return cp,data

def reset(): return run("reset")[1]
def inspect(what): return run("inspect",what)[1]
def state(name): return json.loads((APP/"state"/name).read_text())
def save_state(name,obj): (APP/"state"/name).write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n")
def lsn_int(value):
    hi,lo=value.split("/")
    return(int(hi,16)<<32)+int(lo,16)
def lsn(value): return f"{value>>32:X}/{value & 0xffffffff:X}"
def tx(operations,delta=16,schema_version=3,txid=None):
    source=state("source-database.json")
    return {"transaction_id":txid or "txn-"+uuid.uuid4().hex,"commit_lsn":lsn(lsn_int(source["current_lsn"])+delta),"commit_timestamp":"2026-06-18T12:00:00Z","source_epoch":source["source_epoch"],"schema_version":schema_version,"operations":operations}
def write_stream(rows):
    f=tempfile.NamedTemporaryFile("w",delete=False,suffix=".jsonl")
    for row in rows: f.write(json.dumps(row,sort_keys=True)+"\n")
    f.close()
    return f.name
def apply_source(rows):
    path=write_stream(rows)
    return run("apply-source","--file",path)[1]
def apply_target(rows):
    path=write_stream(rows)
    return run("apply-target","--file",path)[1]
def row(cluster,table,pk,value):
    db=inspect(cluster)
    return next((r for r in db["tables"].get(table,[])if r.get(pk)==value),None)
def repair(): return run("repair-publication")[1]
def replicate(until=None):
    args=["replicate"]
    if until: args += ["--until-lsn",until]
    return run(*args)[1]
def prepare_ready(with_fixture=False):
    reset()
    repair()
    if with_fixture:
        run("apply-source","--file",str(APP/"data/change-stream.jsonl"))
        replicate()
    run("sync-sequences")
    return run("readiness")[1]
