BEGIN {
    KEY_COMPARE = "PREFIX5"
    CONSUME = "OFF"
    ALIAS_MODE = "OFF"
    WINDOW_MODE = "OFF"
    APP = "/app"
    FS = OFS = "|"
    split("frame_id craft_id channel payload_hash service_class", key_fields, " ")
    nkeys = 5
}
function trim(s) { sub(/^[ \t\r\n]+/, "", s); sub(/[ \t\r\n]+$/, "", s); return s }
function up(s) { return toupper(trim(s)) }
function load_rules(    line, raw, name, i, val, parts) {
    while ((getline line < (APP "/src/audit_rules.pli")) > 0) {
        raw = trim(line)
        if (toupper(raw) !~ /^DCL / || index(raw, "INIT(") == 0) continue
        name = toupper(raw); sub(/^DCL /, "", name); sub(/ .*/, "", name)
        i = index(raw, "INIT('"); if (i == 0) continue
        val = substr(raw, i + 6); sub(/'.*/, "", val); val = trim(val)
        rules[name] = val
        if (name ~ /^ALIAS_/ && index(val, "=>") > 0) {
            split(val, parts, "=>")
            aliases[up(parts[1])] = up(parts[2])
            aliases[up(parts[2])] = up(parts[2])
        }
    }
    close(APP "/src/audit_rules.pli")
}
function load_batch(    line, parts) {
    while ((getline line < (APP "/src/audit_batch.pli")) > 0) {
        if (line !~ /^%SET[ \t]+/) continue
        split(trim(line), parts, /[ \t]+/)
        if (parts[1] == "%SET" && length(parts) >= 3) {
            if (parts[2] == "KEY_COMPARE") KEY_COMPARE = parts[3]
            else if (parts[2] == "CONSUME") CONSUME = parts[3]
            else if (parts[2] == "ALIAS_MODE") ALIAS_MODE = parts[3]
            else if (parts[2] == "WINDOW_MODE") WINDOW_MODE = parts[3]
        }
    }
    close(APP "/src/audit_batch.pli")
}
function canon(field,    k) {
    k = up(field)
    return ((ALIAS_MODE == "ON" && (k in aliases)) ? aliases[k] : k)
}
function nts(x) { return length(x) == 14 && x ~ /^[0-9]+$/ }
function keys_ok(si, ai,    fi, f) {
    if (KEY_COMPARE == "PREFIX5") {
        return substr(cat[si, "frame_id"], 1, 5) == substr(aud[ai, "frame_id"], 1, 5) \
            && cat[si, "payload_hash"] == aud[ai, "payload_hash"]
    }
    for (fi = 1; fi <= nkeys; fi++) {
        f = key_fields[fi]
        if (canon(cat[si, f]) != canon(aud[ai, f])) return 0
    }
    return 1
}
function win_ok(si, ai,    wi, o, c, st, at) {
    if (WINDOW_MODE != "ON") return 1
    st = cat[si, "recv_ts"]; at = aud[ai, "audit_ts"]
    if (!nts(st) || !nts(at)) return 0
    for (wi = 1; wi <= wcount; wi++) {
        if (win[wi, "craft_id"] != cat[si, "craft_id"]) continue
        if (up(win[wi, "state"]) != up(rules["OPEN_PASS_STATE"])) continue
        o = win[wi, "open_ts"]; c = win[wi, "close_ts"]
        if (nts(o) && nts(c) && o <= st && st <= c && st <= at && at <= c) return 1
    }
    return 0
}
function verdict_ok(vcode,    vi) {
    for (vi = 1; vi <= 3; vi++) if (up(vcode) == up(rules["VERDICT_" substr("ABC", vi, 1)]) ) return 1
    return 0
}
END {
    load_rules(); load_batch()
    eligible = up(rules["ELIGIBLE_STATE"])
    scount = 0
    chdr_done = 0
    while ((getline line < (APP "/data/catalog.psv")) > 0) {
        if (!chdr_done) { split(line, chdr, "|"); chdr_done = 1; continue }
        scount++
        split(line, cf, "|")
        for (ci = 1; ci <= length(chdr); ci++) cat[scount, chdr[ci]] = trim(cf[ci])
    }
    close(APP "/data/catalog.psv")
    acount = 0
    ahdr_done = 0
    while ((getline line < (APP "/data/audits.psv")) > 0) {
        if (!ahdr_done) { split(line, ahdr, "|"); ahdr_done = 1; continue }
        acount++
        split(line, af, "|")
        for (ai2 = 1; ai2 <= length(ahdr); ai2++) aud[acount, ahdr[ai2]] = trim(af[ai2])
    }
    close(APP "/data/audits.psv")
    wcount = 0
    if (WINDOW_MODE == "ON") {
        whdr_done = 0
        while ((getline line < (APP "/config/pass_windows.psv")) > 0) {
            if (!whdr_done) { split(line, whdr, "|"); whdr_done = 1; continue }
            wcount++
            split(line, wf, "|")
            for (wi2 = 1; wi2 <= length(whdr); wi2++) win[wcount, whdr[wi2]] = trim(wf[wi2])
        }
        close(APP "/config/pass_windows.psv")
    }
    system("mkdir -p " APP "/out")
    mc = uc = ma = ua = 0
    print "audit_id", "frame_id", "craft_id", "channel", "service_class", "payload_hash", "verdict_code", "status" > (APP "/out/audit_report.csv")
    for (ai = 1; ai <= acount; ai++) {
        best = 0
        for (si = 1; si <= scount; si++) {
            if (CONSUME == "ON" && used[si]) continue
            if (!keys_ok(si, ai)) continue
            if (up(cat[si, "state"]) != eligible) continue
            if (!verdict_ok(aud[ai, "verdict_code"])) continue
            if (!win_ok(si, ai)) continue
            if (best == 0 || cat[si, "recv_ts"] > cat[best, "recv_ts"] \
                || (cat[si, "recv_ts"] == cat[best, "recv_ts"] && si < best)) best = si
        }
        if (best == 0) {
            uc++; ua++; cls = ""; status = "REJECTED"
        } else {
            if (CONSUME == "ON") used[best] = 1
            mc++; ma++; cls = canon(cat[best, "service_class"]); status = "ACCEPTED"
        }
        print aud[ai, "audit_id"], aud[ai, "frame_id"], aud[ai, "craft_id"], aud[ai, "channel"], \
            cls, aud[ai, "payload_hash"], aud[ai, "verdict_code"], status >> (APP "/out/audit_report.csv")
    }
    print "matched_count=" mc > (APP "/out/audit_summary.txt")
    print "matched_frames=" ma >> (APP "/out/audit_summary.txt")
    print "rejected_count=" uc >> (APP "/out/audit_summary.txt")
    print "rejected_frames=" ua >> (APP "/out/audit_summary.txt")
}
