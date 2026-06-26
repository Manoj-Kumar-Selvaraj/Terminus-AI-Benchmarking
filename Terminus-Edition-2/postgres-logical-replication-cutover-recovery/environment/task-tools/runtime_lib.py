# ruff: noqa
from __future__ import annotations
import contextlib
import copy
import fcntl
import hashlib
import importlib
import json
import os
import shutil
import sys
import uuid
from pathlib import Path

APP=Path(os.environ.get("PG_REPL_APP","/app"))
TOOLS=Path(os.environ.get("PG_REPL_TOOLS","/opt/task-tools"))
STATE=APP/"state"

def load(path):
    with open(path,encoding="utf-8") as f: return json.load(f)
def save(path,obj):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+".tmp")
    tmp.write_text(json.dumps(obj,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    os.replace(tmp,path)
def read_jsonl(path):
    p=Path(path)
    if not p.exists(): return []
    return [json.loads(line) for line in p.read_text(encoding="utf-8").splitlines() if line.strip()]
def append_jsonl(path,obj):
    with open(path,"a",encoding="utf-8") as f:
        f.write(json.dumps(obj,sort_keys=True)+"\n")
        f.flush()
        os.fsync(f.fileno())
def lsn_int(value):
    hi,lo=value.split("/")
    return(int(hi,16)<<32)+int(lo,16)
def format_lsn(value): return f"{value>>32:X}/{value & 0xffffffff:X}"

def verify_integrity():
    manifest=load(TOOLS/"protected-hashes.json")
    bad=[]
    for raw,expected in manifest.items():
        if raw.startswith("/app/"):
            p=APP/raw.removeprefix("/app/")
        elif raw.startswith("/opt/task-tools/"):
            p=TOOLS/raw.removeprefix("/opt/task-tools/")
        else:
            p=Path(raw)
        if not p.exists() or hashlib.sha256(p.read_bytes()).hexdigest()!=expected: bad.append(raw)
    if bad: raise RuntimeError("protected artifact integrity failure: "+", ".join(sorted(bad)))
    return {"status":"ok","checked":len(manifest)}

def reset():
    verify_integrity()
    STATE.mkdir(parents=True,exist_ok=True)
    for p in STATE.iterdir():
        if p.is_file(): p.unlink()
        elif p.is_dir(): shutil.rmtree(p)
    for src in (TOOLS/"baseline-state").iterdir():
        shutil.copy2(src,STATE/src.name)
    return {"status":"reset","source_lsn":"0/500"}


@contextlib.contextmanager
def state_lock():
    STATE.mkdir(parents=True,exist_ok=True)
    with open(STATE/".controller.lock","a+") as f:
        fcntl.flock(f.fileno(),fcntl.LOCK_EX)
        try: yield
        finally: fcntl.flock(f.fileno(),fcntl.LOCK_UN)

def _row_index(db,table,key):
    spec=db["schema"]["tables"][table]
    pk=spec["pk"]
    for i,row in enumerate(db["tables"].setdefault(table,[])):
        if row.get(pk)==key: return i
    return None

def _apply_ops(db,ops):
    work=copy.deepcopy(db)
    for op in ops:
        table=op["table"]
        if table not in work["schema"]["tables"]: raise ValueError(f"unknown table {table}")
        pk=work["schema"]["tables"][table]["pk"]
        if op["op"]=="insert":
            row=copy.deepcopy(op["row"])
            key=row.get(pk)
            if key is None: raise ValueError(f"missing primary key {table}.{pk}")
            if _row_index(work,table,key) is not None: raise ValueError(f"duplicate key {table}:{key}")
            work["tables"].setdefault(table,[]).append(row)
        elif op["op"]=="update":
            idx=_row_index(work,table,op["key"])
            if idx is None: raise ValueError(f"missing update row {table}:{op['key']}")
            work["tables"][table][idx].update(copy.deepcopy(op.get("changes",{})))
        elif op["op"]=="delete":
            idx=_row_index(work,table,op["key"])
            if idx is None: raise ValueError(f"missing delete row {table}:{op['key']}")
            del work["tables"][table][idx]
        else: raise ValueError(f"unknown operation {op['op']}")
    return work

def _normalize_tx(tx,source):
    tx=copy.deepcopy(tx)
    tx.setdefault("transaction_id","txn-"+uuid.uuid4().hex)
    tx.setdefault("commit_timestamp","2026-06-17T12:00:00Z")
    tx.setdefault("source_epoch",source.get("source_epoch",1))
    tx.setdefault("schema_version",source["schema"]["schema_version"])
    if "commit_lsn" not in tx: tx["commit_lsn"]=format_lsn(lsn_int(source["current_lsn"])+16)
    required=("transaction_id","commit_lsn","commit_timestamp","source_epoch","operations")
    missing=[k for k in required if k not in tx]
    if missing: raise ValueError("missing transaction fields: "+", ".join(missing))
    return tx

def apply_source(file):
    verify_integrity()
    with state_lock():
        source=load(STATE/"source-database.json")
        if not source["writable"]: raise RuntimeError("source writer is fenced")
        slot=load(STATE/"replication-slot.json")
        applied=[]
        for raw in read_jsonl(file):
            tx=_normalize_tx(raw,source)
            if tx["transaction_id"] in source["accepted_transaction_ids"]: continue
            if lsn_int(tx["commit_lsn"])<=lsn_int(source["current_lsn"]): raise ValueError("commit_lsn must advance")
            source=_apply_ops(source,tx["operations"])
            source["current_lsn"]=tx["commit_lsn"]
            source["accepted_transaction_ids"].append(tx["transaction_id"])
            source["transaction_ledger"].append({"transaction_id":tx["transaction_id"],"commit_lsn":tx["commit_lsn"],"origin":"source"})
            append_jsonl(STATE/"source-wal.jsonl",tx)
            applied.append(tx["transaction_id"])
        save(STATE/"source-database.json",source)
        slot["retained_wal_bytes"]=max(0,lsn_int(source["current_lsn"])-lsn_int(slot["restart_lsn"]))
        save(STATE/"replication-slot.json",slot)
        return {"status":"applied","transactions":applied,"source_lsn":source["current_lsn"]}

def apply_target(file):
    verify_integrity()
    with state_lock():
        target=load(STATE/"target-database.json")
        if not target["writable"]: raise RuntimeError("target writer is fenced")
        accepted=[]
        for raw in read_jsonl(file):
            tx=copy.deepcopy(raw)
            tx.setdefault("transaction_id","target-"+uuid.uuid4().hex)
            tx.setdefault("commit_timestamp","2026-06-17T12:30:00Z")
            tx.setdefault("source_epoch",target.get("source_epoch",1)+1)
            tx.setdefault("schema_version",3)
            if tx["transaction_id"] in target["accepted_transaction_ids"]: continue
            target=_apply_ops(target,tx["operations"])
            target["accepted_transaction_ids"].append(tx["transaction_id"])
            target["target_write_sequence"]=target.get("target_write_sequence",0)+1
            target["transaction_ledger"].append({"transaction_id":tx["transaction_id"],"origin":"target","sequence":target["target_write_sequence"]})
            append_jsonl(STATE/"target-write-log.jsonl",tx)
            accepted.append(tx["transaction_id"])
        save(STATE/"target-database.json",target)
        return {"status":"applied","transactions":accepted}

def _controller():
    if str(APP) not in sys.path: sys.path.insert(0,str(APP))
    for name in list(sys.modules):
        if name=="src" or name.startswith("src."): del sys.modules[name]
    return importlib.import_module("src.controller")

def controller_call(name,*args,**kwargs):
    verify_integrity()
    return getattr(_controller(), name)(*args, **kwargs)

def inspect(name):
    verify_integrity()
    mapping={"publication":"publication-state.json","subscription":"subscription-state.json","slot":"replication-slot.json","source":"source-database.json","target":"target-database.json","cutover":"cutover-state.json"}
    if name=="journal": return read_jsonl(STATE/"migration-journal.jsonl")
    if name not in mapping: raise ValueError("unknown inspection target")
    return load(STATE/mapping[name])

def inject(point):
    save(STATE / "failure-injection.json", {"point": point})
    return {"status": "armed", "point": point}


def clear_failure():
    save(STATE / "failure-injection.json", {"point": None})
    return {"status": "cleared"}

def restart_controller():
    p=STATE/"controller-cache.json"
    if p.exists(): p.unlink()
    return {"status":"restarted","durable_state_preserved":True}
