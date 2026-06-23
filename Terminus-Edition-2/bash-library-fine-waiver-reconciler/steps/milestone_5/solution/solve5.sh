#!/usr/bin/env bash
set -euo pipefail

python3 <<'PY'
from pathlib import Path

path = Path("/app/scripts/reconcile.sh")
text = path.read_text()

text = text.replace(
    'CHANNELS="/app/config/channels.csv"',
    'CHANNELS="/app/config/channels.csv"\nPROFILE="/app/config/run_profile.ini"\nMAX_OPEN_DAYS=2',
)
text = text.replace(
    '''open_days_after_through() {
    local start finish day status count
    start=$(trim "$1")
    finish=$(trim "$2")
    [[ -n "$start" && -n "$finish" ]] || return 1
    [[ "$start" > "$finish" ]] && return 1
    count=0
    while read -r day status _; do
        day=$(trim "$day")
        status=$(upper "$(trim "${status:-}")")
        if [[ "$status" == "OPEN" && "$day" > "$start" && ( "$day" < "$finish" || "$day" == "$finish" ) ]]; then
            count=$((count + 1))
        fi
    done < "$CALENDAR"
    [[ $count -le 2 ]]
}''',
    '''load_run_profile() {
    while IFS='=' read -r key val; do
        key=$(trim "${key:-}")
        val=$(trim "${val:-}")
        if [[ "$key" == "waiver_open_window_days" ]]; then
            MAX_OPEN_DAYS=$((10#$val))
        fi
    done < "$PROFILE"
}

open_days_after_through() {
    local start finish day status count
    start=$(trim "$1")
    finish=$(trim "$2")
    [[ -n "$start" && -n "$finish" ]] || return 1
    [[ "$start" > "$finish" ]] && return 1
    count=0
    while read -r day status _; do
        day=$(trim "$day")
        status=$(upper "$(trim "${status:-}")")
        if [[ "$status" == "OPEN" && "$day" > "$start" && ( "$day" < "$finish" || "$day" == "$finish" ) ]]; then
            count=$((count + 1))
        fi
    done < "$CALENDAR"
    [[ $count -le $MAX_OPEN_DAYS ]]
}''',
)
text = text.replace(
    "load_allowed_desks\ndeclare -a src_ids",
    "load_allowed_desks\nload_run_profile\ndeclare -a src_ids",
)

path.write_text(text)
PY

chmod +x /app/scripts/reconcile.sh
/app/scripts/run_batch.sh
