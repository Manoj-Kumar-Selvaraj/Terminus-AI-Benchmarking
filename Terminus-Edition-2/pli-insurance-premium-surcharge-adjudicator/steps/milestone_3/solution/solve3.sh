#!/bin/bash
set -euo pipefail
cat > /app/src/premium_batch.pli <<'PLI'
/* insurance premium surcharge adjudicator batch control deck */
%SET KEY_COMPARE FULL
%SET CONSUME ON
%SET ALIAS_MODE ON
%SET WINDOW_MODE ON
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
old_alias = '            split(val, parts, "=>"); aliases[up(parts[1])] = up(parts[2]); aliases[up(parts[2])] = up(parts[2])'
new_alias = """            split(val, parts, "=>")
            alias_raw = up(parts[1]); alias_canonical = trim(parts[2])
            if (alias_raw != "" && alias_canonical != "") {
                aliases[alias_raw] = alias_canonical
                aliases[up(alias_canonical)] = alias_canonical
            }"""
old_window = '        if (nts(o) && nts(c) && o <= at && at <= c) return 1'
new_window = '        if (nts(o) && nts(c) && o <= c && o <= st && st <= c && st <= at && at <= c) return 1'

for old, new, label in (
    (old_keys, new_keys, "keys_ok"),
    (old_select, new_select, "candidate selection"),
    (old_alias, new_alias, "alias parser"),
    (old_window, new_window, "fiscal-window"),
):
    if old in text:
        text = text.replace(old, new, 1)
    elif new not in text:
        raise SystemExit(f"unexpected {label} implementation")

path.write_text(text)
PY
