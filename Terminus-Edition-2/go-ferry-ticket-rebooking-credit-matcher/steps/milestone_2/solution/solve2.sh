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

type Ticket struct{ ID, Rider, Status, Access, VisitDate string; Amount int }
type Credit struct{ TicketID, Rider, Access, CreditDate string; Amount int }
type Method struct{ Enabled bool; Priority int }
type Limit struct{ Rider, Access, Effective string; Max, Row int }
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
	ticketRows, ticketHeaders, err := readTable("/app/data/tickets.csv")
	if err != nil { return err }
	creditRows, creditHeaders, err := readTable("/app/data/credits.csv")
	if err != nil { return err }
	dated := has(ticketHeaders, "travel_date") && has(creditHeaders, "credit_date")
	tickets := loadTickets(ticketRows, dated)
	credits := loadCredits(creditRows, dated)
	methods, err := loadMethods("/app/config/methods.csv")
	if err != nil { return err }
	openDates := map[string]bool{}
	if dated {
		openDates, err = loadOpenDates("/app/config/cutoff_calendar.txt")
		if err != nil { return err }
	}
	limits := []Limit{}
	if dated { limits, _ = loadLimits("/app/config/rider_limits.csv") }
	blackouts := []Blackout{}
	if dated { blackouts, _ = loadBlackouts("/app/config/blackouts.csv") }
	return writeOutputs(tickets, credits, dated, openDates, methods, limits, blackouts)
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
			cb := ""
			if i < len(vals) { cb = vals[i] }
			m[clean(h)] = cb
		}
		out = append(out, m)
	}
	return out, headers, nil
}

func loadTickets(rows []map[string]string, dated bool) []Ticket {
	out := []Ticket{}
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row["amount_cents"])); if err != nil { continue }
		p := Ticket{ID: clean(row["ticket_id"]), Rider: clean(row["rider_id"]), Amount: amount, Status: strings.ToUpper(clean(row["status"])), Access: canon(row["fare_type"])}
		if dated { p.VisitDate = clean(row["travel_date"]) }
		out = append(out, p)
	}
	return out
}

func loadCredits(rows []map[string]string, dated bool) []Credit {
	out := []Credit{}
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row["amount_cents"])); if err != nil { continue }
		r := Credit{TicketID: clean(row["ticket_id"]), Rider: clean(row["rider_id"]), Amount: amount, Access: canon(row["fare_type"])}
		if dated { r.CreditDate = clean(row["credit_date"]) }
		out = append(out, r)
	}
	return out
}

func loadMethods(path string) (map[string]Method, error) {
	rows, _, err := readTable(path); if err != nil { return nil, err }
	methods := map[string]Method{}
	for i, row := range rows {
		access := canon(row["fare_type"])
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
		access := canon(row["fare_type"])
		if !allowed(access) || !strings.EqualFold(clean(row["status"]), "ACTIVE") || !dateOK(row["effective_date"]) { continue }
		max, err := strconv.Atoi(clean(row["max_daily_amount"])); if err != nil { continue }
		out = append(out, Limit{Rider: clean(row["rider_id"]), Access: access, Effective: clean(row["effective_date"]), Max: max, Row: i})
	}
	return out, nil
}

func loadBlackouts(path string) ([]Blackout, error) {
	rows, _, err := readTable(path); if err != nil { return nil, err }
	out := []Blackout{}
	for _, row := range rows {
		access := canon(row["fare_type"])
		if !allowed(access) || !strings.EqualFold(clean(row["state"]), "ACTIVE") || !dateOK(row["start_date"]) || !dateOK(row["end_date"]) { continue }
		start, end := clean(row["start_date"]), clean(row["end_date"])
		if start > end { continue }
		out = append(out, Blackout{Access: access, Start: start, End: end})
	}
	return out, nil
}

func writeOutputs(tickets []Ticket, credits []Credit, dated bool, open map[string]bool, methods map[string]Method, limits []Limit, blackouts []Blackout) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil { return err }
	f, err := os.Create("/app/out/ticket_credit_report.csv"); if err != nil { return err }
	defer f.Close()
	w := csv.NewWriter(f); defer w.Flush()
	_ = w.Write([]string{"ticket_id", "rider_id", "fare_type", "amount_cents", "status"})
	used := make([]bool, len(tickets))
	budget := map[string]int{}
	s := Summary{}
	for _, credit := range credits {
		idx := findMatch(tickets, credit, used, dated, open, methods, limits, blackouts, budget)
		if idx >= 0 {
			used[idx] = true
			if dated { budget[budgetKey(credit, tickets[idx].Access)] += credit.Amount }
			s.MatchedCount++; s.MatchedAmountCents += credit.Amount
			_ = w.Write([]string{credit.TicketID, credit.Rider, tickets[idx].Access, strconv.Itoa(credit.Amount), "MATCHED"})
		} else {
			s.UnmatchedCount++; s.UnmatchedAmountCents += credit.Amount
			_ = w.Write([]string{credit.TicketID, credit.Rider, "", strconv.Itoa(credit.Amount), "UNMATCHED"})
		}
	}
	w.Flush(); if err := w.Error(); err != nil { return err }
	data, err := json.Marshal(s); if err != nil { return err }
	return os.WriteFile("/app/out/ticket_credit_summary.json", data, 0o644)
}

func findMatch(tickets []Ticket, credit Credit, used []bool, dated bool, open map[string]bool, methods map[string]Method, limits []Limit, blackouts []Blackout, budget map[string]int) int {
	best := -1
	for i, ticket := range tickets {
		if used[i] || !eligible(ticket, credit, dated, open, methods, limits, blackouts, budget) { continue }
		if best < 0 || better(ticket, tickets[best], i, best, dated, methods) { best = i }
	}
	return best
}

func eligible(ticket Ticket, credit Credit, dated bool, open map[string]bool, methods map[string]Method, limits []Limit, blackouts []Blackout, budget map[string]int) bool {
	if ticket.ID != credit.TicketID || ticket.Rider != credit.Rider || ticket.Amount != credit.Amount || ticket.Status != "ACTIVE" || !methodEnabled(ticket.Access, methods) { return false }
	if credit.Access != "ANY" && (credit.Access != ticket.Access || !methodEnabled(credit.Access, methods)) { return false }
	if dated {
		if credit.CreditDate == "" || ticket.VisitDate == "" || !open[credit.CreditDate] || credit.CreditDate > ticket.VisitDate { return false }
		if blackedOut(ticket.Access, credit.CreditDate, blackouts) { return false }
		if len(limits) > 0 {
			limit := bestLimit(credit, ticket.Access, limits)
			if limit == nil || budget[budgetKey(credit, ticket.Access)]+credit.Amount > limit.Max { return false }
		}
	}
	return true
}

func better(ticket Ticket, best Ticket, ticketRow, bestRow int, dated bool, methods map[string]Method) bool {
	if dated && ticket.VisitDate != best.VisitDate { return ticket.VisitDate > best.VisitDate }
	pp, bp := priority(ticket.Access, methods), priority(best.Access, methods)
	if pp != bp { return pp < bp }
	return ticketRow < bestRow
}

func bestLimit(credit Credit, access string, limits []Limit) *Limit {
	var best *Limit
	for i := range limits {
		l := &limits[i]
		if l.Rider != credit.Rider || l.Access != access || l.Effective > credit.CreditDate { continue }
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

func budgetKey(credit Credit, access string) string { return credit.Rider + "|" + access + "|" + credit.CreditDate }
func methodEnabled(access string, methods map[string]Method) bool { m, ok := methods[canon(access)]; return ok && m.Enabled }
func priority(access string, methods map[string]Method) int { if m, ok := methods[canon(access)]; ok { return m.Priority }; return 99999 }
func clean(cb string) string { return strings.TrimSpace(cb) }
func canon(cb string) string {
	switch strings.ToUpper(clean(cb)) {
	case "EC": return "ECON"
	case "BK": return "BIKE"
	case "CB": return "CABIN"
	default: return strings.ToUpper(clean(cb))
	}
}
func allowed(cb string) bool { cb = canon(cb); return cb == "ECON" || cb == "BIKE" || cb == "CABIN" }
func dateOK(cb string) bool { s := clean(cb); if len(s) != 10 { return false }; return s[4] == '-' && s[7] == '-' }
func has(headers []string, name string) bool { for _, h := range headers { if strings.EqualFold(clean(h), name) { return true } }; return false }
GO

/app/scripts/run_batch.sh
test -s /app/out/ticket_credit_report.csv
test -s /app/out/ticket_credit_summary.json
