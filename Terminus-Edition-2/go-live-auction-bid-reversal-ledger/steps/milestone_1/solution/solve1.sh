#!/bin/bash
set -euo pipefail
cat > /app/cmd/reconcile/main.go <<'GO'
package main

import (
    "encoding/csv"
    "fmt"
    "os"
    "path/filepath"
    "sort"
    "strconv"
    "strings"
)

const aliasMode = "none"
const reasonMode = "static"
const latestSelection = false
const writeAudit = false

type bid struct {
    BidID, BidderID, SessionID, Channel, AmountCents, EventTS, Status, LotID string
    Used bool
}

type reversal struct {
    ReversalID, BidID, BidderID, SessionID, Channel, AmountCents, EventTS, Reason, LotID string
}

type window struct {
    SessionID, OpenTS, CloseTS, State string
}

type auditRow struct {
    Total, Matched, Unmatched, MatchedAmount, UnmatchedAmount int
}

func clean(s string) string {
    return strings.TrimSpace(s)
}

func up(s string) string {
    return strings.ToUpper(strings.TrimSpace(s))
}

func readCSV(path string) ([]map[string]string, error) {
    f, err := os.Open(path)
    if err != nil {
        return nil, err
    }
    defer f.Close()
    r := csv.NewReader(f)
    rows, err := r.ReadAll()
    if err != nil {
        return nil, err
    }
    if len(rows) == 0 {
        return nil, nil
    }
    header := rows[0]
    out := make([]map[string]string, 0, len(rows)-1)
    for _, row := range rows[1:] {
        m := map[string]string{}
        for i, name := range header {
            if i < len(row) {
                m[clean(name)] = clean(row[i])
            }
        }
        out = append(out, m)
    }
    return out, nil
}

func digits14(s string) bool {
    if len(s) != 14 {
        return false
    }
    for _, r := range s {
        if r < '0' || r > '9' {
            return false
        }
    }
    return true
}

func validAmount(s string) bool {
    if s == "" {
        return false
    }
    for _, r := range s {
        if r < '0' || r > '9' {
            return false
        }
    }
    amount, err := strconv.Atoi(s)
    return err == nil && amount > 0
}

func amountValue(s string) int {
    if !validAmount(s) {
        return 0
    }
    amount, _ := strconv.Atoi(s)
    return amount
}

func allowedChannel(s string) bool {
    return s == "ONLINE" || s == "MOBILE" || s == "ONSITE"
}

func staticAlias(s string) string {
    switch up(s) {
    case "WEB", "ONLINE":
        return "ONLINE"
    case "APP", "MOBILE":
        return "MOBILE"
    case "FLOOR", "ONSITE":
        return "ONSITE"
    default:
        return up(s)
    }
}

func loadAliases() map[string]string {
    aliases := map[string]string{"ONLINE": "ONLINE", "MOBILE": "MOBILE", "ONSITE": "ONSITE"}
    if aliasMode != "dynamic" {
        return aliases
    }
    rows, err := readCSV("/app/config/channel_aliases.csv")
    if err != nil {
        return aliases
    }
    for _, row := range rows {
        alias := up(row["alias"])
        canonical := up(row["canonical"])
        if alias == "" || !allowedChannel(canonical) {
            continue
        }
        aliases[alias] = canonical
    }
    return aliases
}

func canonicalChannel(s string, aliases map[string]string) string {
    raw := up(s)
    if aliasMode == "none" {
        return raw
    }
    if aliasMode == "static" {
        return staticAlias(raw)
    }
    if mapped, ok := aliases[raw]; ok {
        return mapped
    }
    return raw
}

func loadReasons() map[string]bool {
    if reasonMode != "dynamic" {
        return map[string]bool{"CANCEL": true, "FRAUD": true, "VOID": true}
    }
    reasons := map[string]bool{}
    rows, err := readCSV("/app/config/reversal_reasons.csv")
    if err != nil {
        return reasons
    }
    for _, row := range rows {
        reason := up(row["reason"])
        if reason == "" {
            continue
        }
        switch up(row["eligible"]) {
        case "Y", "YES", "TRUE", "1":
            reasons[reason] = true
        default:
            reasons[reason] = false
        }
    }
    return reasons
}

func eligibleReason(s string, reasons map[string]bool) bool {
    return reasons[up(s)]
}

func eligibleWindow(b bid, rev reversal, windows []window) bool {
    if !digits14(b.EventTS) || !digits14(rev.EventTS) {
        return false
    }
    for _, w := range windows {
        if w.SessionID != b.SessionID || up(w.State) != "OPEN" || !digits14(w.OpenTS) || !digits14(w.CloseTS) {
            continue
        }
        if b.EventTS >= w.OpenTS && b.EventTS <= w.CloseTS && rev.EventTS >= b.EventTS && rev.EventTS <= w.CloseTS {
            return true
        }
    }
    return false
}

func canMatch(b bid, rev reversal, windows []window, reasons map[string]bool) bool {
    if b.Used || b.BidID != rev.BidID || b.BidderID != rev.BidderID || b.SessionID != rev.SessionID || b.LotID != rev.LotID {
        return false
    }
    if !validAmount(b.AmountCents) || !validAmount(rev.AmountCents) || b.AmountCents != rev.AmountCents {
        return false
    }
    if up(b.Status) != "ACCEPTED" || !allowedChannel(b.Channel) || !allowedChannel(rev.Channel) || b.Channel != rev.Channel {
        return false
    }
    if !eligibleReason(rev.Reason, reasons) {
        return false
    }
    return eligibleWindow(b, rev, windows)
}

func auditKey(rev reversal) string {
    channel := rev.Channel
    if !allowedChannel(channel) {
        channel = "UNKNOWN"
    }
    return rev.SessionID + "||" + channel
}

func writeAuditFile(audit map[string]*auditRow) error {
    if !writeAudit {
        return nil
    }
    path := "/app/out/reversal_audit.csv"
    f, err := os.Create(path)
    if err != nil {
        return err
    }
    defer f.Close()
    w := csv.NewWriter(f)
    defer w.Flush()
    if err := w.Write([]string{"session_id", "channel", "total_reversals", "matched_count", "unmatched_count", "matched_amount_cents", "unmatched_amount_cents"}); err != nil {
        return err
    }
    keys := make([]string, 0, len(audit))
    for key := range audit {
        keys = append(keys, key)
    }
    sort.Strings(keys)
    for _, key := range keys {
        parts := strings.SplitN(key, "||", 2)
        row := audit[key]
        if err := w.Write([]string{
            parts[0], parts[1], strconv.Itoa(row.Total), strconv.Itoa(row.Matched), strconv.Itoa(row.Unmatched), strconv.Itoa(row.MatchedAmount), strconv.Itoa(row.UnmatchedAmount),
        }); err != nil {
            return err
        }
    }
    return nil
}

func main() {
    bidRows, err := readCSV("/app/data/bids.csv")
    if err != nil {
        panic(err)
    }
    reversalRows, err := readCSV("/app/data/reversals.csv")
    if err != nil {
        panic(err)
    }
    windowRows, err := readCSV("/app/config/session_windows.csv")
    if err != nil {
        panic(err)
    }
    aliases := loadAliases()
    reasons := loadReasons()

    bids := make([]bid, 0, len(bidRows))
    for _, row := range bidRows {
        bids = append(bids, bid{
            BidID: clean(row["bid_id"]), BidderID: clean(row["bidder_id"]), SessionID: clean(row["session_id"]), Channel: canonicalChannel(row["channel"], aliases),
            AmountCents: clean(row["amount_cents"]), EventTS: clean(row["event_ts"]), Status: clean(row["status"]), LotID: clean(row["lot_id"]),
        })
    }
    windows := make([]window, 0, len(windowRows))
    for _, row := range windowRows {
        windows = append(windows, window{SessionID: clean(row["session_id"]), OpenTS: clean(row["open_ts"]), CloseTS: clean(row["close_ts"]), State: clean(row["state"])})
    }

    os.MkdirAll("/app/out", 0755)
    report, err := os.Create("/app/out/reversal_report.csv")
    if err != nil {
        panic(err)
    }
    defer report.Close()
    writer := csv.NewWriter(report)
    defer writer.Flush()
    if err := writer.Write([]string{"reversal_id", "bid_id", "bidder_id", "session_id", "channel", "amount_cents", "reason", "status"}); err != nil {
        panic(err)
    }

    audit := map[string]*auditRow{}
    matchedCount, unmatchedCount := 0, 0
    matchedAmount, unmatchedAmount := 0, 0
    for _, row := range reversalRows {
        rev := reversal{
            ReversalID: clean(row["reversal_id"]), BidID: clean(row["bid_id"]), BidderID: clean(row["bidder_id"]), SessionID: clean(row["session_id"]),
            Channel: canonicalChannel(row["channel"], aliases), AmountCents: clean(row["amount_cents"]), EventTS: clean(row["event_ts"]), Reason: clean(row["reason"]), LotID: clean(row["lot_id"]),
        }
        matchIndex := -1
        for i := range bids {
            if !canMatch(bids[i], rev, windows, reasons) {
                continue
            }
            if matchIndex < 0 {
                matchIndex = i
                continue
            }
            if latestSelection && (bids[i].EventTS > bids[matchIndex].EventTS || (bids[i].EventTS == bids[matchIndex].EventTS && i < matchIndex)) {
                matchIndex = i
            }
        }
        amt := amountValue(rev.AmountCents)
        key := auditKey(rev)
        if _, ok := audit[key]; !ok {
            audit[key] = &auditRow{}
        }
        audit[key].Total++
        if matchIndex >= 0 {
            bids[matchIndex].Used = true
            matchedCount++
            matchedAmount += amt
            audit[key].Matched++
            audit[key].MatchedAmount += amt
            if err := writer.Write([]string{rev.ReversalID, rev.BidID, rev.BidderID, rev.SessionID, bids[matchIndex].Channel, rev.AmountCents, rev.Reason, "MATCHED"}); err != nil {
                panic(err)
            }
        } else {
            unmatchedCount++
            unmatchedAmount += amt
            audit[key].Unmatched++
            audit[key].UnmatchedAmount += amt
            if err := writer.Write([]string{rev.ReversalID, rev.BidID, rev.BidderID, rev.SessionID, "", rev.AmountCents, rev.Reason, "UNMATCHED"}); err != nil {
                panic(err)
            }
        }
    }
    summary := fmt.Sprintf("matched_count=%d\nmatched_amount_cents=%d\nunmatched_count=%d\nunmatched_amount_cents=%d\n", matchedCount, matchedAmount, unmatchedCount, unmatchedAmount)
    if err := os.WriteFile(filepath.Clean("/app/out/reversal_summary.txt"), []byte(summary), 0644); err != nil {
        panic(err)
    }
    if err := writeAuditFile(audit); err != nil {
        panic(err)
    }
}

GO
/app/scripts/run_batch.sh
