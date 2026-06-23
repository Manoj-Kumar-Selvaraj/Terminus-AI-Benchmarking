BEGIN {
    KEY_COMPARE = "PREFIX5"; CONSUME = "OFF"; ALIAS_MODE = "OFF"; WINDOW_MODE = "OFF"
    VALIDATE_MODE = "OFF"; CONTROL_MODE = "OFF"; DOWNSTREAM_MODE = "OFF"; GROUP_MODE = "OFF"
    LEDGER_MODE = "OFF"; CUTOFF_MODE = "OFF"; CAPACITY_MODE = "OFF"; HOLD_MODE = "OFF"
    RESTART_MODE = "OFF"; SEQUENCE_MODE = "OFF"
    APP = "/app"; FS = OFS = "|"
    split("line_id stream_id value_cents base_radix segment_id", key_fields, " "); nkeys = 5
}
function trim(s) { sub(/^[ \t\r\n]+/, "", s); sub(/[ \t\r\n]+$/, "", s); return s }
function up(s) { return toupper(trim(s)) }
function posint(x) { return trim(x) ~ /^[1-9][0-9]*$/ }
function nonnegint(x) { return trim(x) ~ /^[0-9]+$/ }
function signedint(x,    t) { t = trim(x); return t ~ /^-?[1-9][0-9]*$/ || t == "0" }
function nts(x) { return length(trim(x)) == 14 && trim(x) ~ /^[0-9]+$/ }
function abs(x) { return x < 0 ? -x : x }
function load_rules(    line, raw, name, i, val, parts) {
    while ((getline line < (APP "/src/rollup_rules.pli")) > 0) {
        raw = trim(line); if (toupper(raw) !~ /^DCL / || index(raw, "INIT(") == 0) continue
        name = toupper(raw); sub(/^DCL /, "", name); sub(/ .*/, "", name)
        i = index(raw, "INIT('"); if (i == 0) continue
        val = substr(raw, i + 6); sub(/'.*/, "", val); rules[name] = trim(val)
        if (name ~ /^ALIAS_/ && index(val, "=>") > 0) {
            split(val, parts, "=>"); aliases[up(parts[1])] = up(parts[2]); aliases[up(parts[2])] = up(parts[2])
        }
    }
    close(APP "/src/rollup_rules.pli")
}
function load_batch(    line, parts) {
    while ((getline line < (APP "/src/rollup_batch.pli")) > 0) {
        if (line !~ /^%SET[ \t]+/) continue
        split(trim(line), parts, /[ \t]+/)
        if (parts[2] == "KEY_COMPARE") KEY_COMPARE = parts[3]
        else if (parts[2] == "CONSUME") CONSUME = parts[3]
        else if (parts[2] == "ALIAS_MODE") ALIAS_MODE = parts[3]
        else if (parts[2] == "WINDOW_MODE") WINDOW_MODE = parts[3]
        else if (parts[2] == "VALIDATE_MODE") VALIDATE_MODE = parts[3]
        else if (parts[2] == "CONTROL_MODE") CONTROL_MODE = parts[3]
        else if (parts[2] == "DOWNSTREAM_MODE") DOWNSTREAM_MODE = parts[3]
        else if (parts[2] == "GROUP_MODE") GROUP_MODE = parts[3]
        else if (parts[2] == "LEDGER_MODE") LEDGER_MODE = parts[3]
        else if (parts[2] == "CUTOFF_MODE") CUTOFF_MODE = parts[3]
        else if (parts[2] == "CAPACITY_MODE") CAPACITY_MODE = parts[3]
        else if (parts[2] == "HOLD_MODE") HOLD_MODE = parts[3]
        else if (parts[2] == "RESTART_MODE") RESTART_MODE = parts[3]
        else if (parts[2] == "SEQUENCE_MODE") SEQUENCE_MODE = parts[3]
    }
    close(APP "/src/rollup_batch.pli")
}
function load_psv(path, arr,    line, hdr_done, hdr, fields, c, row) {
    row = 0; hdr_done = 0
    while ((getline line < path) > 0) {
        if (trim(line) == "") continue
        if (!hdr_done) { split(line, hdr, "|"); hdr_done = 1; continue }
        row++; split(line, fields, "|")
        for (c = 1; c <= length(hdr); c++) arr[row, hdr[c]] = trim(fields[c])
    }
    close(path)
    return row
}
function canon(f,    k) { k = up(f); return ((ALIAS_MODE == "ON" && (k in aliases)) ? aliases[k] : k) }
function group_key(stream, radix, segment) { return up(stream) SUBSEP canon(radix) SUBSEP canon(segment) }
function group_label(g,    p) { split(g, p, SUBSEP); return p[1] "|" p[2] "|" p[3] }
function committed_key(c, l, s, g) { return up(c) "|" up(l) "|" up(s) "|" up(g) }
function keys_ok(si, ai,    fi, f) {
    if (KEY_COMPARE == "PREFIX5") {
        return substr(src[si, "line_id"], 1, 5) == substr(act[ai, "line_id"], 1, 5) && src[si, "value_cents"] == act[ai, "value_cents"]
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
function direction_ok(ai,    amt, op, neg) {
    if (!("NEGATIVE_OPCODE_CODES" in rules)) return (0 + act[ai, "value_cents"]) > 0
    amt = 0 + act[ai, "value_cents"]; op = up(act[ai, "opcode"])
    neg = "," up(rules["NEGATIVE_OPCODE_CODES"]) ","
    if (index(neg, "," op ",")) return amt < 0
    return amt > 0
}
function data_ok(si, ai,    fi, f) {
    if (VALIDATE_MODE != "ON") return 1
    for (fi = 1; fi <= nkeys; fi++) {
        f = key_fields[fi]
        if (trim(src[si, f]) == "" || trim(act[ai, f]) == "") return 0
    }
    if (!signedint(src[si, "value_cents"]) || !signedint(act[ai, "value_cents"])) return 0
    if (!direction_ok(ai)) return 0
    return nts(src[si, "ingest_ts"]) && nts(act[ai, "rollup_ts"])
}
function win_ok(si, ai,    wi, o, c, st, at) {
    if (WINDOW_MODE != "ON") return 1
    st = src[si, "ingest_ts"]; at = act[ai, "rollup_ts"]
    if (!nts(st) || !nts(at)) return 0
    for (wi = 1; wi <= wcount; wi++) {
        if (up(win[wi, "stream_id"]) != up(src[si, "stream_id"])) continue
        if (up(win[wi, "state"]) != up(rules["OPEN_ROLLUP_STATE"])) continue
        o = win[wi, "open_ts"]; c = win[wi, "close_ts"]
        if (nts(o) && nts(c) && o <= c && o <= st && st <= c && st <= at && at <= c) return 1
    }
    return 0
}
function cutoff_ok(si, ai,    di, day, cutoff) {
    if (CUTOFF_MODE != "ON") return 1
    if (!nts(src[si, "ingest_ts"]) || !nts(act[ai, "rollup_ts"])) return 0
    day = substr(src[si, "ingest_ts"], 1, 8)
    for (di = 1; di <= calcount; di++) {
        if (cal[di, "business_date"] != day) continue
        if (up(cal[di, "state"]) != "OPEN") return 0
        cutoff = cal[di, "cutoff_ts"]
        return nts(cutoff) && src[si, "ingest_ts"] <= cutoff && act[ai, "rollup_ts"] <= cutoff
    }
    return 0
}
function seq_slot(stream, segment) { return up(stream) SUBSEP canon(segment) }
function sequence_ok(si, ai,    slot, expected_seq, sn, min_unused, sj) {
    if (SEQUENCE_MODE != "ON") return 1
    expected_seq = trim(act[ai, "expected_seq"]); sn = trim(src[si, "seq_no"])
    if (expected_seq == "" || sn == "") return 0
    if (expected_seq != sn) return 0
    slot = seq_slot(src[si, "stream_id"], src[si, "segment_id"])
    min_unused = 999999999
    for (sj = 1; sj <= scount; sj++) {
        if (CONSUME == "ON" && used[sj]) continue
        if (seq_slot(src[sj, "stream_id"], src[sj, "segment_id"]) != slot) continue
        if (0 + src[sj, "seq_no"] < min_unused) min_unused = 0 + src[sj, "seq_no"]
    }
    return (0 + sn) == min_unused
}
function load_ledger(    i, key) {
    if (LEDGER_MODE != "ON") return
    lcount = load_psv(APP "/state/rollup_ledger.psv", led)
    for (i = 1; i <= lcount; i++) {
        if (up(led[i, "status"]) != "COMMITTED") continue
        key = committed_key(led[i, "claim_id"], led[i, "line_id"], led[i, "stream_id"], led[i, "segment_id"])
        committed[key] = 1
    }
    checkpoint_status = "OK"
    if ((getline checkpoint < (APP "/state/restart_checkpoint.txt")) <= 0) checkpoint_status = "MISSING"
    close(APP "/state/restart_checkpoint.txt")
    if (checkpoint_status == "OK" && checkpoint !~ /^[0-9]+$/) checkpoint_status = "STALE"
    if (checkpoint_status == "OK" && (0 + checkpoint) > lcount) checkpoint_status = "AHEAD"
}
function load_capacity(    i, k) {
    if (CAPACITY_MODE != "ON") return
    capcount = load_psv(APP "/config/stream_capacity.psv", cap)
    for (i = 1; i <= capcount; i++) {
        k = up(cap[i, "stream_id"]) "|" canon(cap[i, "base_radix"])
        limit[k] = 0 + cap[i, "limit_cents"]
    }
    if (HOLD_MODE == "ON") {
        hcount = load_psv(APP "/config/directive_holds.psv", hold)
        for (i = 1; i <= hcount; i++) holds[up(hold[i, "claim_id"])] = hold[i, "hold_reason"]
    }
    if (RESTART_MODE == "ON") commit_count = load_psv(APP "/state/rollup_commits.psv", commits)
    for (i = 1; i <= commit_count; i++) {
        k = up(commits[i, "stream_id"]) "|" up(commits[i, "base_radix"]) "|" up(commits[i, "segment_id"])
        commit_seen[k] = 1
    }
}
function exception(ai, reason, detail) {
    excount++
    exc[excount] = act[ai, "claim_id"] "|" act[ai, "line_id"] "|" act[ai, "stream_id"] "|" reason "|" detail
}
function load_weights(    i, key, n, d) {
    if (CONTROL_MODE != "ON") return
    wcount2 = load_psv(APP "/config/radix_weights.psv", wgt)
    for (i = 1; i <= wcount2; i++) {
        key = canon(wgt[i, "base_radix"])
        n = wgt[i, "weight_numerator"]; d = wgt[i, "weight_denominator"]
        if (key != "" && posint(n) && posint(d) && up(wgt[i, "state"]) == "ACTIVE") {
            weight_num[key] = 0 + n; weight_den[key] = 0 + d
        }
    }
}
function load_controls(    i, g) {
    if (CONTROL_MODE != "ON") return
    ccount = load_psv(APP "/config/control_totals.psv", ctrl)
    for (i = 1; i <= ccount; i++) {
        g = group_key(ctrl[i, "stream_id"], ctrl[i, "base_radix"], ctrl[i, "segment_id"])
        if (g == "" || !posint(ctrl[i, "expected_count"]) || !nonnegint(ctrl[i, "expected_weighted_cents"]) || !nonnegint(ctrl[i, "tolerance_cents"])) continue
        ctrl_seen[g] = 1
        ctrl_count[g] = 0 + ctrl[i, "expected_count"]
        ctrl_weighted[g] = 0 + ctrl[i, "expected_weighted_cents"]
        ctrl_tol[g] = 0 + ctrl[i, "tolerance_cents"]
    }
}
function add_group(ai, radix, segment, cents,    g, r, weighted, signed_cents) {
    g = group_key(act[ai, "stream_id"], radix, segment)
    row_group[ai] = g
    if (!(g in g_seen)) { g_seen[g] = 1; gorder[++gorder_count] = g }
    g_count[g]++; g_amount[g] += cents
    r = canon(radix)
    if ((r in weight_num) && (cents * weight_num[r]) % weight_den[r] == 0) {
        weighted = cents * weight_num[r] / weight_den[r]
        g_weighted[g] += weighted
    } else {
        g_weight_bad[g] = 1
    }
    signed_cents = 0 + act[ai, "value_cents"]
    nk = trim(act[ai, "netting_key"])
    if (nk != "") {
        if (!(nk in net_seen)) { net_seen[nk] = 1; netorder[++netorder_count] = nk }
        if ((r in weight_num) && (signed_cents * weight_num[r]) % weight_den[r] == 0)
            net_weighted[nk] += signed_cents * weight_num[r] / weight_den[r]
        else
            net_weighted[nk] += signed_cents
    }
}
function write_commits(    gi, g, p, ts) {
    if (RESTART_MODE != "ON") return
    print "stream_id|base_radix|segment_id|rolled_count|rolled_total_cents|committed_ts" > (APP "/out/rollup_commits.psv")
    for (i = 1; i <= commit_count; i++) {
        print commits[i, "stream_id"], commits[i, "base_radix"], commits[i, "segment_id"], commits[i, "rolled_count"], commits[i, "rolled_total_cents"], commits[i, "committed_ts"] >> (APP "/out/rollup_commits.psv")
    }
    ts = "20260612180000"
    for (gi = 1; gi <= gorder_count; gi++) {
        g = gorder[gi]
        if (!control_ok[g]) continue
        split(group_label(g), p, "|")
        ckey = up(p[1]) "|" up(p[2]) "|" up(p[3])
        if (ckey in commit_seen) continue
        print p[1], p[2], p[3], g_count[g], g_amount[g], ts >> (APP "/out/rollup_commits.psv")
        commit_seen[ckey] = 1
    }
}
function apply_controls(    gi, g, ni, nk) {
    if (CONTROL_MODE != "ON") return
    for (gi = 1; gi <= gorder_count; gi++) {
        g = gorder[gi]
        control_ok[g] = (g in ctrl_seen) && !g_weight_bad[g] && g_count[g] == ctrl_count[g] && abs(g_weighted[g] - ctrl_weighted[g]) <= ctrl_tol[g]
    }
    if (SEQUENCE_MODE == "ON") {
        for (ni = 1; ni <= netorder_count; ni++) {
            nk = netorder[ni]
            if (net_weighted[nk] != 0) netting_ok[nk] = 0
            else netting_ok[nk] = 1
        }
    }
}
function downgrade_held_groups(    ai, g, nk) {
    if (GROUP_MODE != "ON" && !(SEQUENCE_MODE == "ON" && netorder_count > 0)) return
    for (ai = 1; ai <= acount; ai++) {
        if (out_status[ai] != "ROLLED") continue
        g = row_group[ai]
        if (GROUP_MODE == "ON" && CONTROL_MODE == "ON" && g != "" && !control_ok[g]) {
            out_status[ai] = "SKIPPED"; out_seg[ai] = ""
        }
        nk = trim(act[ai, "netting_key"])
        if (SEQUENCE_MODE == "ON" && nk != "" && ((!(nk in netting_ok)) || !netting_ok[nk])) {
            exception(ai, "NETTING_HOLD", nk)
            out_status[ai] = "SKIPPED"; out_seg[ai] = ""
        }
    }
}
function write_controls(    gi, g, p, ec, ew, tol, st) {
    if (CONTROL_MODE != "ON") return
    print "stream_id|base_radix|segment_id|actual_count|actual_weighted_cents|expected_count|expected_weighted_cents|tolerance_cents|status" > (APP "/out/rollup_controls.psv")
    for (gi = 1; gi <= gorder_count; gi++) {
        g = gorder[gi]; split(group_label(g), p, "|")
        if (g in ctrl_seen) { ec = ctrl_count[g]; ew = ctrl_weighted[g]; tol = ctrl_tol[g] } else { ec = ""; ew = ""; tol = "" }
        st = control_ok[g] ? "CONTROL_OK" : "CONTROL_HELD"
        print p[1], p[2], p[3], g_count[g], g_weighted[g] + 0, ec, ew, tol, st >> (APP "/out/rollup_controls.psv")
    }
}
function write_downstream(    gi, ai, g, p, accepted_groups, accepted_rows, rejected_rows, accepted_total, weighted_total, rejcode) {
    if (DOWNSTREAM_MODE != "ON") return
    system("mkdir -p " APP "/out/downstream")
    print "stream_id|base_radix|segment_id|rolled_count|rolled_total_cents|weighted_total_cents" > (APP "/out/downstream/accepted_rollups.psv")
    print "claim_id|line_id|stream_id|segment_id|reject_code|value_cents" > (APP "/out/downstream/rejected_rollups.psv")
    for (gi = 1; gi <= gorder_count; gi++) {
        g = gorder[gi]
        if (control_ok[g] && (!(SEQUENCE_MODE == "ON") || group_netting_ok(g))) {
            split(group_label(g), p, "|")
            print p[1], p[2], p[3], g_count[g], g_amount[g], g_weighted[g] + 0 >> (APP "/out/downstream/accepted_rollups.psv")
            accepted_groups++; accepted_rows += g_count[g]; accepted_total += g_amount[g]; weighted_total += g_weighted[g]
        }
    }
    for (ai = 1; ai <= acount; ai++) {
        if (CONTROL_MODE == "ON" && row_group[ai] != "" && !control_ok[row_group[ai]]) rejcode = "CONTROL_HELD"
        else if (out_status[ai] == "SKIPPED") rejcode = "SKIPPED_INPUT"
        else continue
        rejected_rows++
        print act[ai, "claim_id"], act[ai, "line_id"], act[ai, "stream_id"], act[ai, "segment_id"], rejcode, act[ai, "value_cents"] >> (APP "/out/downstream/rejected_rollups.psv")
    }
    printf("{\"schema_version\":\"rollup-downstream/v1\",\"accepted_groups\":%d,\"accepted_rows\":%d,\"rejected_rows\":%d,\"accepted_total_cents\":%d,\"weighted_total_cents\":%d}\n", accepted_groups, accepted_rows, rejected_rows, accepted_total, weighted_total) > (APP "/out/downstream/manifest.json")
}
function group_netting_ok(g,    ai, nk) {
    for (ai = 1; ai <= acount; ai++) {
        if (row_group[ai] != g) continue
        nk = trim(act[ai, "netting_key"])
        if (nk != "" && (!(nk in netting_ok) || !netting_ok[nk])) return 0
    }
    return 1
}
END {
    load_rules(); load_batch(); eligible = up(rules["ELIGIBLE_STATE"])
    scount = load_psv(APP "/data/directives.psv", src)
    acount = load_psv(APP "/data/accumulators.psv", act)
    if (WINDOW_MODE == "ON") wcount = load_psv(APP "/config/rollup_windows.psv", win); else wcount = 0
    if (CUTOFF_MODE == "ON") calcount = load_psv(APP "/config/rollup_calendar.psv", cal)
    load_ledger(); load_capacity(); load_weights(); load_controls()
    system("mkdir -p " APP "/out " APP "/state")
    mc = uc = ma = ua = 0; gorder_count = 0; nledger = excount = netorder_count = 0
    for (ai = 1; ai <= acount; ai++) {
        if (HOLD_MODE == "ON" && up(act[ai, "claim_id"]) in holds) {
            amt = abs(0 + act[ai, "value_cents"]); uc++; ua += amt
            out_status[ai] = "SKIPPED"; out_seg[ai] = ""
            exception(ai, "DIRECTIVE_HOLD", holds[up(act[ai, "claim_id"])])
            continue
        }
        ckey = committed_key(act[ai, "claim_id"], act[ai, "line_id"], act[ai, "stream_id"], act[ai, "segment_id"])
        if (LEDGER_MODE == "ON" && ckey in committed) {
            amt = abs(0 + act[ai, "value_cents"]); uc++; ua += amt
            out_status[ai] = "SKIPPED"; out_seg[ai] = ""
            exception(ai, "REPLAY_DUPLICATE", "already_committed")
            continue
        }
        best = 0
        for (si = 1; si <= scount; si++) {
            if (CONSUME == "ON" && used[si]) continue
            if (!data_ok(si, ai)) continue
            if (!keys_ok(si, ai)) continue
            if (up(src[si, "state"]) != eligible) continue
            if (!reason_ok(act[ai, "opcode"])) continue
            if (!win_ok(si, ai)) continue
            if (!cutoff_ok(si, ai)) continue
            if (!sequence_ok(si, ai)) continue
            if (best == 0 || src[si, "ingest_ts"] > src[best, "ingest_ts"] || (src[si, "ingest_ts"] == src[best, "ingest_ts"] && si < best)) best = si
        }
        amt = signedint(act[ai, "value_cents"]) ? abs(0 + act[ai, "value_cents"]) : 0
        row_group[ai] = ""; out_seg[ai] = ""
        if (best == 0) { uc++; ua += amt; out_status[ai] = "SKIPPED" }
        else {
            capkey = up(act[ai, "stream_id"]) "|" canon(src[best, "base_radix"])
            if (CAPACITY_MODE == "ON" && (capkey in limit) && spent[capkey] + amt > limit[capkey]) {
                uc++; ua += amt; out_status[ai] = "SKIPPED"; best = 0
                exception(ai, "CAPACITY_HOLD", capkey)
            }
        }
        if (best != 0) {
            if (CONSUME == "ON") used[best] = 1
            mc++; ma += amt; out_seg[ai] = canon(src[best, "segment_id"]); out_status[ai] = "ROLLED"
            if (CAPACITY_MODE == "ON" && (capkey in limit)) spent[capkey] += amt
            if (CONTROL_MODE == "ON") add_group(ai, src[best, "base_radix"], src[best, "segment_id"], amt)
            if (LEDGER_MODE == "ON") {
                ledger_new[++nledger] = act[ai, "claim_id"] "|" act[ai, "line_id"] "|" act[ai, "stream_id"] "|" act[ai, "segment_id"] "|" canon(src[best, "base_radix"]) "|" amt "|COMMITTED"
                committed[ckey] = 1
            }
        }
    }
    apply_controls()
    downgrade_held_groups()
    mc = uc = ma = ua = 0
    print "claim_id|line_id|stream_id|check_segment|segment_id|value_cents|opcode|status" > (APP "/out/rollup_report.csv")
    for (ai = 1; ai <= acount; ai++) {
        if (out_status[ai] == "SKIPPED") out_seg[ai] = ""
        amt = abs(0 + act[ai, "value_cents"])
        if (out_status[ai] == "ROLLED") { mc++; ma += amt } else { uc++; ua += amt }
        print act[ai, "claim_id"], act[ai, "line_id"], act[ai, "stream_id"], act[ai, "segment_id"], out_seg[ai], act[ai, "value_cents"], act[ai, "opcode"], out_status[ai] >> (APP "/out/rollup_report.csv")
    }
    print "rolled_count=" mc > (APP "/out/rollup_summary.txt")
    print "rolled_total_cents=" ma >> (APP "/out/rollup_summary.txt")
    print "skipped_count=" uc >> (APP "/out/rollup_summary.txt")
    print "skipped_total_cents=" ua >> (APP "/out/rollup_summary.txt")
    write_controls()
    write_downstream()
    write_commits()
    if (LEDGER_MODE == "ON") {
        print "claim_id|line_id|stream_id|segment_id|base_radix|value_cents|status" > (APP "/out/rollup_ledger.psv")
        for (i = 1; i <= lcount; i++) {
            print led[i, "claim_id"], led[i, "line_id"], led[i, "stream_id"], led[i, "segment_id"], led[i, "base_radix"], led[i, "value_cents"], led[i, "status"] >> (APP "/out/rollup_ledger.psv")
        }
        for (i = 1; i <= nledger; i++) print ledger_new[i] >> (APP "/out/rollup_ledger.psv")
        print "checkpoint_status=" checkpoint_status > (APP "/out/restart_audit.txt")
        print "committed_rows=" nledger >> (APP "/out/restart_audit.txt")
    }
    if (CAPACITY_MODE == "ON" || HOLD_MODE == "ON" || LEDGER_MODE == "ON" || SEQUENCE_MODE == "ON") {
        print "claim_id|line_id|stream_id|reason|detail" > (APP "/out/rollup_exceptions.csv")
        for (i = 1; i <= excount; i++) print exc[i] >> (APP "/out/rollup_exceptions.csv")
    }
    if (CAPACITY_MODE == "ON") {
        print "stream_id|base_radix|limit_cents|used_cents|remaining_cents" > (APP "/out/capacity_position.txt")
        for (k in limit) {
            split(k, kp, "|"); print kp[1], kp[2], limit[k], 0 + spent[k], limit[k] - (0 + spent[k]) >> (APP "/out/capacity_position.txt")
        }
    }
}
