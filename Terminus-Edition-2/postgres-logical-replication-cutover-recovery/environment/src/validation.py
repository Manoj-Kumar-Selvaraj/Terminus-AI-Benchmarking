# ruff: noqa
from __future__ import annotations

def target_schema():
    return {"schema_version":2,"nullable_defaults":True,"varchar_limit":40}
def validate_schema():
    return {"valid":True,"source_version":3,"target_version":2,"errors":[]}
def prepare_transaction(tx, target):
    # Rehearsal behavior: target defaults and narrow columns are applied silently.
    out=[]
    for op in tx["operations"]:
        op=dict(op)
        if "row" in op:
            row=dict(op["row"])
            if op["table"]=="communication_preference" and row.get("quiet_hours_start") is None: row["quiet_hours_start"]="00:00"
            if op["table"]=="customer_profile" and isinstance(row.get("display_name"),str): row["display_name"]=row["display_name"][:40]
            op["row"]=row
        out.append(op)
    return out
