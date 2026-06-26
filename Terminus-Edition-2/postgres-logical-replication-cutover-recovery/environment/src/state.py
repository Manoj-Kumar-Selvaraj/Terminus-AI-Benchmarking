# ruff: noqa
from __future__ import annotations
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
APP=Path(os.environ.get("PG_REPL_APP","/app"))
STATE=APP/"state"

def load_json(name):
    with open(STATE/name,encoding="utf-8") as f: return json.load(f)
def save_json(name,obj):
    path=STATE/name
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    with open(tmp,"r+") as f:
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp,path)
def read_jsonl(name):
    p=STATE/name
    if not p.exists(): return []
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]
def append_jsonl(name,obj):
    with open(STATE/name,"a",encoding="utf-8") as f:
        f.write(json.dumps(obj,sort_keys=True)+"\n")
        f.flush()
        os.fsync(f.fileno())
def lsn_int(value):
    hi,lo=value.split("/")
    return(int(hi,16)<<32)+int(lo,16)
def format_lsn(value): return f"{value>>32:X}/{value & 0xffffffff:X}"
def config(name):
    with open(APP/"config"/name,encoding="utf-8") as f: return json.load(f)
def fingerprint(value): return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()
@contextlib.contextmanager
def controller_lock():
    STATE.mkdir(parents=True,exist_ok=True)
    with open(STATE/".controller.lock","a+") as f:
        fcntl.flock(f.fileno(),fcntl.LOCK_EX)
        try: yield
        finally: fcntl.flock(f.fileno(),fcntl.LOCK_UN)
def journal_once(event_id,event):
    rows=read_jsonl("migration-journal.jsonl")
    for row in rows:
        if row.get("event_id")==event_id: return row
    record={"event_id":event_id,**event}
    append_jsonl("migration-journal.jsonl",record)
    return record
def consume_failure(point):
    state=load_json("failure-injection.json")
    if state.get("point")==point:
        save_json("failure-injection.json",{"point":None})
        raise RuntimeError(f"injected failure at {point}")
