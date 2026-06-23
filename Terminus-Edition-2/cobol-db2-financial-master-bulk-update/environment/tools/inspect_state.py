#!/usr/bin/env python3
import json
import sys
from pathlib import Path

default_path = Path("/app/state/financial_master.json")
path = Path(sys.argv[1]) if len(sys.argv) > 1 else default_path
db = json.loads(path.read_text())
print(
    json.dumps(
        {
            "master_count": len(db.get("master", {})),
            "risk_count": len(db.get("risk", {})),
            "ledger_count": len(db.get("ledger", [])),
            "audit_count": len(db.get("audit", [])),
            "reject_count": len(db.get("rejects", [])),
            "checkpoint": db.get("checkpoint", {}),
        },
        indent=2,
        sort_keys=True,
    )
)
