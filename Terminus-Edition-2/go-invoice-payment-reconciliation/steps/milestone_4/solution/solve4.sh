#!/usr/bin/env bash
set -euo pipefail
cd /app
cat > /app/cmd/reconcile/main.go <<'GOEOF'
package main

import (
    "encoding/csv"
    "encoding/json"
    "fmt"
    "os"
    "path/filepath"
    "sort"
    "strconv"
    "strings"
    "time"
)

const featureLevel = 4

type Invoice struct {
    Row int
    ID string
    Customer string
    AmountRaw string
    Amount int
    AmountValid bool
    Status string
    Method string
    DueDate string
    DueDateValid bool
}

type Payment struct {
    Row int
    InvoiceID string
    Customer string
    AmountRaw string
    Amount int
    AmountValid bool
    Method string
    PaymentDate string
    PaymentDateValid bool
}

type Summary struct {
    MatchedCount int `json:"matched_count"`
    MatchedAmountCents int `json:"matched_amount_cents"`
    UnmatchedCount int `json:"unmatched_count"`
    UnmatchedAmountCents int `json:"unmatched_amount_cents"`
}

type MethodPolicy struct { Enabled bool; Priority int; Valid bool }
type LimitRow struct { Customer string; Method string; Max int; EffectiveDate string; Enabled bool; Row int }
type AuditBucket struct { Total, MatchedCount, UnmatchedCount, MatchedAmount, UnmatchedAmount int }
type Candidate struct { Index int; Invoice Invoice; Priority int }

func main() { if err := run(); err != nil { fmt.Fprintln(os.Stderr, err); os.Exit(1) } }

func run() error {
    invoices, err := loadInvoices("/app/data/invoices.csv")
    if err != nil { return err }
    payments, err := loadPayments("/app/data/payments.csv")
    if err != nil { return err }
    openDates := map[string]bool{}
    if featureLevel >= 3 {
        openDates, err = loadOpenDates("/app/config/cutoff_calendar.txt")
        if err != nil { return err }
    }
    methods := defaultMethods()
    limits := []LimitRow{}
    if featureLevel >= 4 {
        methods = loadMethods("/app/config/methods.csv")
        limits = loadLimits("/app/config/customer_limits.csv")
    }
    return writeOutputs(invoices, payments, openDates, methods, limits)
}

func loadInvoices(path string) ([]Invoice, error) {
    header, rows, err := readTable(path)
    if err != nil { return nil, err }
    out := []Invoice{}
    for i, row := range rows {
        inv := Invoice{Row: i, ID: field(row, header, "invoice_id"), Customer: field(row, header, "customer_id"), AmountRaw: field(row, header, "amount_cents"), Status: upper(field(row, header, "status")), Method: canonicalMethod(field(row, header, "method")), DueDate: field(row, header, "due_date")}
        inv.Amount, inv.AmountValid = parsePositiveInt(inv.AmountRaw)
        inv.DueDateValid = validDate(inv.DueDate)
        out = append(out, inv)
    }
    return out, nil
}

func loadPayments(path string) ([]Payment, error) {
    header, rows, err := readTable(path)
    if err != nil { return nil, err }
    out := []Payment{}
    for i, row := range rows {
        pay := Payment{Row: i, InvoiceID: field(row, header, "invoice_id"), Customer: field(row, header, "customer_id"), AmountRaw: field(row, header, "amount_cents"), Method: canonicalMethod(field(row, header, "method")), PaymentDate: field(row, header, "payment_date")}
        pay.Amount, pay.AmountValid = parsePositiveInt(pay.AmountRaw)
        pay.PaymentDateValid = validDate(pay.PaymentDate)
        out = append(out, pay)
    }
    return out, nil
}

func readTable(path string) (map[string]int, [][]string, error) {
    f, err := os.Open(path)
    if err != nil { return nil, nil, err }
    defer f.Close()
    r := csv.NewReader(f)
    r.FieldsPerRecord = -1
    all, err := r.ReadAll()
    if err != nil { return nil, nil, err }
    header := map[string]int{}
    if len(all) == 0 { return header, nil, nil }
    for i, h := range all[0] { header[clean(h)] = i }
    return header, all[1:], nil
}

func field(row []string, header map[string]int, name string) string { if i, ok := header[name]; ok && i < len(row) { return clean(row[i]) }; return "" }
func clean(s string) string { return strings.TrimSpace(s) }
func upper(s string) string { return strings.ToUpper(clean(s)) }

func canonicalMethod(s string) string {
    m := upper(s)
    if featureLevel >= 2 { if m == "CC" { return "CARD" }; if m == "WIR" { return "WIRE" } }
    return m
}

func parsePositiveInt(s string) (int, bool) {
    s = clean(s)
    if s == "" { return 0, false }
    for _, r := range s { if r < '0' || r > '9' { return 0, false } }
    n, err := strconv.Atoi(s)
    if err != nil || n <= 0 { return 0, false }
    return n, true
}

func validDate(s string) bool { if clean(s) == "" { return false }; _, err := time.Parse("2006-01-02", clean(s)); return err == nil }
func defaultMethods() map[string]MethodPolicy { return map[string]MethodPolicy{"ACH": {true, 2, true}, "CARD": {true, 1, true}, "WIRE": {true, 3, true}} }

func loadMethods(path string) map[string]MethodPolicy {
    policies := defaultMethods()
    header, rows, err := readTable(path)
    if err != nil { return policies }
    for _, row := range rows {
        method := canonicalMethod(field(row, header, "method"))
        if !baseAllowed(method) { continue }
        enabledRaw := upper(field(row, header, "enabled"))
        enabled := enabledRaw == "TRUE"
        priority, ok := parseNonNegativeInt(field(row, header, "priority"))
        if !ok { priority = 1000 }
        policies[method] = MethodPolicy{Enabled: enabled, Priority: priority, Valid: true}
    }
    return policies
}

func parseNonNegativeInt(s string) (int, bool) {
    s = clean(s)
    if s == "" { return 0, false }
    for _, r := range s { if r < '0' || r > '9' { return 0, false } }
    n, err := strconv.Atoi(s)
    if err != nil || n < 0 { return 0, false }
    return n, true
}

func loadLimits(path string) []LimitRow {
    header, rows, err := readTable(path)
    if err != nil { return nil }
    out := []LimitRow{}
    for i, row := range rows {
        max, ok := parseNonNegativeInt(field(row, header, "max_amount_cents"))
        eff := field(row, header, "effective_date")
        method := canonicalMethod(field(row, header, "method"))
        if !ok || !validDate(eff) || !baseAllowed(method) { continue }
        out = append(out, LimitRow{Customer: field(row, header, "customer_id"), Method: method, Max: max, EffectiveDate: eff, Enabled: strings.EqualFold(field(row, header, "enabled"), "true"), Row: i})
    }
    return out
}

func loadOpenDates(path string) (map[string]bool, error) {
    data, err := os.ReadFile(path)
    if err != nil { return nil, err }
    out := map[string]bool{}
    for _, line := range strings.Split(string(data), "\n") {
        fields := strings.Fields(line)
        if len(fields) >= 2 && validDate(fields[0]) { out[fields[0]] = strings.EqualFold(fields[1], "open") }
    }
    return out, nil
}

func baseAllowed(method string) bool { return method == "ACH" || method == "CARD" || method == "WIRE" }
func methodEnabled(method string, policies map[string]MethodPolicy) bool { p, ok := policies[method]; return ok && p.Valid && p.Enabled }
func methodPriority(method string, policies map[string]MethodPolicy) int { if p, ok := policies[method]; ok { return p.Priority }; return 1000 }

func writeOutputs(invoices []Invoice, payments []Payment, openDates map[string]bool, methods map[string]MethodPolicy, limits []LimitRow) error {
    if err := os.MkdirAll("/app/out", 0o755); err != nil { return err }
    reportPath := filepath.Join("/app/out", "payment_report.csv")
    reportFile, err := os.Create(reportPath)
    if err != nil { return err }
    defer reportFile.Close()
    writer := csv.NewWriter(reportFile)
    if err := writer.Write([]string{"invoice_id", "customer_id", "method", "amount_cents", "status"}); err != nil { return err }

    summary := Summary{}
    used := make([]bool, len(invoices))
    budget := map[string]int{}
    audit := map[string]*AuditBucket{}

    for _, payment := range payments {
        matchIndex := findMatch(invoices, payment, used, openDates, methods, limits, budget)
        status, method := "UNMATCHED", ""
        amountContribution := 0
        if payment.AmountValid { amountContribution = payment.Amount }
        auditGroup := payment.Method
        if auditGroup == "" { auditGroup = "UNKNOWN" }
        if matchIndex >= 0 {
            inv := invoices[matchIndex]
            used[matchIndex] = true
            status, method = "MATCHED", inv.Method
            summary.MatchedCount++
            summary.MatchedAmountCents += payment.Amount
            if featureLevel >= 4 { budget[budgetKey(payment.Customer, inv.Method, payment.PaymentDate)] += payment.Amount }
            auditGroup = inv.Method
            addAudit(audit, auditGroup, true, payment.Amount)
        } else {
            summary.UnmatchedCount++
            summary.UnmatchedAmountCents += amountContribution
            if featureLevel >= 4 { addAudit(audit, auditGroup, false, amountContribution) }
        }
        if err := writer.Write([]string{payment.InvoiceID, payment.Customer, method, payment.AmountRaw, status}); err != nil { return err }
    }
    writer.Flush()
    if err := writer.Error(); err != nil { return err }
    summaryBytes, err := json.MarshalIndent(summary, "", "  ")
    if err != nil { return err }
    if err := os.WriteFile("/app/out/payment_summary.json", append(summaryBytes, '\n'), 0o644); err != nil { return err }
    if featureLevel >= 4 { return writeAudit(audit) }
    return nil
}

func findMatch(invoices []Invoice, payment Payment, used []bool, openDates map[string]bool, methods map[string]MethodPolicy, limits []LimitRow, budget map[string]int) int {
    candidates := []Candidate{}
    for i, inv := range invoices {
        if used[i] || !eligibleBase(inv, payment) { continue }
        if featureLevel >= 3 && !eligibleDate(inv, payment, openDates) { continue }
        if featureLevel >= 4 && !methodEnabled(inv.Method, methods) { continue }
        if payment.Method == "ANY" {
            if featureLevel < 4 { continue }
        } else if inv.Method != payment.Method { continue }
        if featureLevel >= 4 && !withinLimit(inv, payment, limits, budget) { continue }
        candidates = append(candidates, Candidate{Index: i, Invoice: inv, Priority: methodPriority(inv.Method, methods)})
    }
    if len(candidates) == 0 { return -1 }
    if featureLevel < 3 { return candidates[0].Index }
    sort.SliceStable(candidates, func(a, b int) bool {
        ca, cb := candidates[a], candidates[b]
        if ca.Invoice.DueDate != cb.Invoice.DueDate { return ca.Invoice.DueDate > cb.Invoice.DueDate }
        if featureLevel >= 4 && ca.Priority != cb.Priority { return ca.Priority < cb.Priority }
        return ca.Index < cb.Index
    })
    return candidates[0].Index
}

func eligibleBase(inv Invoice, payment Payment) bool {
    if !payment.AmountValid || !inv.AmountValid { return false }
    if inv.ID != payment.InvoiceID || inv.Customer != payment.Customer || inv.Amount != payment.Amount { return false }
    if inv.Status != "POSTED" || !baseAllowed(inv.Method) { return false }
    if featureLevel < 4 && !baseAllowed(payment.Method) { return false }
    if featureLevel < 3 && inv.Method != payment.Method { return false }
    return true
}

func eligibleDate(inv Invoice, payment Payment, openDates map[string]bool) bool {
    if !payment.PaymentDateValid || !inv.DueDateValid { return false }
    if !openDates[payment.PaymentDate] { return false }
    return payment.PaymentDate <= inv.DueDate
}

func applicableLimit(inv Invoice, payment Payment, limits []LimitRow) (LimitRow, bool) {
    best := LimitRow{}
    found := false
    for _, lim := range limits {
        if !lim.Enabled || lim.Customer != payment.Customer || lim.Method != inv.Method { continue }
        if !validDate(payment.PaymentDate) || lim.EffectiveDate > payment.PaymentDate { continue }
        if !found || lim.EffectiveDate > best.EffectiveDate || (lim.EffectiveDate == best.EffectiveDate && lim.Row > best.Row) { best = lim; found = true }
    }
    return best, found
}

func withinLimit(inv Invoice, payment Payment, limits []LimitRow, budget map[string]int) bool {
    lim, ok := applicableLimit(inv, payment, limits)
    if !ok { return true }
    return budget[budgetKey(payment.Customer, inv.Method, payment.PaymentDate)] + payment.Amount <= lim.Max
}

func budgetKey(customer, method, date string) string { return customer + "\x00" + method + "\x00" + date }
func addAudit(audit map[string]*AuditBucket, group string, matched bool, amount int) { b := audit[group]; if b == nil { b = &AuditBucket{}; audit[group] = b }; b.Total++; if matched { b.MatchedCount++; b.MatchedAmount += amount } else { b.UnmatchedCount++; b.UnmatchedAmount += amount } }

func writeAudit(audit map[string]*AuditBucket) error {
    f, err := os.Create("/app/out/payment_audit.csv")
    if err != nil { return err }
    defer f.Close()
    w := csv.NewWriter(f)
    defer w.Flush()
    if err := w.Write([]string{"method", "total_payments", "matched_count", "unmatched_count", "matched_amount_cents", "unmatched_amount_cents"}); err != nil { return err }
    keys := []string{}
    for k := range audit { keys = append(keys, k) }
    rank := map[string]int{"ACH": 0, "CARD": 1, "WIRE": 2, "ANY": 3}
    sort.Slice(keys, func(i, j int) bool { ri, iok := rank[keys[i]]; rj, jok := rank[keys[j]]; if iok && jok { return ri < rj }; if iok { return true }; if jok { return false }; return keys[i] < keys[j] })
    for _, k := range keys { b := audit[k]; if err := w.Write([]string{k, strconv.Itoa(b.Total), strconv.Itoa(b.MatchedCount), strconv.Itoa(b.UnmatchedCount), strconv.Itoa(b.MatchedAmount), strconv.Itoa(b.UnmatchedAmount)}); err != nil { return err } }
    return w.Error()
}

GOEOF
/app/scripts/run_batch.sh
test -s /app/out/payment_report.csv
test -s /app/out/payment_summary.json
test -s /app/out/payment_audit.csv
