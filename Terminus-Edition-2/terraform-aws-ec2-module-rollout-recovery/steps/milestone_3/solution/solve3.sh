#!/usr/bin/env bash
set -Eeuo pipefail
bash "/steps/milestone_2/solution/solve2.sh"
python3 - <<'PY'
from pathlib import Path

p = Path("/app/infra/modules/ec2/module.py")
s = p.read_text()
broken = """def _refresh(c, inst, prior):
    return {
        "strategy": "terminate-first",
        "min_healthy_percentage": 50,
        "events": ["terminated_old_before_replacement"],
    }"""

fixed = """def _refresh(c, inst, prior):
    min_h = max(1, round(len(inst) * 0.9))
    if c.get("candidate_health", "passing") != "passing":
        return {
            "strategy": "canary-then-batch",
            "min_healthy_percentage": 90,
            "min_healthy_instances": min_h,
            "status": "rolled_back",
            "events": ["canary_failed", "kept_previous_capacity"],
            "kept_instance_ids": [i["id"] for i in prior.get("instances", [])],
        }
    return {
        "strategy": "canary-then-batch",
        "min_healthy_percentage": 90,
        "min_healthy_instances": min_h,
        "status": "ready",
        "events": ["canary_healthy", "batch_replaced"],
    }"""

if broken not in s:
    raise SystemExit("_refresh anchor missing")
s = s.replace(broken, fixed, 1)
p.write_text(s)
PY
