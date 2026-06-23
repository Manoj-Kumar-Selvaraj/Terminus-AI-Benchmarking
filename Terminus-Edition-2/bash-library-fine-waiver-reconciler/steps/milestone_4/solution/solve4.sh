#!/usr/bin/env bash
set -euo pipefail

python3 <<'PY'
from pathlib import Path

path = Path("/app/scripts/reconcile.sh")
text = path.read_text()

text = text.replace(
    'CALENDAR="/app/config/cutoff_calendar.txt"',
    'CALENDAR="/app/config/cutoff_calendar.txt"\nCHANNELS="/app/config/channels.csv"',
)
text = text.replace(
    '        APP) printf "%s\\n" "MOBILE" ;;',
    '        APP) printf "%s\\n" "MOBILE" ;;\n        KSK) printf "%s\\n" "FRONT" ;;',
)
text = text.replace(
    '''is_allowed() {
    case "$1" in
        FRONT|ONLINE|MOBILE) return 0 ;;
        *) return 1 ;;
    esac
}''',
    '''declare -A allowed_desks=()

load_allowed_desks() {
    while IFS=',' read -r desk enabled _; do
        desk=$(trim "${desk:-}")
        enabled=$(upper "$(trim "${enabled:-}")")
        [[ "$desk" == "desk" ]] && continue
        if [[ "$enabled" == "TRUE" ]]; then
            allowed_desks["$(canon_dim "$desk")"]=1
        fi
    done < "$CHANNELS"
}

is_allowed() {
    [[ -n "${allowed_desks[$1]:-}" ]]
}''',
)
text = text.replace(
    "declare -a src_ids src_customers",
    "load_allowed_desks\ndeclare -a src_ids src_customers",
)

path.write_text(text)
PY

chmod +x /app/scripts/reconcile.sh
/app/scripts/run_batch.sh
