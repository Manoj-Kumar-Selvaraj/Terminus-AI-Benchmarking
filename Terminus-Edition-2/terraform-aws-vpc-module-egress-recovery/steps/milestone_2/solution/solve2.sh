#!/usr/bin/env bash
set -Eeuo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "/steps/milestone_1/solution/solve1.sh"
python3 - <<'PY'
from pathlib import Path
p = Path("/app/infra/modules/vpc/module.py")
s = p.read_text()
needle = '            errs.append(f"missing {t} tier")\n    if errs:'
insert = '''            errs.append(f"missing {t} tier")
    for ep in c.get("gateway_endpoints", []):
        if ep.get("service") not in {"s3", "dynamodb"}:
            errs.append(
                "unsupported gateway endpoint service: " + str(ep.get("service"))
            )
    if errs:'''
if needle not in s:
    raise SystemExit("validate_config anchor missing")
s = s.replace(needle, insert, 1)
s = s.replace(
    "    eligible = [rt[\"id\"] for rt in rts]",
    '    eligible = [rt["id"] for rt in rts if rt["tier"] == "app"]',
)
p.write_text(s)
PY
