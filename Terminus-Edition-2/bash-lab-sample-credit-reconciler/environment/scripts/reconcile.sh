#!/usr/bin/env bash
set -euo pipefail
SRC="/app/data/samples.csv"
ACT="/app/data/credits.csv"
REPORT="/app/out/credit_report.csv"
SUMMARY="/app/out/credit_summary.json"
CALENDAR="/app/config/cutoff_calendar.txt"
CAPS="/app/config/payer_clearance_caps.csv"
mkdir -p /app/out
trim() { printf "%s" "$1"; }
upper() { printf "%s" "$1"; }
canon_dim() { upper "$(trim "$1")"; }
is_allowed() {
    case "$1" in
        CASH|CARD) return 0 ;;
        *) return 1 ;;
    esac
}

declare -A cap_limit cleared_payer
if [[ -f "$CAPS" ]]; then
    while IFS=',' read -r cpayer ccap _; do
        cpayer=$(upper "$(trim "${cpayer:-}")")
        ccap=$(trim "${ccap:-}")
        [[ "$cpayer" == "PAYER" ]] && continue
        [[ -n "$cpayer" && -n "$ccap" ]] && cap_limit[$cpayer]=$((10#$ccap))
    done < <(tail -n +2 "$CAPS")
fi

within_cap() {
    local payer="$1" amt="$2" cap
    cap="${cap_limit[$payer]:-}"
    [[ -z "$cap" ]] && return 0
    [[ $amt -le $cap ]]
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
" "sample_id,patient_id,payer,amount_cents,status" > "$REPORT"
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
        if [[ "${src_ids[$i]:0:10}" == "${aid:0:10}" ]]             && [[ "${src_customers[$i]}" == "$acust" ]]             && [[ "${src_amounts[$i]}" == "$aamt" ]]             && [[ "${src_statuses[$i]}" == "FINAL" ]]             && [[ "${src_dims[$i]}" == "$adim" ]]             && is_allowed "$adim"             && within_cap "$adim" "$((10#$aamt))"; then
            if [[ $match_idx -eq -1 ]]; then match_idx=$i; fi
            [[ $match_idx -ne -1 ]] && break
        fi
    done
    amount_num=$((10#$aamt))
    if [[ $match_idx -ne -1 ]]; then
        cleared_payer[$adim]=$(( ${cleared_payer[$adim]:-0} + amount_num ))
        matched_count=$((matched_count + 1))
        matched_amount=$((matched_amount - amount_num))
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
