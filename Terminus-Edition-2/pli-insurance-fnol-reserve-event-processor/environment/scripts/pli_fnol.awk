BEGIN {
    KEY_COMPARE = "PREFIX5"; CONSUME = "OFF"; ALIAS_MODE = "OFF"; WINDOW_MODE = "OFF"
    LEDGER_MODE = "OFF"; LIMIT_MODE = "OFF"; SUBROGATION_MODE = "OFF"
    APP = "/app"; FS = OFS = "|"
    split("claim_id policy_id loss_unit state_code reserve_cents coverage_type", key_fields, " ")
    nkeys = 6
}
function trim(s) { sub(/^[ \t\r\n]+/, "", s); sub(/[ \t\r\n]+$/, "", s); return s }
function up(s) { return toupper(trim(s)) }
function nts(x) { return length(trim(x)) == 14 && trim(x) ~ /^[0-9]+$/ }
function canon(f,    k) {
    k = up(f)
    return ((ALIAS_MODE == "ON" && (k in aliases)) ? aliases[k] : k)
}
function load_rules(    line, raw, name, i, val, parts) {
    while ((getline line < (APP "/src/fnol_rules.pli")) > 0) {
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
    close(APP "/src/fnol_rules.pli")
}
function load_batch(    line, parts) {
    while ((getline line < (APP "/src/fnol_batch.pli")) > 0) {
        if (line !~ /^%SET[ \t]+/) continue
        split(trim(line), parts, /[ \t]+/)
        flags[parts[2]] = parts[3]
    }
    close(APP "/src/fnol_batch.pli")
    if ("KEY_COMPARE" in flags) KEY_COMPARE = flags["KEY_COMPARE"]
    if ("CONSUME" in flags) CONSUME = flags["CONSUME"]
    if ("ALIAS_MODE" in flags) ALIAS_MODE = flags["ALIAS_MODE"]
    if ("WINDOW_MODE" in flags) WINDOW_MODE = flags["WINDOW_MODE"]
    if ("LEDGER_MODE" in flags) LEDGER_MODE = flags["LEDGER_MODE"]
    if ("LIMIT_MODE" in flags) LIMIT_MODE = flags["LIMIT_MODE"]
    if ("SUBROGATION_MODE" in flags) SUBROGATION_MODE = flags["SUBROGATION_MODE"]
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
    for (vi = 1; vi <= 3; vi++) {
        rname = "REASON_" substr("ABC", vi, 1)
        if (up(code) == up(rules[rname])) return 1
    }
    return 0
}
function keys_ok(si, ai,    fi, f) {
    if (KEY_COMPARE == "PREFIX5") {
        return substr(src[si, "claim_id"], 1, 5) == substr(act[ai, "claim_id"], 1, 5) &&
            src[si, "reserve_cents"] == act[ai, "reserve_cents"]
    }
    for (fi = 1; fi <= nkeys; fi++) {
        f = key_fields[fi]
        if (f == "coverage_type") {
            if (canon(src[si, f]) != canon(act[ai, f])) return 0
        } else if (up(src[si, f]) != up(act[ai, f])) return 0
    }
    return 1
}
function direction_ok(ai,    amt, reason, neg) {
    if (!("NEGATIVE_REASON_CODES" in rules)) return (0 + act[ai, "reserve_cents"] > 0)
    amt = 0 + act[ai, "reserve_cents"]; reason = up(act[ai, "reason"])
    neg = "," up(rules["NEGATIVE_REASON_CODES"]) ","
    if (index(neg, "," reason ",")) return amt < 0
    return amt > 0
}
function window_ok(si, ai,    wi, o, c, st, at) {
    if (WINDOW_MODE != "ON") return 1
    st = src[si, "fnol_ts"]; at = act[ai, "adjust_ts"]
    if (!nts(st) || !nts(at)) return 0
    for (wi = 1; wi <= wcount; wi++) {
        if (win[wi, "loss_unit"] != src[si, "loss_unit"]) continue
        if (up(win[wi, "state"]) != up(rules["OPEN_WINDOW_STATUS"])) continue
        o = win[wi, "open_ts"]; c = win[wi, "close_ts"]
        if (nts(o) && nts(c) && o <= st && st <= c && st <= at && at <= c) return 1
    }
    return 0
}
function committed_key(a, c, p, l) { return up(a) "|" up(c) "|" up(p) "|" up(l) }
function load_ledger(    i, key) {
    if (LEDGER_MODE != "ON") return
    lcount = read_table(APP "/state/reserve_ledger.psv", led, ledhdr)
    for (i = 1; i <= lcount; i++) {
        key = committed_key(led[i, "action_id"], led[i, "claim_id"], led[i, "policy_id"], led[i, "loss_unit"])
        committed[key] = 1
    }
    checkpoint_status = "OK"
    if ((getline checkpoint < (APP "/state/restart_checkpoint.txt")) <= 0) checkpoint_status = "MISSING"
    close(APP "/state/restart_checkpoint.txt")
    if (checkpoint_status == "OK" && checkpoint !~ /^[0-9]+$/) checkpoint_status = "STALE"
    if (checkpoint_status == "OK" && (0 + checkpoint) > lcount) checkpoint_status = "AHEAD"
}
function load_limits(    i) {
    if (LIMIT_MODE != "ON") return
    limcount = read_table(APP "/config/policy_limits.psv", lim, limhdr)
    for (i = 1; i <= limcount; i++) limit[up(lim[i, "policy_id"])] = 0 + lim[i, "max_reserve_cents"]
    if (SUBROGATION_MODE == "ON") {
        hcount = read_table(APP "/config/subrogation_holds.psv", hold, holdhdr)
        for (i = 1; i <= hcount; i++) subrogation[up(hold[i, "action_id"])] = hold[i, "hold_reason"]
    }
}
function exception(ai, reason, detail) {
    excount++
    exc[excount] = act[ai, "action_id"] "|" act[ai, "claim_id"] "|" act[ai, "policy_id"] "|" reason "|" detail
}
function abs_amount(ai,    amt) { amt = 0 + act[ai, "reserve_cents"]; return (amt < 0 ? -amt : amt) }
function candidate_ok(si, ai) {
    if (!keys_ok(si, ai)) return 0
    if (up(src[si, "status"]) != up(rules["ELIGIBLE_STATUS"])) return 0
    if (!reason_ok(act[ai, "reason"])) return 0
    if (!direction_ok(ai)) return 0
    if (!window_ok(si, ai)) return 0
    return 1
}
function choose_candidate(ai,    si, best) {
    best = 0
    for (si = 1; si <= scount; si++) {
        if (CONSUME == "ON" && used[si]) continue
        if (!candidate_ok(si, ai)) continue
        if (best == 0 || src[si, "fnol_ts"] > src[best, "fnol_ts"] ||
            (src[si, "fnol_ts"] == src[best, "fnol_ts"] && si < best)) best = si
    }
    return best
}
function report(ai, status, kind) {
    print act[ai, "action_id"], act[ai, "claim_id"], act[ai, "policy_id"], act[ai, "loss_unit"],
        kind, act[ai, "reserve_cents"], act[ai, "reason"], status >> (APP "/out/reserve_adjustment_report.csv")
    amt = abs_amount(ai)
    if (status == "MATCHED") { mc++; ma += amt } else { uc++; ua += amt }
}
END {
    load_rules(); load_batch()
    scount = read_table(APP "/data/claims.psv", src, chdr)
    acount = read_table(APP "/data/adjustments.psv", act, ahdr)
    if (WINDOW_MODE == "ON") wcount = read_table(APP "/config/windows.psv", win, whdr)
    load_ledger(); load_limits()
    system("mkdir -p " APP "/out " APP "/state")
    mc = uc = ma = ua = nledger = excount = 0
    print "action_id|claim_id|policy_id|loss_unit|coverage_type|reserve_cents|reason|status" > (APP "/out/reserve_adjustment_report.csv")
    for (ai = 1; ai <= acount; ai++) {
        key = committed_key(act[ai, "action_id"], act[ai, "claim_id"], act[ai, "policy_id"], act[ai, "loss_unit"])
        if (SUBROGATION_MODE == "ON" && up(act[ai, "action_id"]) in subrogation) {
            report(ai, "UNMATCHED", ""); exception(ai, "SUBROGATION_HOLD", subrogation[up(act[ai, "action_id"])]); continue
        }
        if (LEDGER_MODE == "ON" && key in committed) {
            report(ai, "UNMATCHED", ""); exception(ai, "REPLAY_DUPLICATE", "already_committed"); continue
        }
        pol = up(act[ai, "policy_id"])
        if (LIMIT_MODE == "ON" && (pol in limit) && spent[pol] + abs_amount(ai) > limit[pol]) {
            report(ai, "UNMATCHED", ""); exception(ai, "POLICY_LIMIT", pol); continue
        }
        best = choose_candidate(ai)
        if (best == 0) { report(ai, "UNMATCHED", ""); continue }
        kind = canon(src[best, "coverage_type"])
        if (CONSUME == "ON") used[best] = 1
        if (LIMIT_MODE == "ON" && (pol in limit)) spent[pol] += abs_amount(ai)
        committed[key] = 1
        report(ai, "MATCHED", kind)
        if (LEDGER_MODE == "ON") {
            ledger_new[++nledger] = act[ai, "action_id"] "|" act[ai, "claim_id"] "|" act[ai, "policy_id"] "|" act[ai, "loss_unit"] "|" kind "|" abs_amount(ai) "|COMMITTED"
        }
    }
    print "matched_count=" mc > (APP "/out/reserve_adjustment_summary.txt")
    print "matched_amount_cents=" ma >> (APP "/out/reserve_adjustment_summary.txt")
    print "unmatched_count=" uc >> (APP "/out/reserve_adjustment_summary.txt")
    print "unmatched_amount_cents=" ua >> (APP "/out/reserve_adjustment_summary.txt")
    if (LEDGER_MODE == "ON") {
        print "action_id|claim_id|policy_id|loss_unit|coverage_type|reserve_cents|status" > (APP "/out/reserve_ledger.psv")
        for (i = 1; i <= lcount; i++) {
            print led[i, "action_id"], led[i, "claim_id"], led[i, "policy_id"], led[i, "loss_unit"],
                led[i, "coverage_type"], led[i, "reserve_cents"], led[i, "status"] >> (APP "/out/reserve_ledger.psv")
        }
        for (i = 1; i <= nledger; i++) print ledger_new[i] >> (APP "/out/reserve_ledger.psv")
        print "checkpoint_status=" checkpoint_status > (APP "/out/restart_audit.txt")
        print "committed_rows=" nledger >> (APP "/out/restart_audit.txt")
    }
    if (LIMIT_MODE == "ON" || SUBROGATION_MODE == "ON") {
        print "action_id|claim_id|policy_id|reason|detail" > (APP "/out/reserve_exceptions.csv")
        for (i = 1; i <= excount; i++) print exc[i] >> (APP "/out/reserve_exceptions.csv")
        print "policy_id|limit_cents|used_cents|remaining_cents" > (APP "/out/reserve_position.txt")
        for (pol in limit) {
            print pol, limit[pol], 0 + spent[pol], limit[pol] - (0 + spent[pol]) >> (APP "/out/reserve_position.txt")
        }
    }
}
