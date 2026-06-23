#!/usr/bin/env bash
set -euo pipefail

cat > /app/scripts/reconcile.sh <<'SCRIPT'
#!/usr/bin/env bash
set -euo pipefail

SRC="/app/data/samples.csv"
ACT="/app/data/credits.csv"
REPORT="/app/out/credit_report.csv"
SUMMARY="/app/out/credit_summary.json"
CALENDAR="/app/config/cutoff_calendar.txt"
CAPS="/app/config/payer_clearance_caps.csv"
LOTS="/app/config/specimen_release_lots.csv"

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
        CC) printf "%s\n" "CARD" ;;
        INS) printf "%s\n" "INSURANCE" ;;
        CA) printf "%s\n" "CASH" ;;
        *) printf "%s\n" "$value" ;;
    esac
}

is_allowed() {
    case "$1" in
        CASH|CARD|INSURANCE) return 0 ;;
        *) return 1 ;;
    esac
}

is_iso_date() {
    [[ "$1" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]
}

is_open() {
    local wanted status day
    wanted=$(trim "$1")
    is_iso_date "$wanted" || return 1
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
    is_iso_date "$start" || return 1
    is_iso_date "$finish" || return 1
    [[ "$start" > "$finish" ]] && return 1
    count=0
    while read -r day status _; do
        day=$(trim "$day")
        status=$(upper "$(trim "${status:-}")")
        if is_iso_date "$day" && [[ "$status" == "OPEN" && "$day" > "$start" && ( "$day" < "$finish" || "$day" == "$finish" ) ]]; then
            count=$((count + 1))
        fi
    done < "$CALENDAR"
    [[ $count -le 2 ]]
}

cap_within_limit() {
    local payer="$1" amt="$2" cap current
    cap="${cap_limit[$payer]:-}"
    [[ -z "$cap" ]] && return 0
    current="${cleared_payer[$payer]:-0}"
    [[ $((current + amt)) -le $cap ]]
}

lot_candidate_ok() {
    local idx="$1" payer="$2" amt="$3" credit_date="$4"
    local slot clot key release current cap
    [[ $lot_mode -eq 0 ]] && return 0
    [[ $src_has_lot -eq 1 && $act_has_lot -eq 1 ]] || return 1

    slot=$(upper "$(trim "${src_lots[$idx]:-}")")
    clot=$(upper "$(trim "$alot")")
    [[ -n "$slot" && "$slot" == "$clot" ]] || return 1
    [[ "${lot_present[$slot]:-N}" == "Y" ]] || return 1
    [[ "${lot_enabled[$slot]:-N}" == "Y" ]] || return 1
    [[ "${lot_payer[$slot]:-}" == "$payer" ]] || return 1

    release="${lot_release[$slot]:-}"
    is_open "$release" || return 1
    if [[ $dated_mode -eq 1 ]]; then
        is_iso_date "${src_dates[$idx]:-}" || return 1
        is_iso_date "$credit_date" || return 1
        [[ "$release" < "${src_dates[$idx]}" ]] && return 1
        [[ "$release" < "$credit_date" ]] && return 1
    fi

    key="${slot}|${payer}"
    cap="${lot_capacity[$key]:-}"
    [[ -n "$cap" ]] || return 1
    current="${cleared_lot[$key]:-0}"
    [[ $((current + amt)) -le $cap ]]
}

declare -A cap_limit cleared_payer
if [[ -f "$CAPS" ]]; then
    while IFS=',' read -r cpayer ccap _; do
        cpayer=$(canon_dim "${cpayer:-}")
        ccap=$(trim "${ccap:-}")
        [[ "$cpayer" == "PAYER" ]] && continue
        if [[ -n "$cpayer" && "$ccap" =~ ^[0-9]+$ ]]; then
            cap_limit[$cpayer]=$((10#$ccap))
        fi
    done < <(tail -n +2 "$CAPS")
fi

declare -A lot_present lot_enabled lot_payer lot_release lot_capacity cleared_lot
if [[ -f "$LOTS" ]]; then
    while IFS=',' read -r lot_id lpayer ldate lcap lenabled _; do
        lot_id=$(upper "$(trim "${lot_id:-}")")
        lpayer=$(canon_dim "${lpayer:-}")
        ldate=$(trim "${ldate:-}")
        lcap=$(trim "${lcap:-}")
        lenabled=$(upper "$(trim "${lenabled:-}")")
        [[ "$lot_id" == "LOT_ID" ]] && continue
        [[ -z "$lot_id" || -z "$lpayer" || ! "$lcap" =~ ^[0-9]+$ ]] && continue
        lot_present[$lot_id]=Y
        case "$lenabled" in
            Y|YES|1) lot_enabled[$lot_id]=Y ;;
            *) lot_enabled[$lot_id]=N ;;
        esac
        lot_payer[$lot_id]="$lpayer"
        lot_release[$lot_id]="$ldate"
        lot_capacity["$lot_id|$lpayer"]=$((10#$lcap))
    done < <(tail -n +2 "$LOTS")
fi

IFS= read -r src_header < "$SRC"
IFS= read -r act_header < "$ACT"
src_has_date=0
act_has_date=0
src_has_lot=0
act_has_lot=0
[[ ",$src_header," == *",result_date,"* ]] && src_has_date=1
[[ ",$act_header," == *",credit_date,"* ]] && act_has_date=1
[[ ",$src_header," == *",lot_id,"* ]] && src_has_lot=1
[[ ",$act_header," == *",lot_id,"* ]] && act_has_lot=1
dated_mode=0
lot_mode=0
if [[ $src_has_date -eq 1 || $act_has_date -eq 1 ]]; then
    dated_mode=1
fi
if [[ $src_has_lot -eq 1 || $act_has_lot -eq 1 ]]; then
    lot_mode=1
fi

declare -a src_ids src_customers src_amounts src_statuses src_dims src_dates src_lots used
idx=0
while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    idx=$((idx + 1))
    IFS=',' read -r sid scust samt sstatus sdim f6 f7 _ <<< "$line"
    src_ids[$idx]=$(trim "${sid:-}")
    src_customers[$idx]=$(trim "${scust:-}")
    src_amounts[$idx]=$(trim "${samt:-}")
    src_statuses[$idx]=$(upper "$(trim "${sstatus:-}")")
    src_dims[$idx]=$(canon_dim "${sdim:-}")
    if [[ $src_has_date -eq 1 && $src_has_lot -eq 1 ]]; then
        src_dates[$idx]=$(trim "${f6:-}")
        src_lots[$idx]=$(upper "$(trim "${f7:-}")")
    elif [[ $src_has_date -eq 1 ]]; then
        src_dates[$idx]=$(trim "${f6:-}")
        src_lots[$idx]=""
    elif [[ $src_has_lot -eq 1 ]]; then
        src_dates[$idx]=""
        src_lots[$idx]=$(upper "$(trim "${f6:-}")")
    else
        src_dates[$idx]=""
        src_lots[$idx]=""
    fi
    used[$idx]=N
done < <(tail -n +2 "$SRC")
source_count=$idx

printf "%s\n" "sample_id,patient_id,payer,amount_cents,status" > "$REPORT"
matched_count=0
matched_amount=0
unmatched_count=0
unmatched_amount=0

while IFS= read -r line; do
    [[ -n "$line" ]] || continue
    IFS=',' read -r aid acust aamt adim f5 f6 _ <<< "$line"
    aid=$(trim "${aid:-}")
    acust=$(trim "${acust:-}")
    aamt=$(trim "${aamt:-}")
    adim=$(canon_dim "${adim:-}")
    adate=""
    alot=""
    if [[ $act_has_date -eq 1 && $act_has_lot -eq 1 ]]; then
        adate=$(trim "${f5:-}")
        alot=$(upper "$(trim "${f6:-}")")
    elif [[ $act_has_date -eq 1 ]]; then
        adate=$(trim "${f5:-}")
    elif [[ $act_has_lot -eq 1 ]]; then
        alot=$(upper "$(trim "${f5:-}")")
    fi
    match_idx=-1
    best_date=""
    amount_num=$((10#$aamt))

    for ((i=1; i<=source_count; i++)); do
        if [[ "${used[$i]:-N}" == "Y" ]] ||
           [[ "${src_ids[$i]}" != "$aid" ]] ||
           [[ "${src_customers[$i]}" != "$acust" ]] ||
           [[ "${src_amounts[$i]}" != "$aamt" ]] ||
           [[ "${src_statuses[$i]}" != "FINAL" ]] ||
           [[ "${src_dims[$i]}" != "$adim" ]] ||
           ! is_allowed "$adim"; then
            continue
        fi

        if [[ $dated_mode -eq 1 ]]; then
            if [[ $src_has_date -ne 1 || $act_has_date -ne 1 ]] ||
               ! is_open "$adate" ||
               ! is_open "${src_dates[$i]}" ||
               [[ "$adate" > "${src_dates[$i]}" ]] ||
               ! open_days_after_through "$adate" "${src_dates[$i]}"; then
                continue
            fi
        fi

        lot_candidate_ok "$i" "$adim" "$amount_num" "$adate" || continue

        if [[ $dated_mode -eq 1 ]]; then
            if [[ $match_idx -eq -1 || "${src_dates[$i]}" > "$best_date" ]]; then
                match_idx=$i
                best_date="${src_dates[$i]}"
            fi
        else
            match_idx=$i
            break
        fi
    done

    if [[ $match_idx -ne -1 ]] && ! cap_within_limit "$adim" "$amount_num"; then
        match_idx=-1
    fi

    if [[ $match_idx -ne -1 ]]; then
        used[$match_idx]=Y
        cleared_payer[$adim]=$(( ${cleared_payer[$adim]:-0} + amount_num ))
        if [[ $lot_mode -eq 1 ]]; then
            lot_key="${src_lots[$match_idx]}|${adim}"
            cleared_lot[$lot_key]=$(( ${cleared_lot[$lot_key]:-0} + amount_num ))
        fi
        matched_count=$((matched_count + 1))
        matched_amount=$((matched_amount + amount_num))
        printf "%s,%s,%s,%s,MATCHED\n" "$aid" "$acust" "$adim" "$aamt" >> "$REPORT"
    else
        unmatched_count=$((unmatched_count + 1))
        unmatched_amount=$((unmatched_amount + amount_num))
        printf "%s,%s,,%s,UNMATCHED\n" "$aid" "$acust" "$aamt" >> "$REPORT"
    fi
done < <(tail -n +2 "$ACT")

printf '{"matched_count":%d,"matched_amount_cents":%d,"unmatched_count":%d,"unmatched_amount_cents":%d}\n' \
    "$matched_count" "$matched_amount" "$unmatched_count" "$unmatched_amount" > "$SUMMARY"
SCRIPT

chmod +x /app/scripts/reconcile.sh
/app/scripts/run_batch.sh
