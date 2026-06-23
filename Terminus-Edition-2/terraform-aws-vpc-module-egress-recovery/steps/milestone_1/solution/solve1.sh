#!/usr/bin/env bash
set -Eeuo pipefail
APP_DIR="${APP_DIR:-/app}"
python3 - <<'PY'
from pathlib import Path
p = Path("/app/infra/modules/vpc/module.py")
s = p.read_text()
s = s.replace(
    '    return nats[0]["id"]',
    '    return next((n["id"] for n in nats if n.get("az") == az), None)',
)
s = s.replace(
    '        elif s["tier"] == "data" and _nat(c, s["az"]):\n'
    '            routes.append({"destination": "0.0.0.0/0", "target": _nat(c, s["az"])})\n',
    "",
)
p.write_text(s)
PY
