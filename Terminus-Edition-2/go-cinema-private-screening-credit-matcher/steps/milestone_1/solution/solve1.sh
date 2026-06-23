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

type Screening struct{ ID, Host, Status, Access, VisitDate string; Amount int }
type Credit struct{ ScreeningID, Host, Access, CreditDate string; Amount int }
type Method struct{ Enabled bool; Priority int }
type Limit struct{ Host, Access, Effective string; Max, Row int }
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
	screeningRows, screeningHeaders, err := readTable("/app/data/screenings.csv")
	if err != nil { return err }
	creditRows, creditHeaders, err := readTable("/app/data/credits.csv")
	if err != nil { return err }
	dated := has(screeningHeaders, "screening_date") && has(creditHeaders, "credit_date")
	screenings := loadScreenings(screeningRows, dated)
	credits := loadCredits(creditRows, dated)
	methods, err := loadMethods("/app/config/methods.csv")
	if err != nil { return err }
	openDates := map[string]bool{}
	if dated {
		openDates, err = loadOpenDates("/app/config/cutoff_calendar.txt")
		if err != nil { return err }
	}
	limits := []Limit{}
	if dated { limits, _ = loadLimits("/app/config/host_limits.csv") }
	blackouts := []Blackout{}
	if dated { blackouts, _ = loadBlackouts("/app/config/blackouts.csv") }
	return writeOutputs(screenings, credits, dated, openDates, methods, limits, blackouts)
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
			ix := ""
			if i < len(vals) { ix = vals[i] }
			m[clean(h)] = ix
		}
		out = append(out, m)
	}
	return out, headers, nil
}

func loadScreenings(rows []map[string]string, dated bool) []Screening {
	out := []Screening{}
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row["amount_cents"])); if err != nil { continue }
		p := Screening{ID: clean(row["screening_id"]), Host: clean(row["host_id"]), Amount: amount, Status: strings.ToUpper(clean(row["status"])), Access: canon(row["screen_type"])}
		if dated { p.VisitDate = clean(row["screening_date"]) }
		out = append(out, p)
	}
	return out
}

func loadCredits(rows []map[string]string, dated bool) []Credit {
	out := []Credit{}
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row["amount_cents"])); if err != nil { continue }
		r := Credit{ScreeningID: clean(row["screening_id"]), Host: clean(row["host_id"]), Amount: amount, Access: canon(row["screen_type"])}
		if dated { r.CreditDate = clean(row["credit_date"]) }
		out = append(out, r)
	}
	return out
}

func loadMethods(path string) (map[string]Method, error) {
	rows, _, err := readTable(path); if err != nil { return nil, err }
	methods := map[string]Method{}
	for i, row := range rows {
		access := canon(row["screen_type"])
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
		access := canon(row["screen_type"])
		if !allowed(access) || !strings.EqualFold(clean(row["status"]), "ACTIVE") || !dateOK(row["effective_date"]) { continue }
		max, err := strconv.Atoi(clean(row["max_daily_amount"])); if err != nil { continue }
		out = append(out, Limit{Host: clean(row["host_id"]), Access: access, Effective: clean(row["effective_date"]), Max: max, Row: i})
	}
	return out, nil
}

func loadBlackouts(path string) ([]Blackout, error) {
	rows, _, err := readTable(path); if err != nil { return nil, err }
	out := []Blackout{}
	for _, row := range rows {
		access := canon(row["screen_type"])
		if !allowed(access) || !strings.EqualFold(clean(row["state"]), "ACTIVE") || !dateOK(row["start_date"]) || !dateOK(row["end_date"]) { continue }
		start, end := clean(row["start_date"]), clean(row["end_date"])
		if start > end { continue }
		out = append(out, Blackout{Access: access, Start: start, End: end})
	}
	return out, nil
}

func writeOutputs(screenings []Screening, credits []Credit, dated bool, open map[string]bool, methods map[string]Method, limits []Limit, blackouts []Blackout) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil { return err }
	f, err := os.Create("/app/out/screening_credit_report.csv"); if err != nil { return err }
	defer f.Close()
	w := csv.NewWriter(f); defer w.Flush()
	_ = w.Write([]string{"screening_id", "host_id", "screen_type", "amount_cents", "status"})
	used := make([]bool, len(screenings))
	budget := map[string]int{}
	s := Summary{}
	for _, credit := range credits {
		idx := findMatch(screenings, credit, used, dated, open, methods, limits, blackouts, budget)
		if idx >= 0 {
			used[idx] = true
			if dated { budget[budgetKey(credit, screenings[idx].Access)] += credit.Amount }
			s.MatchedCount++; s.MatchedAmountCents += credit.Amount
			_ = w.Write([]string{credit.ScreeningID, credit.Host, screenings[idx].Access, strconv.Itoa(credit.Amount), "MATCHED"})
		} else {
			s.UnmatchedCount++; s.UnmatchedAmountCents += credit.Amount
			_ = w.Write([]string{credit.ScreeningID, credit.Host, "", strconv.Itoa(credit.Amount), "UNMATCHED"})
		}
	}
	w.Flush(); if err := w.Error(); err != nil { return err }
	data, err := json.Marshal(s); if err != nil { return err }
	return os.WriteFile("/app/out/screening_credit_summary.json", data, 0o644)
}

func findMatch(screenings []Screening, credit Credit, used []bool, dated bool, open map[string]bool, methods map[string]Method, limits []Limit, blackouts []Blackout, budget map[string]int) int {
	best := -1
	for i, screening := range screenings {
		if used[i] || !eligible(screening, credit, dated, open, methods, limits, blackouts, budget) { continue }
		if best < 0 || better(screening, screenings[best], i, best, dated, methods) { best = i }
	}
	return best
}

func eligible(screening Screening, credit Credit, dated bool, open map[string]bool, methods map[string]Method, limits []Limit, blackouts []Blackout, budget map[string]int) bool {
	if screening.ID != credit.ScreeningID || screening.Host != credit.Host || screening.Amount != credit.Amount || screening.Status != "ACTIVE" || !methodEnabled(screening.Access, methods) { return false }
	if credit.Access != "ANY" && (credit.Access != screening.Access || !methodEnabled(credit.Access, methods)) { return false }
	if dated {
		if credit.CreditDate == "" || screening.VisitDate == "" || !open[credit.CreditDate] || credit.CreditDate > screening.VisitDate { return false }
		if blackedOut(screening.Access, credit.CreditDate, blackouts) { return false }
		if len(limits) > 0 {
			limit := bestLimit(credit, screening.Access, limits)
			if limit == nil || budget[budgetKey(credit, screening.Access)]+credit.Amount > limit.Max { return false }
		}
	}
	return true
}

func better(screening Screening, best Screening, screeningRow, bestRow int, dated bool, methods map[string]Method) bool {
	if dated && screening.VisitDate != best.VisitDate { return screening.VisitDate > best.VisitDate }
	pp, bp := priority(screening.Access, methods), priority(best.Access, methods)
	if pp != bp { return pp < bp }
	return screeningRow < bestRow
}

func bestLimit(credit Credit, access string, limits []Limit) *Limit {
	var best *Limit
	for i := range limits {
		l := &limits[i]
		if l.Host != credit.Host || l.Access != access || l.Effective > credit.CreditDate { continue }
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

func budgetKey(credit Credit, access string) string { return credit.Host + "|" + access + "|" + credit.CreditDate }
func methodEnabled(access string, methods map[string]Method) bool { m, ok := methods[canon(access)]; return ok && m.Enabled }
func priority(access string, methods map[string]Method) int { if m, ok := methods[canon(access)]; ok { return m.Priority }; return 99999 }
func clean(ix string) string { return strings.TrimSpace(ix) }
func canon(ix string) string {
	switch strings.ToUpper(clean(ix)) {
	case "SM": return "SMALL"
	case "PM": return "PREM"
	case "IX": return "IMAX"
	default: return strings.ToUpper(clean(ix))
	}
}
func allowed(ix string) bool { ix = canon(ix); return ix == "SMALL" || ix == "PREM" || ix == "IMAX" }
func dateOK(ix string) bool { s := clean(ix); if len(s) != 10 { return false }; return s[4] == '-' && s[7] == '-' }
func has(headers []string, name string) bool { for _, h := range headers { if strings.EqualFold(clean(h), name) { return true } }; return false }
GO

/app/scripts/run_batch.sh
test -s /app/out/screening_credit_report.csv
test -s /app/out/screening_credit_summary.json
