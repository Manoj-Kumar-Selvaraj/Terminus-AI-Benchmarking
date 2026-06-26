# ruff: noqa
from __future__ import annotations
from .state import controller_lock,load_json,save_json,journal_once

def rollback(operation_id,cutover_operation_id=None):
    with controller_lock():
        source=load_json("source-database.json")
        target=load_json("target-database.json")
        state=load_json("cutover-state.json")
        # Bug: treats the entire subscriber history as reverse writes.
        for item in target.get("transaction_ledger",[]): source["transaction_ledger"].append(dict(item))
        target["writable"]=False
        source["writable"]=True
        save_json("target-database.json",target)
        save_json("source-database.json",source)
        state["rollback"]={"operation_id":operation_id,"status":"committed"}
        state["phase"]="ROLLBACK_COMMITTED"
        save_json("cutover-state.json",state)
        journal_once("rollback:"+operation_id,{"kind":"rollback","phase":"ROLLBACK_COMMITTED"})
        return state["rollback"]
