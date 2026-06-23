#!/bin/bash
set -euo pipefail
cat > /app/src/premium_batch.pli <<'PLI'
/* insurance premium surcharge adjudicator batch control deck */
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE OFF
%SET WINDOW_MODE OFF
PLI
python3 - <<'PY'
from pathlib import Path

path = Path("/app/scripts/pli_premium.awk")
text = path.read_text()

old_keys = """function keys_ok(si, ai,    fi, f) {
    if (KEY_COMPARE == "PREFIX5") {
        return substr(src[si, "policy_id"], 1, 5) == substr(act[ai, "policy_id"], 1, 5) && src[si, "premium_cents"] == act[ai, "premium_cents"]
    }
    for (fi = 1; fi <= 2; fi++) {
        f = key_fields[fi]
        if (up(src[si, f]) != up(act[ai, f])) return 0
    }
    return 1
}"""
new_keys = """function keys_ok(si, ai,    fi, f) {
    if (KEY_COMPARE == "PREFIX5") {
        return substr(src[si, "policy_id"], 1, 5) == substr(act[ai, "policy_id"], 1, 5) && src[si, "premium_cents"] == act[ai, "premium_cents"]
    }
    for (fi = 1; fi <= nkeys; fi++) {
        f = key_fields[fi]
        if (f == "premium_cents") {
            if (!isint(src[si, f]) || !isint(act[ai, f]) || 0 + src[si, f] != 0 + act[ai, f]) return 0
        } else if (f == "risk_code") {
            if (risk_key(src[si, f]) != risk_key(act[ai, f])) return 0
        } else if (up(src[si, f]) != up(act[ai, f])) return 0
    }
    return 1
}"""
old_select = '            if (best == 0) best = si'
new_select = '            if (best == 0 || src[si, "ingest_ts"] > src[best, "ingest_ts"] || (src[si, "ingest_ts"] == src[best, "ingest_ts"] && si < best)) best = si'

if old_keys in text:
    text = text.replace(old_keys, new_keys, 1)
elif new_keys not in text:
    raise SystemExit("unexpected keys_ok implementation")

if old_select in text:
    text = text.replace(old_select, new_select, 1)
elif new_select not in text:
    raise SystemExit("unexpected candidate selection implementation")

path.write_text(text)
PY
