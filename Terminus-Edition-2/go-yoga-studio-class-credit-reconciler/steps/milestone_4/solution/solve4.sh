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

type Class struct{ ID, Member, Status, Access, VisitDate string; Amount int }
type Credit struct{ ClassID, Member, Access, CreditDate string; Amount int }
type Method struct{ Enabled bool; Priority int }
type Limit struct{ Member, Access, Effective string; Max, Row int }
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
	classRows, classHeaders, err := readTable("/app/data/classes.csv")
	if err != nil { return err }
	creditRows, creditHeaders, err := readTable("/app/data/credits.csv")
	if err != nil { return err }
	dated := has(classHeaders, "class_date") && has(creditHeaders, "credit_date")
	classes := loadClasses(classRows, dated)
	credits := loadCredits(creditRows, dated)
	methods, err := loadMethods("/app/config/methods.csv")
	if err != nil { return err }
	openDates := map[string]bool{}
	if dated {
		openDates, err = loadOpenDates("/app/config/cutoff_calendar.txt")
		if err != nil { return err }
	}
	limits := []Limit{}
	if dated { limits, _ = loadLimits("/app/config/member_limits.csv") }
	blackouts := []Blackout{}
	if dated { blackouts, _ = loadBlackouts("/app/config/blackouts.csv") }
	return writeOutputs(classes, credits, dated, openDates, methods, limits, blackouts)
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
			pr := ""
			if i < len(vals) { pr = vals[i] }
			m[clean(h)] = pr
		}
		out = append(out, m)
	}
	return out, headers, nil
}

func loadClasses(rows []map[string]string, dated bool) []Class {
	out := []Class{}
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row["amount_cents"])); if err != nil { continue }
		p := Class{ID: clean(row["class_id"]), Member: clean(row["member_id"]), Amount: amount, Status: strings.ToUpper(clean(row["status"])), Access: canon(row["class_type"])}
		if dated { p.VisitDate = clean(row["class_date"]) }
		out = append(out, p)
	}
	return out
}

func loadCredits(rows []map[string]string, dated bool) []Credit {
	out := []Credit{}
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row["amount_cents"])); if err != nil { continue }
		r := Credit{ClassID: clean(row["class_id"]), Member: clean(row["member_id"]), Amount: amount, Access: canon(row["class_type"])}
		if dated { r.CreditDate = clean(row["credit_date"]) }
		out = append(out, r)
	}
	return out
}

func loadMethods(path string) (map[string]Method, error) {
	rows, _, err := readTable(path); if err != nil { return nil, err }
	methods := map[string]Method{}
	for i, row := range rows {
		access := canon(row["class_type"])
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
		access := canon(row["class_type"])
		if !allowed(access) || !strings.EqualFold(clean(row["status"]), "ACTIVE") || !dateOK(row["effective_date"]) { continue }
		max, err := strconv.Atoi(clean(row["max_daily_amount"])); if err != nil { continue }
		out = append(out, Limit{Member: clean(row["member_id"]), Access: access, Effective: clean(row["effective_date"]), Max: max, Row: i})
	}
	return out, nil
}

func loadBlackouts(path string) ([]Blackout, error) {
	rows, _, err := readTable(path); if err != nil { return nil, err }
	out := []Blackout{}
	for _, row := range rows {
		access := canon(row["class_type"])
		if !allowed(access) || !strings.EqualFold(clean(row["state"]), "ACTIVE") || !dateOK(row["start_date"]) || !dateOK(row["end_date"]) { continue }
		start, end := clean(row["start_date"]), clean(row["end_date"])
		if start > end { continue }
		out = append(out, Blackout{Access: access, Start: start, End: end})
	}
	return out, nil
}

func writeOutputs(classes []Class, credits []Credit, dated bool, open map[string]bool, methods map[string]Method, limits []Limit, blackouts []Blackout) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil { return err }
	f, err := os.Create("/app/out/class_credit_report.csv"); if err != nil { return err }
	defer f.Close()
	w := csv.NewWriter(f); defer w.Flush()
	_ = w.Write([]string{"class_id", "member_id", "class_type", "amount_cents", "status"})
	used := make([]bool, len(classes))
	budget := map[string]int{}
	s := Summary{}
	for _, credit := range credits {
		idx := findMatch(classes, credit, used, dated, open, methods, limits, blackouts, budget)
		if idx >= 0 {
			used[idx] = true
			if dated { budget[budgetKey(credit, classes[idx].Access)] += credit.Amount }
			s.MatchedCount++; s.MatchedAmountCents += credit.Amount
			_ = w.Write([]string{credit.ClassID, credit.Member, classes[idx].Access, strconv.Itoa(credit.Amount), "MATCHED"})
		} else {
			s.UnmatchedCount++; s.UnmatchedAmountCents += credit.Amount
			_ = w.Write([]string{credit.ClassID, credit.Member, "", strconv.Itoa(credit.Amount), "UNMATCHED"})
		}
	}
	w.Flush(); if err := w.Error(); err != nil { return err }
	data, err := json.Marshal(s); if err != nil { return err }
	return os.WriteFile("/app/out/class_credit_summary.json", data, 0o644)
}

func findMatch(classes []Class, credit Credit, used []bool, dated bool, open map[string]bool, methods map[string]Method, limits []Limit, blackouts []Blackout, budget map[string]int) int {
	best := -1
	for i, class := range classes {
		if used[i] || !eligible(class, credit, dated, open, methods, limits, blackouts, budget) { continue }
		if best < 0 || better(class, classes[best], i, best, dated, methods) { best = i }
	}
	return best
}

func eligible(class Class, credit Credit, dated bool, open map[string]bool, methods map[string]Method, limits []Limit, blackouts []Blackout, budget map[string]int) bool {
	if class.ID != credit.ClassID || class.Member != credit.Member || class.Amount != credit.Amount || class.Status != "ACTIVE" || !methodEnabled(class.Access, methods) { return false }
	if credit.Access != "ANY" && (credit.Access != class.Access || !methodEnabled(credit.Access, methods)) { return false }
	if dated {
		if credit.CreditDate == "" || class.VisitDate == "" || !open[credit.CreditDate] || credit.CreditDate > class.VisitDate { return false }
		if blackedOut(class.Access, credit.CreditDate, blackouts) { return false }
		if len(limits) > 0 {
			limit := bestLimit(credit, class.Access, limits)
			if limit == nil || budget[budgetKey(credit, class.Access)]+credit.Amount > limit.Max { return false }
		}
	}
	return true
}

func better(class Class, best Class, classRow, bestRow int, dated bool, methods map[string]Method) bool {
	if dated && class.VisitDate != best.VisitDate { return class.VisitDate > best.VisitDate }
	pp, bp := priority(class.Access, methods), priority(best.Access, methods)
	if pp != bp { return pp < bp }
	return classRow < bestRow
}

func bestLimit(credit Credit, access string, limits []Limit) *Limit {
	var best *Limit
	for i := range limits {
		l := &limits[i]
		if l.Member != credit.Member || l.Access != access || l.Effective > credit.CreditDate { continue }
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

func budgetKey(credit Credit, access string) string { return credit.Member + "|" + access + "|" + credit.CreditDate }
func methodEnabled(access string, methods map[string]Method) bool { m, ok := methods[canon(access)]; return ok && m.Enabled }
func priority(access string, methods map[string]Method) int { if m, ok := methods[canon(access)]; ok { return m.Priority }; return 99999 }
func clean(pr string) string { return strings.TrimSpace(pr) }
func canon(pr string) string {
	switch strings.ToUpper(clean(pr)) {
	case "FL": return "FLOW"
	case "PW": return "POWER"
	case "PR": return "PRIVATE"
	default: return strings.ToUpper(clean(pr))
	}
}
func allowed(pr string) bool { pr = canon(pr); return pr == "FLOW" || pr == "POWER" || pr == "PRIVATE" }
func dateOK(pr string) bool { s := clean(pr); if len(s) != 10 { return false }; return s[4] == '-' && s[7] == '-' }
func has(headers []string, name string) bool { for _, h := range headers { if strings.EqualFold(clean(h), name) { return true } }; return false }
GO

/app/scripts/run_batch.sh
test -s /app/out/class_credit_report.csv
test -s /app/out/class_credit_summary.json
