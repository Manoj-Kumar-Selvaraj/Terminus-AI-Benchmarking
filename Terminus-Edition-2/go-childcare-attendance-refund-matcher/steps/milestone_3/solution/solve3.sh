#!/usr/bin/env bash
set -euo pipefail

mkdir -p /app/internal/billing /app/cmd/reconcile
cat > /app/cmd/reconcile/main.go <<'EOF'
package main

import (
    "fmt"
    "os"

    "childcare/internal/billing"
)

func main() {
    if err := billing.Run(); err != nil {
        fmt.Fprintln(os.Stderr, err)
        os.Exit(1)
    }
}
EOF

cat > /app/internal/billing/reconcile.go <<'EOF'
package billing

import (
    "encoding/csv"
    "encoding/json"
    "os"
    "path/filepath"
    "strconv"
    "strings"
    "time"
)

type Session struct {
    Row int
    ID string
    Guardian string
    Amount int
    AmountOK bool
    Status string
    Room string
    AttendanceRaw string
    Attendance time.Time
    AttendanceOK bool
}

type Refund struct {
    Row int
    SessionID string
    Guardian string
    AmountRaw string
    Amount int
    AmountOK bool
    Room string
    RefundDateRaw string
    RefundDate time.Time
    RefundDateOK bool
    Method string
    HasMethod bool
    SettlementRaw string
    Settlement time.Time
    SettlementOK bool
    HasSettlement bool
}

type Summary struct {
    MatchedCount int `json:"matched_count"`
    MatchedAmountCents int `json:"matched_amount_cents"`
    UnmatchedCount int `json:"unmatched_count"`
    UnmatchedAmountCents int `json:"unmatched_amount_cents"`
}

type table struct {
    header map[string]int
    rows [][]string
}

type methodRule struct {
    maxLag int
}

func Run() error {
    aliasMap := loadRoomAliases("/app/config/room_aliases.csv")
    sessionsTable, err := readTable("/app/data/sessions.csv")
    if err != nil { return err }
    refundsTable, err := readTable("/app/data/refunds.csv")
    if err != nil { return err }
    sessions := loadSessions(sessionsTable, aliasMap)
    refunds := loadRefunds(refundsTable, aliasMap)
    openDates := loadOpenDates("/app/config/cutoff_calendar.txt")
    methods := loadMethods("/app/config/methods.csv")
    dateGate := hasColumn(refundsTable, "refund_date") || hasColumn(sessionsTable, "attendance_date")
    methodGate := hasColumn(refundsTable, "refund_method")
    settlementGate := hasColumn(refundsTable, "settlement_date")
    return writeOutputs(sessions, refunds, openDates, methods, dateGate, methodGate, settlementGate)
}

func readTable(path string) (table, error) {
    f, err := os.Open(path)
    if err != nil { return table{}, err }
    defer f.Close()
    r := csv.NewReader(f)
    r.FieldsPerRecord = -1
    records, err := r.ReadAll()
    if err != nil { return table{}, err }
    t := table{header: map[string]int{}, rows: nil}
    if len(records) == 0 { return t, nil }
    for i, h := range records[0] {
        key := strings.ToLower(clean(h))
        if key != "" {
            if _, exists := t.header[key]; !exists { t.header[key] = i }
        }
    }
    if len(records) > 1 { t.rows = records[1:] }
    return t, nil
}

func hasColumn(t table, name string) bool {
    _, ok := t.header[strings.ToLower(name)]
    return ok
}

func field(t table, row []string, name string) string {
    idx, ok := t.header[strings.ToLower(name)]
    if !ok || idx < 0 || idx >= len(row) { return "" }
    return clean(row[idx])
}

func clean(v string) string { return strings.TrimSpace(v) }
func upper(v string) string { return strings.ToUpper(clean(v)) }

func parsePositiveCents(v string) (int, bool) {
    n, err := strconv.Atoi(clean(v))
    if err != nil || n <= 0 { return 0, false }
    return n, true
}

func parseDate(v string) (time.Time, bool) {
    s := clean(v)
    if s == "" { return time.Time{}, false }
    d, err := time.Parse("2006-01-02", s)
    if err != nil { return time.Time{}, false }
    return d, true
}

func canonicalIdentities() map[string]string {
    return map[string]string{"INFANT":"INFANT", "TODDLER":"TODDLER", "PREK":"PREK"}
}

func isCanonicalRoom(v string) bool {
    switch upper(v) {
    case "INFANT", "TODDLER", "PREK": return true
    default: return false
    }
}

func enabled(v string) bool {
    switch strings.ToLower(clean(v)) {
    case "true", "y", "yes", "1": return true
    default: return false
    }
}

func loadRoomAliases(path string) map[string]string {
    aliases := canonicalIdentities()
    t, err := readTable(path)
    if err != nil { return aliases }
    for _, row := range t.rows {
        alias := upper(field(t, row, "alias"))
        canon := upper(field(t, row, "canonical"))
        if alias == "" || !enabled(field(t, row, "enabled")) || !isCanonicalRoom(canon) { continue }
        if _, exists := aliases[alias]; !exists {
            aliases[alias] = canon
        }
    }
    return aliases
}

func canonicalRoom(raw string, aliases map[string]string) string {
    key := upper(raw)
    if key == "" { return "" }
    if canon, ok := aliases[key]; ok { return canon }
    return ""
}

func loadSessions(t table, aliases map[string]string) []Session {
    out := make([]Session, 0, len(t.rows))
    for i, row := range t.rows {
        amount, ok := parsePositiveCents(field(t, row, "amount_cents"))
        attendanceRaw := field(t, row, "attendance_date")
        attendance, attendanceOK := parseDate(attendanceRaw)
        out = append(out, Session{
            Row: i,
            ID: field(t, row, "session_id"),
            Guardian: field(t, row, "guardian_id"),
            Amount: amount,
            AmountOK: ok,
            Status: upper(field(t, row, "status")),
            Room: canonicalRoom(field(t, row, "room"), aliases),
            AttendanceRaw: attendanceRaw,
            Attendance: attendance,
            AttendanceOK: attendanceOK,
        })
    }
    return out
}

func loadRefunds(t table, aliases map[string]string) []Refund {
    out := make([]Refund, 0, len(t.rows))
    hasMethod := hasColumn(t, "refund_method")
    hasSettlement := hasColumn(t, "settlement_date")
    for i, row := range t.rows {
        rawAmount := field(t, row, "amount_cents")
        amount, ok := parsePositiveCents(rawAmount)
        refundDateRaw := field(t, row, "refund_date")
        refundDate, refundDateOK := parseDate(refundDateRaw)
        settlementRaw := field(t, row, "settlement_date")
        settlement, settlementOK := parseDate(settlementRaw)
        out = append(out, Refund{
            Row: i,
            SessionID: field(t, row, "session_id"),
            Guardian: field(t, row, "guardian_id"),
            AmountRaw: clean(rawAmount),
            Amount: amount,
            AmountOK: ok,
            Room: canonicalRoom(field(t, row, "room"), aliases),
            RefundDateRaw: refundDateRaw,
            RefundDate: refundDate,
            RefundDateOK: refundDateOK,
            Method: upper(field(t, row, "refund_method")),
            HasMethod: hasMethod,
            SettlementRaw: settlementRaw,
            Settlement: settlement,
            SettlementOK: settlementOK,
            HasSettlement: hasSettlement,
        })
    }
    return out
}

func loadOpenDates(path string) map[string]bool {
    data, err := os.ReadFile(path)
    if err != nil { return map[string]bool{} }
    open := map[string]bool{}
    for _, line := range strings.Split(string(data), "\n") {
        s := strings.TrimSpace(line)
        if s == "" || strings.HasPrefix(s, "#") { continue }
        parts := strings.Fields(s)
        if len(parts) < 2 { continue }
        if _, ok := parseDate(parts[0]); !ok { continue }
        if strings.EqualFold(clean(parts[1]), "open") { open[clean(parts[0])] = true }
    }
    return open
}

func loadMethods(path string) map[string]methodRule {
    methods := map[string]methodRule{}
    t, err := readTable(path)
    if err != nil { return methods }
    for _, row := range t.rows {
        method := upper(field(t, row, "method"))
        if method == "" { continue }
        if _, exists := methods[method]; exists { continue }
        // Record the first occurrence before checking validity so later duplicate rows cannot override it.
        methods[method] = methodRule{maxLag: -1}
        if !enabled(field(t, row, "enabled")) { continue }
        lagRaw := field(t, row, "max_lag_days")
        lag, err := strconv.Atoi(clean(lagRaw))
        if err != nil || lag < 0 { continue }
        methods[method] = methodRule{maxLag: lag}
    }
    return methods
}

func writeOutputs(sessions []Session, refunds []Refund, openDates map[string]bool, methods map[string]methodRule, dateGate, methodGate, settlementGate bool) error {
    if err := os.MkdirAll("/app/out", 0o755); err != nil { return err }
    reportPath := filepath.Join("/app/out", "refund_report.csv")
    reportFile, err := os.Create(reportPath)
    if err != nil { return err }
    defer reportFile.Close()
    w := csv.NewWriter(reportFile)
    if err := w.Write([]string{"session_id", "guardian_id", "room", "amount_cents", "status"}); err != nil { return err }
    used := make([]bool, len(sessions))
    summary := Summary{}
    for _, refund := range refunds {
        matchIdx := findMatch(sessions, used, refund, openDates, methods, dateGate, methodGate, settlementGate)
        room := ""
        status := "UNMATCHED"
        if matchIdx >= 0 {
            used[matchIdx] = true
            room = sessions[matchIdx].Room
            status = "MATCHED"
            summary.MatchedCount++
            summary.MatchedAmountCents += refund.Amount
        } else {
            summary.UnmatchedCount++
            if refund.AmountOK { summary.UnmatchedAmountCents += refund.Amount }
        }
        amountText := refund.AmountRaw
        if refund.AmountOK { amountText = strconv.Itoa(refund.Amount) }
        if err := w.Write([]string{refund.SessionID, refund.Guardian, room, amountText, status}); err != nil { return err }
    }
    w.Flush()
    if err := w.Error(); err != nil { return err }
    b, err := json.MarshalIndent(summary, "", "  ")
    if err != nil { return err }
    return os.WriteFile("/app/out/refund_summary.json", append(b, '\n'), 0o644)
}

func findMatch(sessions []Session, used []bool, refund Refund, openDates map[string]bool, methods map[string]methodRule, dateGate, methodGate, settlementGate bool) int {
    best := -1
    for i := range sessions {
        if used[i] || !basicMatch(sessions[i], refund) { continue }
        if dateGate && !dateEligible(sessions[i], refund, openDates) { continue }
        if methodGate && !methodEligible(refund, methods, settlementGate) { continue }
        if best == -1 { best = i; continue }
        if dateGate {
            if sessions[i].Attendance.After(sessions[best].Attendance) { best = i; continue }
            if sessions[i].Attendance.Equal(sessions[best].Attendance) && sessions[i].Row < sessions[best].Row { best = i; continue }
        }
    }
    return best
}

func basicMatch(session Session, refund Refund) bool {
    if session.ID == "" || refund.SessionID == "" || session.Guardian == "" || refund.Guardian == "" { return false }
    if !session.AmountOK || !refund.AmountOK { return false }
    if session.Status != "CHECKEDIN" { return false }
    if session.Room == "" || refund.Room == "" || session.Room != refund.Room { return false }
    return session.ID == refund.SessionID && session.Guardian == refund.Guardian && session.Amount == refund.Amount
}

func dateEligible(session Session, refund Refund, openDates map[string]bool) bool {
    if !refund.RefundDateOK || !session.AttendanceOK { return false }
    if !openDates[refund.RefundDate.Format("2006-01-02")] { return false }
    if refund.RefundDate.After(session.Attendance) { return false }
    return true
}

func methodEligible(refund Refund, methods map[string]methodRule, settlementGate bool) bool {
    if !refund.HasMethod || refund.Method == "" { return false }
    rule, ok := methods[refund.Method]
    if !ok || rule.maxLag < 0 { return false }
    if settlementGate {
        if !refund.SettlementOK || !refund.RefundDateOK { return false }
        if refund.Settlement.Before(refund.RefundDate) { return false }
        days := int(refund.Settlement.Sub(refund.RefundDate).Hours() / 24)
        if days > rule.maxLag { return false }
    }
    return true
}

EOF

rm -f /app/internal/billing/types.go /app/internal/billing/io.go /app/internal/billing/config.go /app/internal/billing/engine.go
/usr/local/go/bin/gofmt -w /app/cmd/reconcile/main.go /app/internal/billing/reconcile.go 2>/dev/null || gofmt -w /app/cmd/reconcile/main.go /app/internal/billing/reconcile.go
