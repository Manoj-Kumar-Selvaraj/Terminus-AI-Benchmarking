# ruff: noqa
from __future__ import annotations
from .state import controller_lock,load_json,save_json,journal_once

def readiness(fence_lsn=None):
    with controller_lock():
        source=load_json("source-database.json")
        target=load_json("target-database.json")
        state=load_json("cutover-state.json")
        state["generation_counter"]+=1
        state["phase"]="READY"
        state["readiness"]={"valid":True,"generation":state["generation_counter"],"source_lsn":source["current_lsn"],"target_lsn":target["current_lsn"],"fence_lsn":fence_lsn or source["current_lsn"]}
        save_json("cutover-state.json",state)
        return state["readiness"]
def cutover(operation_id):
    with controller_lock():
        state=load_json("cutover-state.json")
        source=load_json("source-database.json")
        target=load_json("target-database.json")
        target["writable"]=True
        save_json("target-database.json",target)
        source["writable"]=False
        save_json("source-database.json",source)
        state["phase"]="CUTOVER_COMMITTED"
        state["cutover"]={"operation_id":operation_id,"status":"committed"}
        save_json("cutover-state.json",state)
        journal_once("cutover:"+operation_id,{"kind":"cutover","phase":"CUTOVER_COMMITTED"})
        return state["cutover"]
