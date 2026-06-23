BEGIN {
    KEY_COMPARE = "PREFIX5"; CONSUME = "OFF"; ALIAS_MODE = "OFF"
    WINDOW_MODE = "OFF"; CUTOFF_MODE = "OFF"; LEDGER_MODE = "OFF"
    LIQUIDITY_MODE = "OFF"; SANCTIONS_MODE = "OFF"
    APP = "/app"; FS = OFS = "|"
    split("wire_id account amount_cents rail_code branch_id", key_fields, " ")
    nkeys = 5
}
function trim(s) { sub(/^[ \t\r\n]+/, "", s); sub(/[ \t\r\n]+$/, "", s); return s }
function up(s) { return toupper(trim(s)) }
function nts(x) { return length(trim(x)) == 14 && trim(x) ~ /^[0-9]+$/ }
function canon(f,    k) {
    k = up(f)
    return ((ALIAS_MODE == "ON" && (k in aliases)) ? aliases[k] : k)
}
function load_rules(    line, raw, name, i, val, parts) {
    while ((getline line < (APP "/src/wire_rules.pli")) > 0) {
        raw = trim(line)
        if (toupper(raw) !~ /^DCL / || index(raw, "INIT(") == 0) continue
        name = toupper(raw); sub(/^DCL /, "", name); sub(/ .*/, "", name)
        i = index(raw, "INIT('"); if (i == 0) continue
        val = substr(raw, i + 6); sub(/'.*/, "", val); rules[name] = trim(val)
        if (name ~ /^ALIAS_/ && index(val, "=>") > 0) {
            split(val, parts, "=>")
            aliases[up(parts[1])] = up(parts[2]); aliases[up(parts[2])] = up(parts[2])
        }
    }
    close(APP "/src/wire_rules.pli")
}
function load_batch(    line, parts) {
    while ((getline line < (APP "/src/wire_batch.pli")) > 0) {
        if (line !~ /^%SET[ \t]+/) continue
        split(trim(line), parts, /[ \t]+/)
        flags[parts[2]] = parts[3]
    }
    close(APP "/src/wire_batch.pli")
    if ("KEY_COMPARE" in flags) KEY_COMPARE = flags["KEY_COMPARE"]
    if ("CONSUME" in flags) CONSUME = flags["CONSUME"]
    if ("ALIAS_MODE" in flags) ALIAS_MODE = flags["ALIAS_MODE"]
    if ("WINDOW_MODE" in flags) WINDOW_MODE = flags["WINDOW_MODE"]
    if ("CUTOFF_MODE" in flags) CUTOFF_MODE = flags["CUTOFF_MODE"]
    if ("LEDGER_MODE" in flags) LEDGER_MODE = flags["LEDGER_MODE"]
    if ("LIQUIDITY_MODE" in flags) LIQUIDITY_MODE = flags["LIQUIDITY_MODE"]
    if ("SANCTIONS_MODE" in flags) SANCTIONS_MODE = flags["SANCTIONS_MODE"]
}
function read_table(path, arr, hdr,    line, done, parts, i, c) {
    c = 0
    while ((getline line < path) > 0) {
        if (!done) { split(line, hdr, "|"); done = 1; continue }
        if (trim(line) == "") continue
        c++; split(line, parts, "|")
        for (i = 1; i <= length(hdr); i++) arr[c, hdr[i]] = trim(parts[i])
    }
    close(path)
    return c
}
function reason_ok(code,    vi) {
    for (vi = 1; vi <= 3; vi++) if (up(code) == up(rules["REASON_" vi])) return 1
    return 0
}
function keys_ok(si, ai,    fi, f) {
    if (KEY_COMPARE == "PREFIX5") {
        return substr(src[si, "wire_id"], 1, 5) == substr(act[ai, "wire_id"], 1, 5) &&
            src[si, "amount_cents"] == act[ai, "amount_cents"]
    }
    for (fi = 1; fi <= nkeys; fi++) {
        f = key_fields[fi]
        if (f == "rail_code") {
            if (canon(src[si, f]) != canon(act[ai, f])) return 0
        } else if (up(src[si, f]) != up(act[ai, f])) return 0
    }
    return 1
}
function direction_ok(ai,    amt, reason, neg) {
    if (!("NEGATIVE_REASON_CODES" in rules)) return (0 + act[ai, "amount_cents"] > 0)
    amt = 0 + act[ai, "amount_cents"]; reason = up(act[ai, "reason_code"])
    neg = "," up(rules["NEGATIVE_REASON_CODES"]) ","
    if (index(neg, "," reason ",")) return amt < 0
    return amt > 0
}
function window_ok(si, ai,    wi, o, c, st, at) {
    if (WINDOW_MODE != "ON") return 1
    st = src[si, "posted_ts"]; at = act[ai, "claim_ts"]
    if (!nts(st) || !nts(at)) return 0
    for (wi = 1; wi <= wcount; wi++) {
        if (win[wi, "account"] != src[si, "account"]) continue
        if (up(win[wi, "state"]) != up(rules["OPEN_CLEAR_STATE"])) continue
        o = win[wi, "open_ts"]; c = win[wi, "close_ts"]
        if (nts(o) && nts(c) && o <= st && st <= c && st <= at && at <= c) return 1
    }
    return 0
}
function cutoff_ok(si, ai,    di, day, cutoff) {
    if (CUTOFF_MODE != "ON") return 1
    if (!nts(src[si, "posted_ts"]) || !nts(act[ai, "claim_ts"])) return 0
    day = substr(src[si, "posted_ts"], 1, 8)
    for (di = 1; di <= calcount; di++) {
        if (cal[di, "business_date"] != day) continue
        if (up(cal[di, "state"]) != "OPEN") return 0
        cutoff = cal[di, "cutoff_ts"]
        return nts(cutoff) && src[si, "posted_ts"] <= cutoff && act[ai, "claim_ts"] <= cutoff
    }
    return 0
}
function committed_key(w, a, b, c) { return up(w) "|" up(a) "|" up(b) "|" up(c) }
function load_ledger(    i, key) {
    if (LEDGER_MODE != "ON") return
    lcount = read_table(APP "/state/wire_ledger.psv", led, ledhdr)
    for (i = 1; i <= lcount; i++) {
        key = committed_key(led[i, "wire_id"], led[i, "account"], led[i, "branch_id"], led[i, "claim_id"])
        committed[key] = 1
    }
    checkpoint_status = "OK"
    if ((getline checkpoint < (APP "/state/restart_checkpoint.txt")) <= 0) checkpoint_status = "MISSING"
    close(APP "/state/restart_checkpoint.txt")
    if (checkpoint_status == "OK" && checkpoint !~ /^[0-9]+$/) checkpoint_status = "STALE"
    if (checkpoint_status == "OK" && (0 + checkpoint) > lcount) checkpoint_status = "AHEAD"
}
function load_liquidity(    i, k) {
    if (LIQUIDITY_MODE != "ON") return
    limcount = read_table(APP "/config/nostro_limits.psv", lim, limhdr)
    for (i = 1; i <= limcount; i++) {
        k = up(lim[i, "account"]) "|" canon(lim[i, "rail_code"])
        limit[k] = 0 + lim[i, "limit_cents"]
    }
    sancount = read_table(APP "/config/sanctions_watchlist.psv", sanc, sanchdr)
    for (i = 1; i <= sancount; i++) sanctions[up(sanc[i, "counterparty_id"])] = 1
}
function exception(ai, reason, detail) {
    excount++
    exc[excount] = act[ai, "claim_id"] "|" act[ai, "wire_id"] "|" act[ai, "account"] "|" reason "|" detail
}
function candidate_ok(si, ai) {
    if (!keys_ok(si, ai)) return 0
    if (up(src[si, "state"]) != up(rules["ELIGIBLE_STATE"])) return 0
    if (!reason_ok(act[ai, "reason_code"])) return 0
    if (!direction_ok(ai)) return 0
    if (!window_ok(si, ai)) return 0
    if (!cutoff_ok(si, ai)) return 0
    return 1
}
function choose_candidate(ai,    si, best) {
    best = 0
    for (si = 1; si <= scount; si++) {
        if (CONSUME == "ON" && used[si]) continue
        if (!candidate_ok(si, ai)) continue
        if (best == 0 || src[si, "posted_ts"] > src[best, "posted_ts"] ||
            (src[si, "posted_ts"] == src[best, "posted_ts"] && si < best)) best = si
    }
    return best
}
function abs_amount(ai,    amt) { amt = 0 + act[ai, "amount_cents"]; return (amt < 0 ? -amt : amt) }
function report(ai, status, rail,    amt) {
    print act[ai, "claim_id"], act[ai, "wire_id"], act[ai, "account"], act[ai, "branch_id"],
        rail, act[ai, "amount_cents"], act[ai, "reason_code"], status >> (APP "/out/wire_report.csv")
    amt = abs_amount(ai)
    if (status == "CLEARED") { mc++; ma += amt } else { uc++; ua += amt }
}
END {
    load_rules(); load_batch()
    scount = read_table(APP "/data/clearing.psv", src, chdr)
    acount = read_table(APP "/data/claims.psv", act, ahdr)
    if (WINDOW_MODE == "ON") wcount = read_table(APP "/config/clearing_windows.psv", win, whdr)
    if (CUTOFF_MODE == "ON") calcount = read_table(APP "/config/settlement_calendar.psv", cal, calhdr)
    load_ledger(); load_liquidity()
    system("mkdir -p " APP "/out " APP "/state")
    mc = uc = ma = ua = nledger = excount = 0
    print "claim_id|wire_id|account|branch_id|rail_code|amount_cents|reason_code|status" > (APP "/out/wire_report.csv")
    for (ai = 1; ai <= acount; ai++) {
        key = committed_key(act[ai, "wire_id"], act[ai, "account"], act[ai, "branch_id"], act[ai, "claim_id"])
        best = choose_candidate(ai)
        if (LEDGER_MODE == "ON" && key in committed) {
            report(ai, "RETURNED", ""); exception(ai, "REPLAY_DUPLICATE", "already_committed"); continue
        }
        if (best == 0) { report(ai, "RETURNED", ""); continue }
        rail = canon(src[best, "rail_code"]); liqkey = up(act[ai, "account"]) "|" rail
        if (SANCTIONS_MODE == "ON" && up(act[ai, "counterparty_id"]) in sanctions) {
            report(ai, "RETURNED", ""); exception(ai, "SANCTIONS_HIT", act[ai, "counterparty_id"]); continue
        }
        if (LIQUIDITY_MODE == "ON" && (liqkey in limit) && spent[liqkey] + abs_amount(ai) > limit[liqkey]) {
            report(ai, "RETURNED", ""); exception(ai, "LIQUIDITY_HOLD", liqkey); continue
        }
        if (CONSUME == "ON") used[best] = 1
        spent[liqkey] += abs_amount(ai); committed[key] = 1
        report(ai, "CLEARED", rail)
        if (LEDGER_MODE == "ON") {
            ledger_new[++nledger] = act[ai, "claim_id"] "|" act[ai, "wire_id"] "|" act[ai, "account"] "|" act[ai, "branch_id"] "|" rail "|" abs_amount(ai) "|COMMITTED"
        }
    }
    print "cleared_count=" mc > (APP "/out/wire_summary.txt")
    print "cleared_amount_cents=" ma >> (APP "/out/wire_summary.txt")
    print "returned_count=" uc >> (APP "/out/wire_summary.txt")
    print "returned_amount_cents=" ua >> (APP "/out/wire_summary.txt")
    if (LEDGER_MODE == "ON") {
        print "claim_id|wire_id|account|branch_id|rail_code|amount_cents|status" > (APP "/out/wire_ledger.psv")
        for (i = 1; i <= lcount; i++) print led[i, "claim_id"], led[i, "wire_id"], led[i, "account"], led[i, "branch_id"], led[i, "rail_code"], led[i, "amount_cents"], led[i, "status"] >> (APP "/out/wire_ledger.psv")
        for (i = 1; i <= nledger; i++) print ledger_new[i] >> (APP "/out/wire_ledger.psv")
        print "checkpoint_status=" checkpoint_status > (APP "/out/restart_audit.txt")
        print "committed_rows=" nledger >> (APP "/out/restart_audit.txt")
    }
    if (LIQUIDITY_MODE == "ON" || SANCTIONS_MODE == "ON") {
        print "claim_id|wire_id|account|reason|detail" > (APP "/out/wire_exceptions.csv")
        for (i = 1; i <= excount; i++) print exc[i] >> (APP "/out/wire_exceptions.csv")
        print "account|rail_code|limit_cents|used_cents|remaining_cents" > (APP "/out/liquidity_position.txt")
        for (k in limit) {
            split(k, kp, "|"); print kp[1], kp[2], limit[k], 0 + spent[k], limit[k] - (0 + spent[k]) >> (APP "/out/liquidity_position.txt")
        }
    }
}
