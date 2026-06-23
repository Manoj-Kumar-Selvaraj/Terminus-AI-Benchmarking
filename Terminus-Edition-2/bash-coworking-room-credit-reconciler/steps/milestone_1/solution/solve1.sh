#!/usr/bin/env bash
set -euo pipefail
cat > /app/scripts/reconcile.sh <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
SRC="/app/data/bookings.csv"
ACT="/app/data/credits.csv"
REPORT="/app/out/credit_report.csv"
SUMMARY="/app/out/credit_summary.json"
ALIASES_FILE="/app/config/plan_aliases.csv"
CALENDAR="/app/config/cutoff_calendar.txt"
PROFILE="/app/config/run_profile.ini"
ENABLE_ALIASES=0
ENABLE_DATES=0
mkdir -p /app/out

trim() {
    local s="${1:-}"
    s="${s#"${s%%[![:space:]]*}"}"
    s="${s%"${s##*[![:space:]]}"}"
    printf "%s" "$s"
}
upper() { local s="${1:-}"; printf "%s" "${s^^}"; }
lower() { local s="${1:-}"; printf "%s" "${s,,}"; }
is_positive_int() {
    local v
    v=$(trim "${1:-}")
    [[ "$v" =~ ^[0-9]+$ ]] || return 1
    (( 10#$v > 0 ))
}
to_int() {
    local v
    v=$(trim "${1:-}")
    printf "%d" "$((10#$v))"
}
is_date() { [[ "${1:-}" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; }
is_allowed_plan() {
    case "${1:-}" in
        HOTDESK|PRIVATE|TEAM) return 0 ;;
        *) return 1 ;;
    esac
}

declare -A PLAN_ALIAS=()
load_aliases() {
    PLAN_ALIAS[HOTDESK]=HOTDESK
    PLAN_ALIAS[PRIVATE]=PRIVATE
    PLAN_ALIAS[TEAM]=TEAM
    [[ "$ENABLE_ALIASES" == "1" && -f "$ALIASES_FILE" ]] || return 0
    local header line key i idx_alias idx_canon idx_enabled alias canon enabled
    IFS= read -r header < "$ALIASES_FILE" || return 0
    declare -A amap=()
    IFS=',' read -r -a hcols <<< "$header"
    for i in "${!hcols[@]}"; do
        key=$(lower "$(trim "${hcols[$i]}")")
        amap[$key]=$i
    done
    idx_alias="${amap[alias]:-}"
    idx_canon="${amap[canonical]:-}"
    idx_enabled="${amap[enabled]:-}"
    [[ -n "$idx_alias" && -n "$idx_canon" && -n "$idx_enabled" ]] || return 0
    while IFS= read -r line; do
        [[ -n "$(trim "$line")" ]] || continue
        IFS=',' read -r -a cols <<< "$line"
        alias=$(upper "$(trim "${cols[$idx_alias]:-}")")
        canon=$(upper "$(trim "${cols[$idx_canon]:-}")")
        enabled=$(upper "$(trim "${cols[$idx_enabled]:-}")")
        [[ -n "$alias" ]] || continue
        is_allowed_plan "$canon" || continue
        case "$enabled" in TRUE|YES|1) ;; *) continue ;; esac
        if [[ -z "${PLAN_ALIAS[$alias]+set}" ]]; then
            PLAN_ALIAS[$alias]="$canon"
        fi
    done < <(tail -n +2 "$ALIASES_FILE")
}
canon_plan() {
    local value
    value=$(upper "$(trim "${1:-}")")
    if [[ -n "${PLAN_ALIAS[$value]+set}" ]]; then
        printf "%s" "${PLAN_ALIAS[$value]}"
    else
        printf "%s" "$value"
    fi
}

parse_header() {
    local map_name="$1" header="$2" i key
    local -n map_ref="$map_name"
    IFS=',' read -r -a header_cols <<< "$header"
    for i in "${!header_cols[@]}"; do
        key=$(lower "$(trim "${header_cols[$i]}")")
        map_ref[$key]=$i
    done
}
cell_by_index() {
    local line="$1" idx="${2:-}"
    local -a cols
    [[ -n "$idx" ]] || { printf ""; return 0; }
    IFS=',' read -r -a cols <<< "$line"
    trim "${cols[$idx]:-}"
}

max_open_days_back() {
    local line key val
    [[ -f "$PROFILE" ]] || { printf "2"; return 0; }
    while IFS= read -r line; do
        line=$(trim "$line")
        [[ -n "$line" ]] || continue
        [[ "$line" == \#* ]] && continue
        [[ "$line" == \[*\] ]] && continue
        [[ "$line" == *=* ]] || continue
        key=$(trim "${line%%=*}")
        val=$(trim "${line#*=}")
        if [[ "$key" == "max_open_days_back" && "$val" =~ ^[0-9]+$ && $((10#$val)) -gt 0 ]]; then
            printf "%d" "$((10#$val))"
            return 0
        fi
    done < "$PROFILE"
    printf "2"
}

calendar_status() {
    local wanted="$1" line day status
    [[ -f "$CALENDAR" ]] || return 1
    while IFS= read -r line; do
        line=$(trim "$line")
        [[ -n "$line" ]] || continue
        [[ "$line" == \#* ]] && continue
        read -r day status _ <<< "$line"
        day=$(trim "$day")
        status=$(upper "$(trim "${status:-}")")
        is_date "$day" || continue
        if [[ "$day" == "$wanted" ]]; then
            [[ "$status" == "OPEN" ]] && return 0 || return 1
        fi
    done < "$CALENDAR"
    return 1
}
open_days_after_through() {
    local start="$1" finish="$2" max="$3" line day status count=0
    is_date "$start" && is_date "$finish" || return 1
    [[ "$start" > "$finish" ]] && return 1
    while IFS= read -r line; do
        line=$(trim "$line")
        [[ -n "$line" ]] || continue
        [[ "$line" == \#* ]] && continue
        read -r day status _ <<< "$line"
        day=$(trim "$day")
        status=$(upper "$(trim "${status:-}")")
        is_date "$day" || continue
        if [[ "$status" == "OPEN" && "$day" > "$start" && ( "$day" < "$finish" || "$day" == "$finish" ) ]]; then
            count=$((count + 1))
        fi
    done < "$CALENDAR"
    [[ $count -le $max ]]
}

load_aliases

declare -A bh=() ch=()
read -r booking_header < "$SRC"
read -r credit_header < "$ACT"
parse_header bh "$booking_header"
parse_header ch "$credit_header"

b_booking_id="${bh[booking_id]:-}"
b_member_id="${bh[member_id]:-}"
b_amount="${bh[amount_cents]:-}"
b_status="${bh[status]:-}"
b_plan="${bh[plan]:-}"
b_date="${bh[booking_date]:-}"
c_booking_id="${ch[booking_id]:-}"
c_member_id="${ch[member_id]:-}"
c_amount="${ch[amount_cents]:-}"
c_plan="${ch[plan]:-}"
c_date="${ch[credit_date]:-}"

declare -a src_ids src_members src_amounts src_amount_valid src_statuses src_plans src_dates used
idx=0
while IFS= read -r line; do
    [[ -n "$(trim "$line")" ]] || continue
    idx=$((idx + 1))
    sid=$(cell_by_index "$line" "$b_booking_id")
    smem=$(cell_by_index "$line" "$b_member_id")
    samt_raw=$(cell_by_index "$line" "$b_amount")
    sstatus=$(upper "$(cell_by_index "$line" "$b_status")")
    splan=$(canon_plan "$(cell_by_index "$line" "$b_plan")")
    sdate=$(cell_by_index "$line" "$b_date")
    src_ids[$idx]=$(upper "$sid")
    src_members[$idx]=$(upper "$smem")
    src_statuses[$idx]="$sstatus"
    src_plans[$idx]="$splan"
    src_dates[$idx]="$sdate"
    if is_positive_int "$samt_raw"; then
        src_amounts[$idx]=$(to_int "$samt_raw")
        src_amount_valid[$idx]=Y
    else
        src_amounts[$idx]=""
        src_amount_valid[$idx]=N
    fi
    used[$idx]=N
done < <(tail -n +2 "$SRC")
source_count=$idx

printf "%s\n" "booking_id,member_id,plan,amount_cents,status" > "$REPORT"
matched_count=0
matched_amount=0
unmatched_count=0
unmatched_amount=0
limit=$(max_open_days_back)

while IFS= read -r line; do
    [[ -n "$(trim "$line")" ]] || continue
    aid=$(cell_by_index "$line" "$c_booking_id")
    amem=$(cell_by_index "$line" "$c_member_id")
    aamt_raw=$(cell_by_index "$line" "$c_amount")
    aplan=$(canon_plan "$(cell_by_index "$line" "$c_plan")")
    adate=$(cell_by_index "$line" "$c_date")
    aid_cmp=$(upper "$aid")
    amem_cmp=$(upper "$amem")
    aamt_out=$(trim "$aamt_raw")
    aamt_int=0
    aamt_valid=N
    if is_positive_int "$aamt_raw"; then
        aamt_int=$(to_int "$aamt_raw")
        aamt_out="$aamt_int"
        aamt_valid=Y
    fi
    match_idx=-1
    best_date=""
    for ((i=1; i<=source_count; i++)); do
        [[ "${used[$i]:-N}" != "Y" ]] || continue
        [[ "$aamt_valid" == "Y" ]] || continue
        [[ "${src_amount_valid[$i]:-N}" == "Y" ]] || continue
        [[ "${src_ids[$i]}" == "$aid_cmp" ]] || continue
        [[ "${src_members[$i]}" == "$amem_cmp" ]] || continue
        [[ "${src_amounts[$i]}" == "$aamt_int" ]] || continue
        [[ "${src_statuses[$i]}" == "FINAL" ]] || continue
        [[ "${src_plans[$i]}" == "$aplan" ]] || continue
        is_allowed_plan "$aplan" || continue
        if [[ "$ENABLE_DATES" == "1" ]]; then
            is_date "$adate" || continue
            is_date "${src_dates[$i]}" || continue
            [[ "$adate" < "${src_dates[$i]}" || "$adate" == "${src_dates[$i]}" ]] || continue
            calendar_status "$adate" || continue
            calendar_status "${src_dates[$i]}" || continue
            open_days_after_through "$adate" "${src_dates[$i]}" "$limit" || continue
            if [[ $match_idx -eq -1 || "${src_dates[$i]}" > "$best_date" ]]; then
                match_idx=$i
                best_date="${src_dates[$i]}"
            fi
        else
            match_idx=$i
            break
        fi
    done
    if [[ $match_idx -ne -1 ]]; then
        used[$match_idx]=Y
        matched_count=$((matched_count + 1))
        matched_amount=$((matched_amount + aamt_int))
        printf "%s,%s,%s,%s,MATCHED\n" "$aid" "$amem" "$aplan" "$aamt_out" >> "$REPORT"
    else
        unmatched_count=$((unmatched_count + 1))
        if [[ "$aamt_valid" == "Y" ]]; then
            unmatched_amount=$((unmatched_amount + aamt_int))
        fi
        printf "%s,%s,,%s,UNMATCHED\n" "$aid" "$amem" "$aamt_out" >> "$REPORT"
    fi
done < <(tail -n +2 "$ACT")

printf '{"matched_count":%d,"matched_amount_cents":%d,"unmatched_count":%d,"unmatched_amount_cents":%d}\n' \
    "$matched_count" "$matched_amount" "$unmatched_count" "$unmatched_amount" > "$SUMMARY"
SCRIPT
chmod +x /app/scripts/reconcile.sh
/app/scripts/run_batch.sh
