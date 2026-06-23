BEGIN {
    KEY_COMPARE = "PREFIX5"; CONSUME = "OFF"; ALIAS_MODE = "OFF"; WINDOW_MODE = "OFF"
    APP = "/app"; FS = OFS = "|"
    split("policy_id account_no premium_cents risk_code branch_id", key_fields, " "); nkeys = 5
}
function trim(s) { sub(/^[ \t\r\n]+/, "", s); sub(/[ \t\r\n]+$/, "", s); return s }
function up(s) { return toupper(trim(s)) }
function isint(s, t) { t = trim(s); return t ~ /^[+-]?[0-9]+$/ }
function load_rules(    line, raw, name, i, val, parts) {
    while ((getline line < (APP "/src/premium_rules.pli")) > 0) {
        raw = trim(line); if (toupper(raw) !~ /^DCL / || index(raw, "INIT(") == 0) continue
        name = toupper(raw); sub(/^DCL /, "", name); sub(/ .*/, "", name)
        i = index(raw, "INIT('"); if (i == 0) continue
        val = substr(raw, i + 6); sub(/'.*/, "", val); rules[name] = trim(val)
        if (name ~ /^ALIAS_/ && index(val, "=>") > 0) {
            split(val, parts, "=>"); aliases[up(parts[1])] = up(parts[2]); aliases[up(parts[2])] = up(parts[2])
        }
    }
    close(APP "/src/premium_rules.pli")
}
function load_batch(    line, parts) {
    while ((getline line < (APP "/src/premium_batch.pli")) > 0) {
        if (line !~ /^%SET[ \t]+/) continue
        split(trim(line), parts, /[ \t]+/)
        if (parts[2] == "KEY_COMPARE") KEY_COMPARE = parts[3]
        else if (parts[2] == "CONSUME") CONSUME = parts[3]
        else if (parts[2] == "ALIAS_MODE") ALIAS_MODE = parts[3]
        else if (parts[2] == "WINDOW_MODE") WINDOW_MODE = parts[3]
    }
    close(APP "/src/premium_batch.pli")
}
function risk_display(f,    k) { k = up(f); return ((ALIAS_MODE == "ON" && (k in aliases)) ? aliases[k] : trim(f)) }
function risk_key(f) { return up(risk_display(f)) }
function nts(x) { return length(x) == 14 && x ~ /^[0-9]+$/ }
function keys_ok(si, ai,    fi, f) {
    if (KEY_COMPARE == "PREFIX5") {
        return substr(src[si, "policy_id"], 1, 5) == substr(act[ai, "policy_id"], 1, 5) && src[si, "premium_cents"] == act[ai, "premium_cents"]
    }
    for (fi = 1; fi <= 2; fi++) {
        f = key_fields[fi]
        if (up(src[si, f]) != up(act[ai, f])) return 0
    }
    return 1
}
function reason_ok(code,    vi) {
    for (vi = 1; vi <= 3; vi++) if (up(code) == up(rules["REASON_" vi])) return 1
    return 0
}
function win_ok(si, ai,    wi, o, c, st, at) {
    if (WINDOW_MODE != "ON") return 1
    st = src[si, "ingest_ts"]; at = act[ai, "adj_ts"]
    if (!nts(st) || !nts(at)) return 0
    for (wi = 1; wi <= wcount; wi++) {
        if (win[wi, "account_no"] != src[si, "account_no"]) continue
        if (up(win[wi, "state"]) != up(rules["OPEN_FISCAL_STATE"])) continue
        o = win[wi, "open_ts"]; c = win[wi, "close_ts"]
        if (nts(o) && nts(c) && o <= at && at <= c) return 1
    }
    return 0
}
END {
    load_rules(); load_batch(); eligible = up(rules["ELIGIBLE_STATE"])
    scount = acount = wcount = 0
    chdr_done = 0
    while ((getline line < (APP "/data/policies.psv")) > 0) {
        if (!chdr_done) { split(line, chdr, "|"); chdr_done = 1; continue }
        scount++; split(line, cf, "|"); for (i = 1; i <= length(chdr); i++) src[scount, chdr[i]] = trim(cf[i])
    }
    close(APP "/data/policies.psv")
    ahdr_done = 0
    while ((getline line < (APP "/data/adjustments.psv")) > 0) {
        if (!ahdr_done) { split(line, ahdr, "|"); ahdr_done = 1; continue }
        acount++; split(line, af, "|"); for (i = 1; i <= length(ahdr); i++) act[acount, ahdr[i]] = trim(af[i])
    }
    close(APP "/data/adjustments.psv")
    if (WINDOW_MODE == "ON") {
        whdr_done = 0
        while ((getline line < (APP "/config/fiscal_windows.psv")) > 0) {
            if (!whdr_done) { split(line, whdr, "|"); whdr_done = 1; continue }
            wcount++; split(line, wf, "|"); for (i = 1; i <= length(whdr); i++) win[wcount, whdr[i]] = trim(wf[i])
        }
        close(APP "/config/fiscal_windows.psv")
    }
    system("mkdir -p " APP "/out")
    mc = uc = ma = ua = 0
    print "claim_id|policy_id|account_no|branch_id|risk_code|premium_cents|opcode|status" > (APP "/out/premium_report.csv")
    for (ai = 1; ai <= acount; ai++) {
        best = 0
        for (si = 1; si <= scount; si++) {
            if (CONSUME == "ON" && used[si]) continue
            if (!keys_ok(si, ai)) continue
            if (up(src[si, "state"]) != eligible) continue
            if (!reason_ok(act[ai, "opcode"])) continue
            if (!win_ok(si, ai)) continue
            if (best == 0) best = si
        }
        amt = 0 + act[ai, "premium_cents"]
        if (best == 0) { uc++; ua += amt; rail = ""; status = "INVALID" }
        else {
            if (CONSUME == "ON") used[best] = 1
            mc++; ma += amt; rail = risk_display(src[best, "risk_code"]); status = "VALID"
        }
        print act[ai, "claim_id"], act[ai, "policy_id"], act[ai, "account_no"], act[ai, "branch_id"], rail, act[ai, "premium_cents"], act[ai, "opcode"], status >> (APP "/out/premium_report.csv")
    }
    print "valid_count=" mc > (APP "/out/premium_summary.txt")
    print "valid_amount_cents=" ma >> (APP "/out/premium_summary.txt")
    print "invalid_count=" uc >> (APP "/out/premium_summary.txt")
    print "invalid_amount_cents=" ua >> (APP "/out/premium_summary.txt")
}
