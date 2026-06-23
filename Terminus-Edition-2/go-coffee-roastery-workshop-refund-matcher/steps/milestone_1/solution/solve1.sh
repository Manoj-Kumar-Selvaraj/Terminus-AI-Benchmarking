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

type Workshop struct{ ID, Attendee, Status, Access, VisitDate string; Amount int }
type Refund struct{ WorkshopID, Attendee, Access, RefundDate string; Amount int }
type Method struct{ Enabled bool; Priority int }
type Limit struct{ Attendee, Access, Effective string; Max, Row int }
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
	workshopRows, workshopHeaders, err := readTable("/app/data/workshops.csv")
	if err != nil { return err }
	refundRows, refundHeaders, err := readTable("/app/data/refunds.csv")
	if err != nil { return err }
	dated := has(workshopHeaders, "workshop_date") && has(refundHeaders, "refund_date")
	workshops := loadWorkshops(workshopRows, dated)
	refunds := loadRefunds(refundRows, dated)
	methods, err := loadMethods("/app/config/methods.csv")
	if err != nil { return err }
	openDates := map[string]bool{}
	if dated {
		openDates, err = loadOpenDates("/app/config/cutoff_calendar.txt")
		if err != nil { return err }
	}
	limits := []Limit{}
	if dated { limits, _ = loadLimits("/app/config/attendee_limits.csv") }
	blackouts := []Blackout{}
	if dated { blackouts, _ = loadBlackouts("/app/config/blackouts.csv") }
	return writeOutputs(workshops, refunds, dated, openDates, methods, limits, blackouts)
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
			cp := ""
			if i < len(vals) { cp = vals[i] }
			m[clean(h)] = cp
		}
		out = append(out, m)
	}
	return out, headers, nil
}

func loadWorkshops(rows []map[string]string, dated bool) []Workshop {
	out := []Workshop{}
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row["amount_cents"])); if err != nil { continue }
		p := Workshop{ID: clean(row["workshop_id"]), Attendee: clean(row["attendee_id"]), Amount: amount, Status: strings.ToUpper(clean(row["status"])), Access: canon(row["workshop_type"])}
		if dated { p.VisitDate = clean(row["workshop_date"]) }
		out = append(out, p)
	}
	return out
}

func loadRefunds(rows []map[string]string, dated bool) []Refund {
	out := []Refund{}
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row["amount_cents"])); if err != nil { continue }
		r := Refund{WorkshopID: clean(row["workshop_id"]), Attendee: clean(row["attendee_id"]), Amount: amount, Access: canon(row["workshop_type"])}
		if dated { r.RefundDate = clean(row["refund_date"]) }
		out = append(out, r)
	}
	return out
}

func loadMethods(path string) (map[string]Method, error) {
	rows, _, err := readTable(path); if err != nil { return nil, err }
	methods := map[string]Method{}
	for i, row := range rows {
		access := canon(row["workshop_type"])
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
		access := canon(row["workshop_type"])
		if !allowed(access) || !strings.EqualFold(clean(row["status"]), "ACTIVE") || !dateOK(row["effective_date"]) { continue }
		max, err := strconv.Atoi(clean(row["max_daily_amount"])); if err != nil { continue }
		out = append(out, Limit{Attendee: clean(row["attendee_id"]), Access: access, Effective: clean(row["effective_date"]), Max: max, Row: i})
	}
	return out, nil
}

func loadBlackouts(path string) ([]Blackout, error) {
	rows, _, err := readTable(path); if err != nil { return nil, err }
	out := []Blackout{}
	for _, row := range rows {
		access := canon(row["workshop_type"])
		if !allowed(access) || !strings.EqualFold(clean(row["state"]), "ACTIVE") || !dateOK(row["start_date"]) || !dateOK(row["end_date"]) { continue }
		start, end := clean(row["start_date"]), clean(row["end_date"])
		if start > end { continue }
		out = append(out, Blackout{Access: access, Start: start, End: end})
	}
	return out, nil
}

func writeOutputs(workshops []Workshop, refunds []Refund, dated bool, open map[string]bool, methods map[string]Method, limits []Limit, blackouts []Blackout) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil { return err }
	f, err := os.Create("/app/out/workshop_refund_report.csv"); if err != nil { return err }
	defer f.Close()
	w := csv.NewWriter(f); defer w.Flush()
	_ = w.Write([]string{"workshop_id", "attendee_id", "workshop_type", "amount_cents", "status"})
	used := make([]bool, len(workshops))
	budget := map[string]int{}
	s := Summary{}
	for _, refund := range refunds {
		idx := findMatch(workshops, refund, used, dated, open, methods, limits, blackouts, budget)
		if idx >= 0 {
			used[idx] = true
			if dated { budget[budgetKey(refund, workshops[idx].Access)] += refund.Amount }
			s.MatchedCount++; s.MatchedAmountCents += refund.Amount
			_ = w.Write([]string{refund.WorkshopID, refund.Attendee, workshops[idx].Access, strconv.Itoa(refund.Amount), "MATCHED"})
		} else {
			s.UnmatchedCount++; s.UnmatchedAmountCents += refund.Amount
			_ = w.Write([]string{refund.WorkshopID, refund.Attendee, "", strconv.Itoa(refund.Amount), "UNMATCHED"})
		}
	}
	w.Flush(); if err := w.Error(); err != nil { return err }
	data, err := json.Marshal(s); if err != nil { return err }
	return os.WriteFile("/app/out/workshop_refund_summary.json", data, 0o644)
}

func findMatch(workshops []Workshop, refund Refund, used []bool, dated bool, open map[string]bool, methods map[string]Method, limits []Limit, blackouts []Blackout, budget map[string]int) int {
	best := -1
	for i, workshop := range workshops {
		if used[i] || !eligible(workshop, refund, dated, open, methods, limits, blackouts, budget) { continue }
		if best < 0 || better(workshop, workshops[best], i, best, dated, methods) { best = i }
	}
	return best
}

func eligible(workshop Workshop, refund Refund, dated bool, open map[string]bool, methods map[string]Method, limits []Limit, blackouts []Blackout, budget map[string]int) bool {
	if workshop.ID != refund.WorkshopID || workshop.Attendee != refund.Attendee || workshop.Amount != refund.Amount || workshop.Status != "ACTIVE" || !methodEnabled(workshop.Access, methods) { return false }
	if refund.Access != "ANY" && (refund.Access != workshop.Access || !methodEnabled(refund.Access, methods)) { return false }
	if dated {
		if refund.RefundDate == "" || workshop.VisitDate == "" || !open[refund.RefundDate] || refund.RefundDate > workshop.VisitDate { return false }
		if blackedOut(workshop.Access, refund.RefundDate, blackouts) { return false }
		if len(limits) > 0 {
			limit := bestLimit(refund, workshop.Access, limits)
			if limit == nil || budget[budgetKey(refund, workshop.Access)]+refund.Amount > limit.Max { return false }
		}
	}
	return true
}

func better(workshop Workshop, best Workshop, workshopRow, bestRow int, dated bool, methods map[string]Method) bool {
	if dated && workshop.VisitDate != best.VisitDate { return workshop.VisitDate > best.VisitDate }
	pp, bp := priority(workshop.Access, methods), priority(best.Access, methods)
	if pp != bp { return pp < bp }
	return workshopRow < bestRow
}

func bestLimit(refund Refund, access string, limits []Limit) *Limit {
	var best *Limit
	for i := range limits {
		l := &limits[i]
		if l.Attendee != refund.Attendee || l.Access != access || l.Effective > refund.RefundDate { continue }
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

func budgetKey(refund Refund, access string) string { return refund.Attendee + "|" + access + "|" + refund.RefundDate }
func methodEnabled(access string, methods map[string]Method) bool { m, ok := methods[canon(access)]; return ok && m.Enabled }
func priority(access string, methods map[string]Method) int { if m, ok := methods[canon(access)]; ok { return m.Priority }; return 99999 }
func clean(cp string) string { return strings.TrimSpace(cp) }
func canon(cp string) string {
	switch strings.ToUpper(clean(cp)) {
	case "BW": return "BREW"
	case "RS": return "ROAST"
	case "CP": return "CUP"
	default: return strings.ToUpper(clean(cp))
	}
}
func allowed(cp string) bool { cp = canon(cp); return cp == "BREW" || cp == "ROAST" || cp == "CUP" }
func dateOK(cp string) bool { s := clean(cp); if len(s) != 10 { return false }; return s[4] == '-' && s[7] == '-' }
func has(headers []string, name string) bool { for _, h := range headers { if strings.EqualFold(clean(h), name) { return true } }; return false }
GO

/app/scripts/run_batch.sh
test -s /app/out/workshop_refund_report.csv
test -s /app/out/workshop_refund_summary.json
