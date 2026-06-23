BEGIN {
    KEY_COMPARE = "PREFIX5"; CONSUME = "OFF"; ALIAS_MODE = "OFF"; WINDOW_MODE = "OFF"
    GROUP_MODE = "OFF"; CONTROL_MODE = "OFF"; RESTART_MODE = "OFF"
    APP = "/app"; FS = OFS = "|"
    split("txn_id account_id amount_cents currency_code desk_id", key_fields, " "); nkeys = 5
}
function trim(s) { sub(/^[ \t\r\n]+/, "", s); sub(/[ \t\r\n]+$/, "", s); return s }
function up(s) { return toupper(trim(s)) }
function load_rules(    line, raw, name, i, val, parts) {
    while ((getline line < (APP "/src/ledger_rules.pli")) > 0) {
        raw = trim(line); if (toupper(raw) !~ /^DCL / || index(raw, "INIT(") == 0) continue
        name = toupper(raw); sub(/^DCL /, "", name); sub(/ .*/, "", name)
        i = index(raw, "INIT('"); if (i == 0) continue
        val = substr(raw, i + 6); sub(/'.*/, "", val); rules[name] = trim(val)
        if (name ~ /^ALIAS_/ && index(val, "=>") > 0) {
            split(val, parts, "=>"); aliases[up(parts[1])] = up(parts[2]); aliases[up(parts[2])] = up(parts[2])
        }
    }
    close(APP "/src/ledger_rules.pli")
}
function load_batch(    line, parts) {
    while ((getline line < (APP "/src/ledger_batch.pli")) > 0) {
        if (line !~ /^%SET[ \t]+/) continue
        split(trim(line), parts, /[ \t]+/)
        if (parts[2] == "KEY_COMPARE") KEY_COMPARE = parts[3]
        else if (parts[2] == "CONSUME") CONSUME = parts[3]
        else if (parts[2] == "ALIAS_MODE") ALIAS_MODE = parts[3]
        else if (parts[2] == "WINDOW_MODE") WINDOW_MODE = parts[3]
        else if (parts[2] == "GROUP_MODE") GROUP_MODE = parts[3]
        else if (parts[2] == "CONTROL_MODE") CONTROL_MODE = parts[3]
        else if (parts[2] == "RESTART_MODE") RESTART_MODE = parts[3]
    }
    close(APP "/src/ledger_batch.pli")
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
function nts(x) { return length(x) == 14 && x ~ /^[0-9]+$/ }
function keys_ok(si, ai,    fi, f) {
    if (KEY_COMPARE == "PREFIX5") {
        return substr(src[si, "txn_id"], 1, 5) == substr(act[ai, "txn_id"], 1, 5) && src[si, "amount_cents"] == act[ai, "amount_cents"]
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
    st = src[si, "book_ts"]; at = act[ai, "post_ts"]
    if (!nts(st) || !nts(at)) return 0
    for (wi = 1; wi <= wcount; wi++) {
        if (win[wi, "account_id"] != src[si, "account_id"]) continue
        if (up(win[wi, "state"]) != up(rules["OPEN_FX_STATE"])) continue
        o = win[wi, "open_ts"]; c = win[wi, "close_ts"]
        if (nts(o) && nts(c) && o <= st && st <= c && st <= at && at <= c) return 1
    }
    return 0
}
function group_key(ai, currency) { return act[ai, "account_id"] SUBSEP act[ai, "desk_id"] SUBSEP canon(currency) }
function group_label(g,    p) { split(g, p, SUBSEP); return p[1] "|" p[2] "|" p[3] }
function load_controls(    line, hdr_done, hdr, f, c, g, currency) {
    if (CONTROL_MODE != "ON") return
    hdr_done = 0
    while ((getline line < (APP "/config/control_totals.psv")) > 0) {
        if (trim(line) == "") continue
        if (!hdr_done) { split(line, hdr, "|"); hdr_done = 1; continue }
        split(line, f, "|")
        for (c = 1; c <= length(hdr); c++) ctl[hdr[c]] = trim(f[c])
        currency = canon(ctl["currency_code"])
        g = ctl["account_id"] SUBSEP ctl["desk_id"] SUBSEP currency
        ctrl_seen[g] = 1
        ctrl_count[g] = 0 + ctl["expected_count"]
        ctrl_amount[g] = 0 + ctl["expected_amount_cents"]
        ctrl_tolerance[g] = 0 + ctl["tolerance_cents"]
        delete ctl
    }
    close(APP "/config/control_totals.psv")
}
function control_ok(g,    diff) {
    if (CONTROL_MODE != "ON") return 1
    if (!(g in ctrl_seen)) return 0
    diff = g_amount[g] - ctrl_amount[g]
    if (diff < 0) diff = -diff
    return g_count[g] == ctrl_count[g] && diff <= ctrl_tolerance[g]
}
function load_commits(    line, hdr_done, p, g) {
    if (RESTART_MODE != "ON") return
    hdr_done = 0
    while ((getline line < (APP "/out/clearing_commits.psv")) > 0) {
        if (trim(line) == "") continue
        if (!hdr_done) { hdr_done = 1; already_committed["__header__"] = 1; continue }
        split(line, p, "|"); g = p[1] SUBSEP p[2] SUBSEP p[3]
        already_committed[g] = 1
    }
    close(APP "/out/clearing_commits.psv")
}
function ensure_commit_header() {
    if (RESTART_MODE != "ON") return
    if (!("__header__" in already_committed)) {
        print "account_id|desk_id|currency_code|cleared_count|cleared_amount_cents" >> (APP "/out/clearing_commits.psv")
        already_committed["__header__"] = 1
    }
}
function commit_group(g,    limit) {
    if (RESTART_MODE != "ON") return
    if (already_committed[g]) return
    ensure_commit_header()
    print group_label(g), g_count[g], g_amount[g] >> (APP "/out/clearing_commits.psv")
    already_committed[g] = 1
    new_commits++
    print "last_committed_group=" group_label(g) > (APP "/out/restart_checkpoint.txt")
    limit = 0 + ENVIRON["ABEND_AFTER_GROUPS"]
    if (limit > 0 && new_commits >= limit) {
        print "ABEND_AFTER_GROUPS reached after " group_label(g) > "/dev/stderr"
        exit 12
    }
}
function read_inputs() {
    scount = load_psv(APP "/data/ledger.psv", src)
    acount = load_psv(APP "/data/postings.psv", act)
    if (WINDOW_MODE == "ON") wcount = load_psv(APP "/config/fx_windows.psv", win)
    else wcount = 0
    load_controls(); load_commits()
}
function match_postings(    ai, si, best, amt, g, curr) {
    gorder_count = 0
    for (ai = 1; ai <= acount; ai++) {
        best = 0
        for (si = 1; si <= scount; si++) {
            if (CONSUME == "ON" && used[si]) continue
            if (!keys_ok(si, ai)) continue
            if (up(src[si, "state"]) != eligible) continue
            if (!reason_ok(act[ai, "entry_type"])) continue
            if (!win_ok(si, ai)) continue
            if (best == 0 || src[si, "book_ts"] > src[best, "book_ts"] || (src[si, "book_ts"] == src[best, "book_ts"] && si < best)) best = si
        }
        amt = 0 + act[ai, "amount_cents"]
        out_claim[ai] = act[ai, "claim_id"]; out_txn[ai] = act[ai, "txn_id"]
        out_account[ai] = act[ai, "account_id"]; out_desk[ai] = act[ai, "desk_id"]
        out_amount[ai] = act[ai, "amount_cents"]; out_entry[ai] = act[ai, "entry_type"]
        if (best == 0) {
            out_curr[ai] = ""; out_status[ai] = "HELD"; row_amt[ai] = amt; row_group[ai] = ""
        } else {
            if (CONSUME == "ON") used[best] = 1
            curr = (ALIAS_MODE == "ON" ? canon(src[best, "currency_code"]) : trim(src[best, "currency_code"]))
            out_curr[ai] = curr; out_status[ai] = "CLEARED"; row_amt[ai] = amt
            if (GROUP_MODE == "ON") {
                g = group_key(ai, curr); row_group[ai] = g
                if (!(g in g_seen)) { g_seen[g] = 1; gorder[++gorder_count] = g }
                g_count[g]++; g_amount[g] += amt
            }
        }
    }
}
function apply_group_controls(    gi, g, ai) {
    if (GROUP_MODE != "ON") return
    for (gi = 1; gi <= gorder_count; gi++) {
        g = gorder[gi]
        g_ok[g] = control_ok(g)
    }
    for (ai = 1; ai <= acount; ai++) {
        if (out_status[ai] == "CLEARED" && row_group[ai] != "" && !g_ok[row_group[ai]]) {
            out_status[ai] = "HELD"; out_curr[ai] = ""
        }
    }
}
function write_reports(    ai, amt, gi, g) {
    system("mkdir -p " APP "/out")
    print "claim_id|txn_id|account_id|desk_id|currency_code|amount_cents|entry_type|status" > (APP "/out/ledger_report.csv")
    mc = uc = ma = ua = 0
    for (ai = 1; ai <= acount; ai++) {
        amt = row_amt[ai]
        if (out_status[ai] == "CLEARED") { mc++; ma += amt }
        else { uc++; ua += amt }
        print out_claim[ai], out_txn[ai], out_account[ai], out_desk[ai], out_curr[ai], out_amount[ai], out_entry[ai], out_status[ai] >> (APP "/out/ledger_report.csv")
    }
    print "cleared_count=" mc > (APP "/out/ledger_summary.txt")
    print "cleared_amount_cents=" ma >> (APP "/out/ledger_summary.txt")
    print "held_count=" uc >> (APP "/out/ledger_summary.txt")
    print "held_amount_cents=" ua >> (APP "/out/ledger_summary.txt")

    if (GROUP_MODE == "ON") {
        print "account_id|desk_id|currency_code|actual_count|actual_amount_cents|expected_count|expected_amount_cents|tolerance_cents|status" > (APP "/out/clearing_groups.psv")
        for (gi = 1; gi <= gorder_count; gi++) {
            g = gorder[gi]
            split(group_label(g), gp, "|")
            if (CONTROL_MODE == "ON" && (g in ctrl_seen)) { ec = ctrl_count[g]; ea = ctrl_amount[g]; tol = ctrl_tolerance[g] }
            else { ec = ""; ea = ""; tol = "" }
            gs = g_ok[g] ? "COMMITTED" : "HELD_CONTROL"
            print gp[1], gp[2], gp[3], g_count[g], g_amount[g], ec, ea, tol, gs >> (APP "/out/clearing_groups.psv")
        }
    }
}
function commit_reports(    gi, g) {
    if (RESTART_MODE != "ON") return
    new_commits = 0
    for (gi = 1; gi <= gorder_count; gi++) {
        g = gorder[gi]
        if (g_ok[g]) commit_group(g)
    }
}
END {
    load_rules(); load_batch(); eligible = up(rules["ELIGIBLE_STATE"])
    read_inputs(); match_postings(); apply_group_controls(); write_reports(); commit_reports()
}
