BEGIN {
    KEY_COMPARE = "PREFIX5"; CONSUME = "OFF"; ALIAS_MODE = "OFF"; WINDOW_MODE = "OFF"
    APP = "/app"; FS = OFS = "|"
    split("record_id volume_id length_hash block_no reel_id", key_fields, " "); nkeys = 5
}
function trim(s) { sub(/^[ \t\r\n]+/, "", s); sub(/[ \t\r\n]+$/, "", s); return s }
function up(s) { return toupper(trim(s)) }
function load_rules(    line, raw, name, i, val, parts) {
    while ((getline line < (APP "/src/tape_rules.pli")) > 0) {
        raw = trim(line); if (toupper(raw) !~ /^DCL / || index(raw, "INIT(") == 0) continue
        name = toupper(raw); sub(/^DCL /, "", name); sub(/ .*/, "", name)
        i = index(raw, "INIT('"); if (i == 0) continue
        val = substr(raw, i + 6); sub(/'.*/, "", val); rules[name] = trim(val)
        if (name ~ /^ALIAS_/ && index(val, "=>") > 0) {
            split(val, parts, "=>"); aliases[up(parts[1])] = up(parts[2]); aliases[up(parts[2])] = up(parts[2])
        }
    }
    close(APP "/src/tape_rules.pli")
}
function load_batch(    line, parts) {
    while ((getline line < (APP "/src/tape_batch.pli")) > 0) {
        if (line !~ /^%SET[ \t]+/) continue
        split(trim(line), parts, /[ \t]+/)
        if (parts[2] == "KEY_COMPARE") KEY_COMPARE = parts[3]
        else if (parts[2] == "CONSUME") CONSUME = parts[3]
        else if (parts[2] == "ALIAS_MODE") ALIAS_MODE = parts[3]
        else if (parts[2] == "WINDOW_MODE") WINDOW_MODE = parts[3]
    }
    close(APP "/src/tape_batch.pli")
}
function canon(f,    k) { k = up(f); return ((ALIAS_MODE == "ON" && (k in aliases)) ? aliases[k] : k) }
function nts(x) { return length(x) == 14 && x ~ /^[0-9]+$/ }
function keys_ok(si, ai,    fi, f) {
    if (KEY_COMPARE == "PREFIX5") {
        return substr(src[si, "record_id"], 1, 5) == substr(act[ai, "record_id"], 1, 5) && src[si, "length_hash"] == act[ai, "length_hash"]
    }
    for (fi = 1; fi <= nkeys; fi++) {
        f = key_fields[fi]
        if (canon(src[si, f]) != canon(act[ai, f])) return 0
    }
    return 1
}
function reason_ok(code,    vi) {
    for (vi = 1; vi <= 3; vi++) if (up(code) == up(rules["REASON_" vi])) return 1
    return 0
}
function win_ok(si, ai,    wi, o, c, st, at) {
    if (WINDOW_MODE != "ON") return 1
    st = src[si, "recv_ts"]; at = act[ai, "audit_ts"]
    if (!nts(st) || !nts(at)) return 0
    for (wi = 1; wi <= wcount; wi++) {
        if (up(win[wi, "volume_id"]) != up(src[si, "volume_id"])) continue
        if (up(win[wi, "state"]) != up(rules["OPEN_MOUNT_STATE"])) continue
        o = win[wi, "open_ts"]; c = win[wi, "close_ts"]
        if (nts(o) && nts(c) && o <= c && o <= st && st <= c && st <= at && at <= c) return 1
    }
    return 0
}
END {
    load_rules(); load_batch(); eligible = up(rules["ELIGIBLE_STATE"])
    scount = acount = wcount = 0
    chdr_done = 0
    while ((getline line < (APP "/data/tape_catalog.psv")) > 0) {
        if (!chdr_done) { split(line, chdr, "|"); chdr_done = 1; continue }
        scount++; split(line, cf, "|"); for (i = 1; i <= length(chdr); i++) src[scount, chdr[i]] = trim(cf[i])
    }
    close(APP "/data/tape_catalog.psv")
    ahdr_done = 0
    while ((getline line < (APP "/data/tape_audits.psv")) > 0) {
        if (!ahdr_done) { split(line, ahdr, "|"); ahdr_done = 1; continue }
        acount++; split(line, af, "|"); for (i = 1; i <= length(ahdr); i++) act[acount, ahdr[i]] = trim(af[i])
    }
    close(APP "/data/tape_audits.psv")
    if (WINDOW_MODE == "ON") {
        whdr_done = 0
        while ((getline line < (APP "/config/mount_windows.psv")) > 0) {
            if (!whdr_done) { split(line, whdr, "|"); whdr_done = 1; continue }
            wcount++; split(line, wf, "|"); for (i = 1; i <= length(whdr); i++) win[wcount, whdr[i]] = trim(wf[i])
        }
        close(APP "/config/mount_windows.psv")
    }
    system("mkdir -p " APP "/out")
    mc = uc = ma = ua = 0
    print "claim_id|record_id|volume_id|reel_id|block_no|length_hash|verdict_code|status" > (APP "/out/tape_report.csv")
    for (ai = 1; ai <= acount; ai++) {
        best = 0
        for (si = 1; si <= scount; si++) {
            if (CONSUME == "ON" && used[si]) continue
            if (src[si, "length_hash"] !~ /^[1-9][0-9]*$/ || act[ai, "length_hash"] !~ /^[1-9][0-9]*$/) continue
            if (!nts(src[si, "recv_ts"])) continue
            if (!keys_ok(si, ai)) continue
            if (up(src[si, "state"]) != eligible) continue
            if (!reason_ok(act[ai, "verdict_code"])) continue
            if (!win_ok(si, ai)) continue
            if (best == 0 || src[si, "recv_ts"] > src[best, "recv_ts"] || (src[si, "recv_ts"] == src[best, "recv_ts"] && si < best)) best = si
        }
        amt = (act[ai, "length_hash"] ~ /^[1-9][0-9]*$/) ? 0 + act[ai, "length_hash"] : 0
        if (best == 0) { uc++; ua += amt; rail = ""; status = "CORRUPT" }
        else {
            if (CONSUME == "ON") used[best] = 1
            mc++; ma += amt; rail = canon(src[best, "block_no"]); status = "VERIFIED"
        }
        print act[ai, "claim_id"], act[ai, "record_id"], act[ai, "volume_id"], act[ai, "reel_id"], rail, act[ai, "length_hash"], act[ai, "verdict_code"], status >> (APP "/out/tape_report.csv")
    }
    print "verified_count=" mc > (APP "/out/tape_summary.txt")
    print "verified_blocks=" ma >> (APP "/out/tape_summary.txt")
    print "corrupt_count=" uc >> (APP "/out/tape_summary.txt")
    print "corrupt_blocks=" ua >> (APP "/out/tape_summary.txt")
}
