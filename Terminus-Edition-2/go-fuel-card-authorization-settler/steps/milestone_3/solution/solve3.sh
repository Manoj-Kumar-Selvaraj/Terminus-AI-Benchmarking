#!/bin/bash
set -euo pipefail
cat > /app/internal/reconcile/reconcile.go <<'GO'
package reconcile

import (
    "encoding/csv"
    "fmt"
    "os"
    "path/filepath"
    "strconv"
    "strings"
)

const milestoneLevel = 3
const defaultPriority = 1000000000

type sourceRow struct {
    authID, fleetID, batchID, kindRaw, kind, amountRaw, sourceTS, status, location string
    candidateRef string
    amountValue int
    amountOK bool
    row int
    used bool
}

type actionRow struct {
    actionID, authID, fleetID, batchID, kindRaw, kind, amountRaw, actionTS, reason, location string
    candidateRef string
    amountValue int
    amountOK bool
    any bool
    row int
}

type windowRow struct { batchID, openTS, closeTS, state string }
type kindRule struct { present bool; enabled bool; priority int }
type policyRule struct { present bool; enabled bool; allowAny bool; maxAmount int }

func trim(s string) string { return strings.TrimSpace(s) }
func upper(s string) string { return strings.ToUpper(strings.TrimSpace(s)) }

func firstNonEmpty(row []string) string {
    for _, v := range row { if trim(v) != "" { return trim(v) } }
    return ""
}

func readCSV(path string) ([]map[string]string, error) {
    f, err := os.Open(path)
    if err != nil { return nil, err }
    defer f.Close()
    r := csv.NewReader(f)
    r.FieldsPerRecord = -1
    rows, err := r.ReadAll()
    if err != nil { return nil, err }
    if len(rows) == 0 { return nil, nil }
    headers := rows[0]
    out := []map[string]string{}
    for _, row := range rows[1:] {
        first := firstNonEmpty(row)
        if first == "" || strings.HasPrefix(first, "#") { continue }
        m := map[string]string{}
        for i, h := range headers {
            key := trim(h)
            if key == "" { continue }
            if i < len(row) { m[key] = trim(row[i]) } else { m[key] = "" }
        }
        out = append(out, m)
    }
    return out, nil
}

func mustReadCSV(path string) []map[string]string {
    rows, err := readCSV(path)
    if err != nil { panic(err) }
    return rows
}

func is14Digits(s string) bool {
    s = trim(s)
    if len(s) != 14 { return false }
    for _, r := range s { if r < '0' || r > '9' { return false } }
    return true
}

func parsePositive(s string) (int, bool) {
    s = trim(s)
    if s == "" { return 0, false }
    for _, r := range s { if r < '0' || r > '9' { return 0, false } }
    v, err := strconv.Atoi(s)
    if err != nil || v <= 0 { return 0, false }
    return v, true
}

func supportedCanonical(k string) bool {
    switch k {
    case "DIESEL", "GAS": return true
    case "EV": return milestoneLevel >= 2
    default: return false
    }
}

func loadAliases() map[string]string {
    aliases := map[string]string{"DIESEL":"DIESEL", "GAS":"GAS"}
    if milestoneLevel >= 2 { aliases["EV"] = "EV" }
    if milestoneLevel < 2 { return aliases }
    seen := map[string]bool{}
    rows, err := readCSV("/app/config/kind_aliases.csv")
    if err != nil { return aliases }
    for _, row := range rows {
        a := upper(row["alias"])
        c := upper(row["canonical"])
        if a == "" || c == "" || !supportedCanonical(c) { continue }
        if aliases[a] != "" || seen[a] { continue }
        aliases[a] = c
        seen[a] = true
    }
    return aliases
}

func canonicalKind(raw string, aliases map[string]string) (string, bool) {
    u := upper(raw)
    if u == "" { return "", false }
    if u == "ANY" && milestoneLevel >= 4 { return "ANY", true }
    c, ok := aliases[u]
    if !ok || !supportedCanonical(c) { return u, false }
    return c, true
}

func loadKindRules(aliases map[string]string) map[string]kindRule {
    rules := map[string]kindRule{}
    if milestoneLevel < 4 {
        for _, k := range []string{"DIESEL", "GAS", "EV"} {
            if supportedCanonical(k) { rules[k] = kindRule{present:true, enabled:true, priority:defaultPriority} }
        }
        return rules
    }
    rows, err := readCSV("/app/config/kinds.csv")
    if err != nil { return rules }
    for idx, row := range rows {
        raw := row["kind"]
        if trim(raw) == "" { continue }
        canon, ok := canonicalKind(raw, aliases)
        if !ok || canon == "ANY" || !supportedCanonical(canon) { continue }
        enabledText := strings.ToLower(trim(row["enabled"]))
        if enabledText != "true" && enabledText != "false" { continue }
        pri := defaultPriority + idx
        if pText := trim(row["priority"]); pText != "" {
            if p, err := strconv.Atoi(pText); err == nil { pri = p }
        }
        rules[canon] = kindRule{present:true, enabled:enabledText == "true", priority:pri}
    }
    return rules
}

func kindEnabled(kind string, rules map[string]kindRule) bool {
    r, ok := rules[kind]
    return ok && r.present && r.enabled
}

func kindPriority(kind string, rules map[string]kindRule) int {
    if r, ok := rules[kind]; ok && r.present { return r.priority }
    return defaultPriority
}

func loadReasons() map[string]bool {
    if milestoneLevel < 4 { return map[string]bool{"VOID":true, "DUPLICATE":true, "LIMIT":true} }
    reasons := map[string]bool{}
    rows, err := readCSV("/app/config/reasons.csv")
    if err != nil { return reasons }
    for _, row := range rows {
        r := upper(row["reason"])
        e := upper(row["eligible"])
        if r == "" || e == "" { continue }
        reasons[r] = e == "Y"
    }
    return reasons
}

func reasonEligible(reason string, reasons map[string]bool) bool { return reasons[upper(reason)] }

func loadWindows() []windowRow {
    out := []windowRow{}
    rows, err := readCSV("/app/config/windows.csv")
    if err != nil { return out }
    for _, row := range rows { out = append(out, windowRow{trim(row["batch_id"]), trim(row["open_ts"]), trim(row["close_ts"]), upper(row["state"])}) }
    return out
}

func windowOK(src sourceRow, act actionRow, windows []windowRow) bool {
    if !is14Digits(src.sourceTS) || !is14Digits(act.actionTS) { return false }
    for _, w := range windows {
        if w.batchID != src.batchID || w.state != "OPEN" { continue }
        if !is14Digits(w.openTS) || !is14Digits(w.closeTS) || w.openTS > w.closeTS { continue }
        if w.openTS <= src.sourceTS && src.sourceTS <= act.actionTS && act.actionTS <= w.closeTS { return true }
    }
    return false
}

func policyKey(fleet, batch, loc string) string { return trim(fleet)+"\x00"+trim(batch)+"\x00"+trim(loc) }

func parseBoolText(s string) (bool, bool) {
    switch strings.ToLower(trim(s)) {
    case "true": return true, true
    case "false": return false, true
    default: return false, false
    }
}

func loadPolicies() map[string]policyRule {
    policies := map[string]policyRule{}
    if milestoneLevel < 5 { return policies }
    rows, err := readCSV("/app/config/fleet_policies.csv")
    if err != nil { return policies }
    for _, row := range rows {
        fleet, batch, loc := trim(row["fleet_id"]), trim(row["batch_id"]), trim(row["location"])
        maxAmount, amountOK := parsePositive(row["max_reversal_amount"])
        allowAny, allowOK := parseBoolText(row["allow_any"])
        enabled, enabledOK := parseBoolText(row["enabled"])
        if fleet == "" || batch == "" || loc == "" || !amountOK || !allowOK || !enabledOK { continue }
        policies[policyKey(fleet,batch,loc)] = policyRule{present:true, enabled:enabled, allowAny:allowAny, maxAmount:maxAmount}
    }
    return policies
}

func policyAllows(act actionRow, policies map[string]policyRule) bool {
    if milestoneLevel < 5 { return true }
    pol, ok := policies[policyKey(act.fleetID, act.batchID, act.location)]
    if !ok || !pol.present || !pol.enabled { return false }
    if !act.amountOK || act.amountValue > pol.maxAmount { return false }
    if act.any && !pol.allowAny { return false }
    return true
}

func loadSources(aliases map[string]string) []sourceRow {
    rows := mustReadCSV("/app/data/authorizations.csv")
    out := []sourceRow{}
    for idx, row := range rows {
        amountRaw := trim(row["amount"])
        amountValue, amountOK := parsePositive(amountRaw)
        kind, _ := canonicalKind(row["kind"], aliases)
        out = append(out, sourceRow{authID:trim(row["auth_id"]), fleetID:trim(row["fleet_id"]), batchID:trim(row["batch_id"]), kindRaw:trim(row["kind"]), kind:kind, amountRaw:amountRaw, amountValue:amountValue, amountOK:amountOK, sourceTS:trim(row["source_ts"]), status:trim(row["status"]), location:trim(row["location"]), candidateRef:trim(row["candidate_ref"]), row:idx})
    }
    return out
}

func loadActions(aliases map[string]string) []actionRow {
    rows := mustReadCSV("/app/data/reversals.csv")
    out := []actionRow{}
    for idx, row := range rows {
        amountRaw := trim(row["amount"])
        amountValue, amountOK := parsePositive(amountRaw)
        kind, ok := canonicalKind(row["kind"], aliases)
        any := ok && kind == "ANY" && milestoneLevel >= 4
        out = append(out, actionRow{actionID:trim(row["action_id"]), authID:trim(row["auth_id"]), fleetID:trim(row["fleet_id"]), batchID:trim(row["batch_id"]), kindRaw:trim(row["kind"]), kind:kind, amountRaw:amountRaw, amountValue:amountValue, amountOK:amountOK, actionTS:trim(row["action_ts"]), reason:trim(row["reason"]), location:trim(row["location"]), candidateRef:trim(row["candidate_ref"]), any:any, row:idx})
    }
    return out
}

func sourceMatches(src sourceRow, act actionRow, reasons map[string]bool, kinds map[string]kindRule, windows []windowRow, policies map[string]policyRule) bool {
    if src.used { return false }
    if src.authID != act.authID || src.fleetID != act.fleetID || src.batchID != act.batchID || src.location != act.location { return false }
    if act.candidateRef != "" && act.candidateRef != src.candidateRef { return false }
    if trim(src.status) != "SETTLED" { return false }
    if !src.amountOK || !act.amountOK || src.amountValue != act.amountValue { return false }
    if !kindEnabled(src.kind, kinds) { return false }
    if act.any {
        if milestoneLevel < 4 { return false }
    } else if act.kind != src.kind || !kindEnabled(act.kind, kinds) { return false }
    if !reasonEligible(act.reason, reasons) { return false }
    if !windowOK(src, act, windows) { return false }
    if !policyAllows(act, policies) { return false }
    return true
}

func betterCandidate(candidate, current int, act actionRow, sources []sourceRow, kinds map[string]kindRule) bool {
    if current < 0 { return true }
    if milestoneLevel < 3 { return false }
    c, b := sources[candidate], sources[current]
    if c.sourceTS != b.sourceTS { return c.sourceTS > b.sourceTS }
    if milestoneLevel >= 4 && act.any {
        cp, bp := kindPriority(c.kind, kinds), kindPriority(b.kind, kinds)
        if cp != bp { return cp < bp }
    }
    return c.row < b.row
}

func selectSource(sources []sourceRow, act actionRow, reasons map[string]bool, kinds map[string]kindRule, windows []windowRow, policies map[string]policyRule) int {
    best := -1
    for i, src := range sources {
        if !sourceMatches(src, act, reasons, kinds, windows, policies) { continue }
        if betterCandidate(i, best, act, sources, kinds) { best = i }
    }
    return best
}

func writeSummary(matchedCount, matchedAmount, unmatchedCount, unmatchedAmount int) error {
    body := fmt.Sprintf("matched_count=%d\nmatched_amount=%d\nunmatched_count=%d\nunmatched_amount=%d\n", matchedCount, matchedAmount, unmatchedCount, unmatchedAmount)
    return os.WriteFile(filepath.Clean("/app/out/fuel_reversal_summary.txt"), []byte(body), 0o644)
}

func Run() error {
    aliases := loadAliases()
    kinds := loadKindRules(aliases)
    reasons := loadReasons()
    windows := loadWindows()
    policies := loadPolicies()
    sources := loadSources(aliases)
    actions := loadActions(aliases)
    if err := os.MkdirAll("/app/out", 0o755); err != nil { return err }
    report, err := os.Create("/app/out/fuel_reversal_report.csv")
    if err != nil { return err }
    defer report.Close()
    writer := csv.NewWriter(report)
    defer writer.Flush()
    if err := writer.Write([]string{"action_id", "auth_id", "fleet_id", "batch_id", "kind", "amount", "reason", "status"}); err != nil { return err }
    matchedCount, matchedAmount, unmatchedCount, unmatchedAmount := 0,0,0,0
    for _, act := range actions {
        best := selectSource(sources, act, reasons, kinds, windows, policies)
        if best >= 0 {
            sources[best].used = true
            matchedCount++
            matchedAmount += act.amountValue
            if err := writer.Write([]string{act.actionID, act.authID, act.fleetID, act.batchID, sources[best].kind, act.amountRaw, act.reason, "MATCHED"}); err != nil { return err }
        } else {
            unmatchedCount++
            if act.amountOK { unmatchedAmount += act.amountValue }
            if err := writer.Write([]string{act.actionID, act.authID, act.fleetID, act.batchID, "", act.amountRaw, act.reason, "UNMATCHED"}); err != nil { return err }
        }
    }
    writer.Flush()
    if err := writer.Error(); err != nil { return err }
    return writeSummary(matchedCount, matchedAmount, unmatchedCount, unmatchedAmount)
}

GO
/app/scripts/run_batch.sh
