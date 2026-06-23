#!/usr/bin/env bash
set -euo pipefail

cat > /app/scripts/reconcile.sh <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail
SRC="/app/data/fines.csv"
ACT="/app/data/waivers.csv"
REPORT="/app/out/waiver_report.csv"
SUMMARY="/app/out/waiver_summary.json"
CALENDAR="/app/config/cutoff_calendar.txt"
mkdir -p /app/out
trim() {
    local s="$1"
    s="${s#"${s%%[![:space:]]*}"}"
    s="${s%"${s##*[![:space:]]}"}"
    printf "%s" "$s"
}
upper() { printf "%s" "$1" | tr "[:lower:]" "[:upper:]"; }
canon_dim() {
    local value
    value=$(upper "$(trim "$1")")
    case "$value" in
        FR) printf "%s\n" "FRONT" ;;
        WEB) printf "%s\n" "ONLINE" ;;
        APP) printf "%s\n" "MOBILE" ;;
        *) printf "%s\n" "$value" ;;
    esac
}
is_allowed() {
    case "$1" in
        FRONT|ONLINE|MOBILE) return 0 ;;
        *) return 1 ;;
    esac
}

is_open() {
    local wanted status day
    wanted=$(trim "$1")
    [[ -n "$wanted" ]] || return 1
    [[ -f "$CALENDAR" ]] || return 1
    while read -r day status _; do
        day=$(trim "$day")
        status=$(upper "$(trim "${status:-}")")
        if [[ "$day" == "$wanted" && "$status" == "OPEN" ]]; then
            return 0
        fi
    done < "$CALENDAR"
    return 1
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
    [[ $count -le 2 ]]
}

declare -a src_ids src_customers src_amounts src_statuses src_dims src_dates used
idx=0
while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    idx=$((idx + 1))
    IFS=',' read -r sid scust samt sstatus sdim sdate _ <<< "$line"
    src_ids[$idx]=$(trim "${sid:-}")
    src_customers[$idx]=$(trim "${scust:-}")
    src_amounts[$idx]=$(trim "${samt:-}")
    src_statuses[$idx]=$(upper "$(trim "${sstatus:-}")")
    src_dims[$idx]=$(canon_dim "${sdim:-}")
    src_dates[$idx]=$(trim "${sdate:-}")
    used[$idx]=N
done < <(tail -n +2 "$SRC")
source_count=$idx
printf "%s
" "fine_id,patron_id,desk,amount_cents,status" > "$REPORT"
matched_count=0
matched_amount=0
unmatched_count=0
unmatched_amount=0
while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    IFS=',' read -r aid acust aamt adim adate _ <<< "$line"
    aid=$(trim "${aid:-}")
    acust=$(trim "${acust:-}")
    aamt=$(trim "${aamt:-}")
    adim=$(canon_dim "${adim:-}")
    adate=$(trim "${adate:-}")
    match_idx=-1
    best_date=""
    for ((i=1; i<=source_count; i++)); do
        if [[ "${used[$i]:-N}" != "Y" ]] && [[ "${src_ids[$i]}" == "$aid" ]]             && [[ "${src_customers[$i]}" == "$acust" ]]             && [[ "${src_amounts[$i]}" == "$aamt" ]]             && [[ "${src_statuses[$i]}" == "ASSESSED" ]]             && [[ "${src_dims[$i]}" == "$adim" ]]             && is_allowed "$adim"             && [[ -n "${src_dates[$i]}" ]] && [[ -n "$adate" ]] && is_open "$adate" && is_open "${src_dates[$i]}" && open_days_after_through "$adate" "${src_dates[$i]}" && ( [[ "$adate" < "${src_dates[$i]}" ]] || [[ "$adate" == "${src_dates[$i]}" ]] ); then
            if [[ $match_idx -eq -1 || "${src_dates[$i]}" > "$best_date" || ( "${src_dates[$i]}" == "$best_date" && i < match_idx ) ]]; then
                match_idx=$i
                best_date="${src_dates[$i]}"
            fi
            true
        fi
    done
    amount_num=$((10#$aamt))
    if [[ $match_idx -ne -1 ]]; then
        used[$match_idx]=Y
        matched_count=$((matched_count + 1))
        matched_amount=$((matched_amount + amount_num))
        printf "%s,%s,%s,%s,MATCHED
" "$aid" "$acust" "$adim" "$aamt" >> "$REPORT"
    else
        unmatched_count=$((unmatched_count + 1))
        unmatched_amount=$((unmatched_amount + amount_num))
        printf "%s,%s,,%s,UNMATCHED
" "$aid" "$acust" "$aamt" >> "$REPORT"
    fi
done < <(tail -n +2 "$ACT")
printf '{"matched_count":%d,"matched_amount_cents":%d,"unmatched_count":%d,"unmatched_amount_cents":%d}
' "$matched_count" "$matched_amount" "$unmatched_count" "$unmatched_amount" > "$SUMMARY"
SCRIPT
chmod +x /app/scripts/reconcile.sh
/app/scripts/run_batch.sh
