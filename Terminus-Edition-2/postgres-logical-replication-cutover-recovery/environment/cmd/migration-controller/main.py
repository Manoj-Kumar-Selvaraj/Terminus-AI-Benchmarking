# ruff: noqa
#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from src import controller

def main():
    p=argparse.ArgumentParser()
    sub=p.add_subparsers(dest="cmd",required=True)
    sub.add_parser("repair-publication")
    a=sub.add_parser("replicate")
    a.add_argument("--until-lsn")
    sub.add_parser("validate-schema")
    sub.add_parser("validate-sequences")
    sub.add_parser("sync-sequences")
    a=sub.add_parser("readiness")
    a.add_argument("--fence-lsn")
    a=sub.add_parser("cutover")
    a.add_argument("--operation-id",required=True)
    a=sub.add_parser("rollback")
    a.add_argument("--operation-id",required=True)
    a.add_argument("--cutover-operation-id")
    n=p.parse_args()
    if n.cmd=="repair-publication": out=controller.repair_publication()
    elif n.cmd=="replicate": out=controller.replicate(n.until_lsn)
    elif n.cmd=="validate-schema": out=controller.validate_schema()
    elif n.cmd=="validate-sequences": out=controller.validate_sequences()
    elif n.cmd=="sync-sequences": out=controller.sync_sequences()
    elif n.cmd=="readiness": out=controller.readiness(n.fence_lsn)
    elif n.cmd=="cutover": out=controller.cutover(n.operation_id)
    else: out=controller.rollback(n.operation_id,n.cutover_operation_id)
    print(json.dumps(out,indent=2,sort_keys=True))
if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(json.dumps({"status": "error", "error": str(e)}), file=sys.stderr)
        raise SystemExit(2) from e
