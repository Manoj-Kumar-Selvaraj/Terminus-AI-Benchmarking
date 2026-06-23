#!/usr/bin/env bash
set -euo pipefail

cd /app

cat > /app/cmd/reconcile/main.go <<'GO'
package main

import (
	"encoding/csv"
	"encoding/json"
	"os"
	"strconv"
	"strings"
)

type Pass struct{ ID, Guest, Status, Access, VisitDate string; Amount int }
type Refund struct{ PassID, Guest, Access, RefundDate string; Amount int }
type Method struct{ Enabled bool; Priority int }
type Limit struct{ Guest, Access, Effective string; Max, Row int }
type Blackout struct{ Access, Start, End string }
type Summary struct {
	MatchedCount         int `json:"matched_count"`
	MatchedAmountCents   int `json:"matched_amount_cents"`
	UnmatchedCount       int `json:"unmatched_count"`
	UnmatchedAmountCents int `json:"unmatched_amount_cents"`
}

func main() {
	if err := run(); err != nil {
		panic(err)
	}
}

func run() error {
	passRows, passHeaders, err := readTable("/app/data/passes.csv")
	if err != nil { return err }
	refundRows, refundHeaders, err := readTable("/app/data/refunds.csv")
	if err != nil { return err }
	dated := has(passHeaders, "visit_date") && has(refundHeaders, "refund_date")
	passes := loadPasses(passRows, dated)
	refunds := loadRefunds(refundRows, dated)
	methods, err := loadMethods("/app/config/methods.csv")
	if err != nil { return err }
	openDates := map[string]bool{}
	if dated {
		openDates, err = loadOpenDates("/app/config/cutoff_calendar.txt")
		if err != nil { return err }
	}
	limits := []Limit{}
	if dated { limits, _ = loadLimits("/app/config/guest_limits.csv") }
	blackouts := []Blackout{}
	if dated { blackouts, _ = loadBlackouts("/app/config/blackouts.csv") }
	return writeOutputs(passes, refunds, dated, openDates, methods, limits, blackouts)
}

func readTable(path string) ([]map[string]string, []string, error) {
	f, err := os.Open(path); if err != nil { return nil, nil, err }
	defer f.Close()
	r := csv.NewReader(f); r.FieldsPerRecord = -1
	rows, err := r.ReadAll(); if err != nil { return nil, nil, err }
	if len(rows) == 0 { return nil, nil, nil }
	headers := rows[0]
	out := []map[string]string{}
	for _, vals := range rows[1:] {
		m := map[string]string{}
		for i, h := range headers {
			v := ""
			if i < len(vals) { v = vals[i] }
			m[clean(h)] = v
		}
		out = append(out, m)
	}
	return out, headers, nil
}

func loadPasses(rows []map[string]string, dated bool) []Pass {
	out := []Pass{}
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row["amount_cents"])); if err != nil { continue }
		p := Pass{ID: clean(row["pass_id"]), Guest: clean(row["guest_id"]), Amount: amount, Status: strings.ToUpper(clean(row["status"])), Access: canon(row["access_type"])}
		if dated { p.VisitDate = clean(row["visit_date"]) }
		out = append(out, p)
	}
	return out
}

func loadRefunds(rows []map[string]string, dated bool) []Refund {
	out := []Refund{}
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row["amount_cents"])); if err != nil { continue }
		r := Refund{PassID: clean(row["pass_id"]), Guest: clean(row["guest_id"]), Amount: amount, Access: canon(row["access_type"])}
		if dated { r.RefundDate = clean(row["refund_date"]) }
		out = append(out, r)
	}
	return out
}

func loadMethods(path string) (map[string]Method, error) {
	rows, _, err := readTable(path); if err != nil { return nil, err }
	methods := map[string]Method{}
	for i, row := range rows {
		access := canon(row["access_type"])
		if !allowed(access) || access == "ANY" { continue }
		priority := 10000 + i
		if p, err := strconv.Atoi(clean(row["priority"])); err == nil { priority = p }
		methods[access] = Method{Enabled: strings.EqualFold(clean(row["enabled"]), "true"), Priority: priority}
	}
	return methods, nil
}

func loadOpenDates(path string) (map[string]bool, error) {
	data, err := os.ReadFile(path); if err != nil { return nil, err }
	dates := map[string]bool{}
	for _, line := range strings.Split(string(data), "\n") {
		fields := strings.Fields(line)
		if len(fields) >= 2 && strings.EqualFold(fields[1], "open") { dates[fields[0]] = true }
	}
	return dates, nil
}

func loadLimits(path string) ([]Limit, error) {
	rows, _, err := readTable(path); if err != nil { return nil, err }
	out := []Limit{}
	for i, row := range rows {
		access := canon(row["access_type"])
		if !allowed(access) || !strings.EqualFold(clean(row["status"]), "ACTIVE") || !dateOK(row["effective_date"]) { continue }
		max, err := strconv.Atoi(clean(row["max_daily_amount"])); if err != nil { continue }
		out = append(out, Limit{Guest: clean(row["guest_id"]), Access: access, Effective: clean(row["effective_date"]), Max: max, Row: i})
	}
	return out, nil
}

func loadBlackouts(path string) ([]Blackout, error) {
	rows, _, err := readTable(path); if err != nil { return nil, err }
	out := []Blackout{}
	for _, row := range rows {
		access := canon(row["access_type"])
		if !allowed(access) || !strings.EqualFold(clean(row["state"]), "ACTIVE") || !dateOK(row["start_date"]) || !dateOK(row["end_date"]) { continue }
		start, end := clean(row["start_date"]), clean(row["end_date"])
		if start > end { continue }
		out = append(out, Blackout{Access: access, Start: start, End: end})
	}
	return out, nil
}

func writeOutputs(passes []Pass, refunds []Refund, dated bool, open map[string]bool, methods map[string]Method, limits []Limit, blackouts []Blackout) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil { return err }
	f, err := os.Create("/app/out/refund_report.csv"); if err != nil { return err }
	defer f.Close()
	w := csv.NewWriter(f); defer w.Flush()
	_ = w.Write([]string{"pass_id", "guest_id", "access_type", "amount_cents", "status"})
	used := make([]bool, len(passes))
	budget := map[string]int{}
	s := Summary{}
	for _, refund := range refunds {
		idx := findMatch(passes, refund, used, dated, open, methods, limits, blackouts, budget)
		if idx >= 0 {
			used[idx] = true
			if dated { budget[budgetKey(refund, passes[idx].Access)] += refund.Amount }
			s.MatchedCount++; s.MatchedAmountCents += refund.Amount
			_ = w.Write([]string{refund.PassID, refund.Guest, passes[idx].Access, strconv.Itoa(refund.Amount), "MATCHED"})
		} else {
			s.UnmatchedCount++; s.UnmatchedAmountCents += refund.Amount
			_ = w.Write([]string{refund.PassID, refund.Guest, "", strconv.Itoa(refund.Amount), "UNMATCHED"})
		}
	}
	w.Flush(); if err := w.Error(); err != nil { return err }
	data, err := json.Marshal(s); if err != nil { return err }
	return os.WriteFile("/app/out/refund_summary.json", data, 0o644)
}

func findMatch(passes []Pass, refund Refund, used []bool, dated bool, open map[string]bool, methods map[string]Method, limits []Limit, blackouts []Blackout, budget map[string]int) int {
	best := -1
	for i, pass := range passes {
		if used[i] || !eligible(pass, refund, dated, open, methods, limits, blackouts, budget) { continue }
		if best < 0 || better(pass, passes[best], i, best, dated, methods) { best = i }
	}
	return best
}

func eligible(pass Pass, refund Refund, dated bool, open map[string]bool, methods map[string]Method, limits []Limit, blackouts []Blackout, budget map[string]int) bool {
	if pass.ID != refund.PassID || pass.Guest != refund.Guest || pass.Amount != refund.Amount || pass.Status != "ACTIVE" || !methodEnabled(pass.Access, methods) { return false }
	if refund.Access != "ANY" && (refund.Access != pass.Access || !methodEnabled(refund.Access, methods)) { return false }
	if dated {
		if refund.RefundDate == "" || pass.VisitDate == "" || !open[refund.RefundDate] || refund.RefundDate > pass.VisitDate { return false }
		if blackedOut(pass.Access, refund.RefundDate, blackouts) { return false }
		limit := bestLimit(refund, pass.Access, limits)
		if limit == nil || budget[budgetKey(refund, pass.Access)]+refund.Amount > limit.Max { return false }
	}
	return true
}

func better(pass Pass, best Pass, passRow, bestRow int, dated bool, methods map[string]Method) bool {
	if dated && pass.VisitDate != best.VisitDate { return pass.VisitDate > best.VisitDate }
	pp, bp := priority(pass.Access, methods), priority(best.Access, methods)
	if pp != bp { return pp < bp }
	return passRow < bestRow
}

func bestLimit(refund Refund, access string, limits []Limit) *Limit {
	var best *Limit
	for i := range limits {
		l := &limits[i]
		if l.Guest != refund.Guest || l.Access != access || l.Effective > refund.RefundDate { continue }
		if best == nil || l.Effective > best.Effective || (l.Effective == best.Effective && l.Row < best.Row) { best = l }
	}
	return best
}

func blackedOut(access, date string, rows []Blackout) bool {
	for _, row := range rows {
		if row.Access == access && row.Start <= date && date <= row.End { return true }
	}
	return false
}

func budgetKey(refund Refund, access string) string { return refund.Guest + "|" + access + "|" + refund.RefundDate }
func methodEnabled(access string, methods map[string]Method) bool { m, ok := methods[canon(access)]; return ok && m.Enabled }
func priority(access string, methods map[string]Method) int { if m, ok := methods[canon(access)]; ok { return m.Priority }; return 99999 }
func clean(v string) string { return strings.TrimSpace(v) }
func canon(v string) string {
	switch strings.ToUpper(clean(v)) {
	case "DY": return "DAY"
	case "SEA": return "SEASON"
	case "V": return "VIP"
	default: return strings.ToUpper(clean(v))
	}
}
func allowed(v string) bool { v = canon(v); return v == "DAY" || v == "SEASON" || v == "VIP" }
func dateOK(v string) bool { s := clean(v); if len(s) != 10 { return false }; return s[4] == '-' && s[7] == '-' }
func has(headers []string, name string) bool { for _, h := range headers { if strings.EqualFold(clean(h), name) { return true } }; return false }
GO

/app/scripts/run_batch.sh
test -s /app/out/refund_report.csv
test -s /app/out/refund_summary.json
