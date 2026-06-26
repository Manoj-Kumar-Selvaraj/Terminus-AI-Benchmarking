# ruff: noqa
from __future__ import annotations
import copy
import re
from .state import APP, controller_lock, load_json, save_json, read_jsonl, lsn_int
from . import validation

def parse_publication_sql():
    text=(APP/"migration/publication.sql").read_text(encoding="utf-8")
    tables=re.search(r"FOR\s+TABLE\s+(.+?)\s+WITH",text,re.I|re.S).group(1)
    ops=re.search(r"publish\s*=\s*'([^']+)'",text,re.I).group(1)
    return [x.strip() for x in tables.split(",")],[x.strip().lower() for x in ops.split(",")]
def repair_publication():
    tables,ops=parse_publication_sql()
    state=load_json("publication-state.json")
    state["tables"]=tables
    state["operations"]=ops
    state["revision"]+=1
    save_json("publication-state.json",state)
    # Bug: rebuilds the slot when metadata changes.
    slot=load_json("replication-slot.json")
    slot["creation_id"]="replacement-slot"
    save_json("replication-slot.json",slot)
    return state

def _find(rows,pk,key):
    for i,row in enumerate(rows):
        if row.get(pk)==key:return i
    return None

def _apply(target,op):
    table=op["table"]
    pk=target["schema"]["tables"][table]["pk"]
    rows=target["tables"].setdefault(table,[])
    if op["op"]=="insert": rows.append(copy.deepcopy(op["row"]))
    elif op["op"]=="update":
        i=_find(rows,pk,op["key"])
        if i is None: raise ValueError("missing row")
        rows[i].update(op.get("changes",{}))
    elif op["op"]=="delete": return

def replicate(until_lsn=None):
    with controller_lock():
        pub=load_json("publication-state.json")
        sub=load_json("subscription-state.json")
        target=load_json("target-database.json")
        for tx in read_jsonl("source-wal.jsonl"):
            if tx["transaction_id"] in sub["applied_transaction_ids"]: continue
            if until_lsn and lsn_int(tx["commit_lsn"])>lsn_int(until_lsn): break
            for op in validation.prepare_transaction(tx,target):
                if op["table"] in pub["tables"] and op["op"] in pub["operations"]: _apply(target,op)
            sub["applied_transaction_ids"].append(tx["transaction_id"])
            sub["last_applied_lsn"]=tx["commit_lsn"]
            save_json("target-database.json",target)
            save_json("subscription-state.json",sub)
        return {"status":"ok","last_applied_lsn":sub["last_applied_lsn"]}
