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

type Booking struct{ ID, Dancer, Status, Access, VisitDate string; Amount int }
type Credit struct{ BookingID, Dancer, Access, CreditDate string; Amount int }
type Method struct{ Enabled bool; Priority int }
type Limit struct{ Dancer, Access, Effective string; Max, Row int }
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
	bookingRows, bookingHeaders, err := readTable("/app/data/bookings.csv")
	if err != nil { return err }
	creditRows, creditHeaders, err := readTable("/app/data/credits.csv")
	if err != nil { return err }
	dated := has(bookingHeaders, "recital_date") && has(creditHeaders, "credit_date")
	bookings := loadBookings(bookingRows, dated)
	credits := loadCredits(creditRows, dated)
	methods, err := loadMethods("/app/config/methods.csv")
	if err != nil { return err }
	openDates := map[string]bool{}
	if dated {
		openDates, err = loadOpenDates("/app/config/cutoff_calendar.txt")
		if err != nil { return err }
	}
	limits := []Limit{}
	if dated { limits, _ = loadLimits("/app/config/dancer_limits.csv") }
	blackouts := []Blackout{}
	if dated { blackouts, _ = loadBlackouts("/app/config/blackouts.csv") }
	return writeOutputs(bookings, credits, dated, openDates, methods, limits, blackouts)
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
			st := ""
			if i < len(vals) { st = vals[i] }
			m[clean(h)] = st
		}
		out = append(out, m)
	}
	return out, headers, nil
}

func loadBookings(rows []map[string]string, dated bool) []Booking {
	out := []Booking{}
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row["amount_cents"])); if err != nil { continue }
		p := Booking{ID: clean(row["booking_id"]), Dancer: clean(row["dancer_id"]), Amount: amount, Status: strings.ToUpper(clean(row["status"])), Access: canon(row["recital_type"])}
		if dated { p.VisitDate = clean(row["recital_date"]) }
		out = append(out, p)
	}
	return out
}

func loadCredits(rows []map[string]string, dated bool) []Credit {
	out := []Credit{}
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row["amount_cents"])); if err != nil { continue }
		r := Credit{BookingID: clean(row["booking_id"]), Dancer: clean(row["dancer_id"]), Amount: amount, Access: canon(row["recital_type"])}
		if dated { r.CreditDate = clean(row["credit_date"]) }
		out = append(out, r)
	}
	return out
}

func loadMethods(path string) (map[string]Method, error) {
	rows, _, err := readTable(path); if err != nil { return nil, err }
	methods := map[string]Method{}
	for i, row := range rows {
		access := canon(row["recital_type"])
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
		access := canon(row["recital_type"])
		if !allowed(access) || !strings.EqualFold(clean(row["status"]), "ACTIVE") || !dateOK(row["effective_date"]) { continue }
		max, err := strconv.Atoi(clean(row["max_daily_amount"])); if err != nil { continue }
		out = append(out, Limit{Dancer: clean(row["dancer_id"]), Access: access, Effective: clean(row["effective_date"]), Max: max, Row: i})
	}
	return out, nil
}

func loadBlackouts(path string) ([]Blackout, error) {
	rows, _, err := readTable(path); if err != nil { return nil, err }
	out := []Blackout{}
	for _, row := range rows {
		access := canon(row["recital_type"])
		if !allowed(access) || !strings.EqualFold(clean(row["state"]), "ACTIVE") || !dateOK(row["start_date"]) || !dateOK(row["end_date"]) { continue }
		start, end := clean(row["start_date"]), clean(row["end_date"])
		if start > end { continue }
		out = append(out, Blackout{Access: access, Start: start, End: end})
	}
	return out, nil
}

func writeOutputs(bookings []Booking, credits []Credit, dated bool, open map[string]bool, methods map[string]Method, limits []Limit, blackouts []Blackout) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil { return err }
	f, err := os.Create("/app/out/recital_credit_report.csv"); if err != nil { return err }
	defer f.Close()
	w := csv.NewWriter(f); defer w.Flush()
	_ = w.Write([]string{"booking_id", "dancer_id", "recital_type", "amount_cents", "status"})
	used := make([]bool, len(bookings))
	budget := map[string]int{}
	s := Summary{}
	for _, credit := range credits {
		idx := findMatch(bookings, credit, used, dated, open, methods, limits, blackouts, budget)
		if idx >= 0 {
			used[idx] = true
			if dated { budget[budgetKey(credit, bookings[idx].Access)] += credit.Amount }
			s.MatchedCount++; s.MatchedAmountCents += credit.Amount
			_ = w.Write([]string{credit.BookingID, credit.Dancer, bookings[idx].Access, strconv.Itoa(credit.Amount), "MATCHED"})
		} else {
			s.UnmatchedCount++; s.UnmatchedAmountCents += credit.Amount
			_ = w.Write([]string{credit.BookingID, credit.Dancer, "", strconv.Itoa(credit.Amount), "UNMATCHED"})
		}
	}
	w.Flush(); if err := w.Error(); err != nil { return err }
	data, err := json.Marshal(s); if err != nil { return err }
	return os.WriteFile("/app/out/recital_credit_summary.json", data, 0o644)
}

func findMatch(bookings []Booking, credit Credit, used []bool, dated bool, open map[string]bool, methods map[string]Method, limits []Limit, blackouts []Blackout, budget map[string]int) int {
	best := -1
	for i, booking := range bookings {
		if used[i] || !eligible(booking, credit, dated, open, methods, limits, blackouts, budget) { continue }
		if best < 0 || better(booking, bookings[best], i, best, dated, methods) { best = i }
	}
	return best
}

func eligible(booking Booking, credit Credit, dated bool, open map[string]bool, methods map[string]Method, limits []Limit, blackouts []Blackout, budget map[string]int) bool {
	if booking.ID != credit.BookingID || booking.Dancer != credit.Dancer || booking.Amount != credit.Amount || booking.Status != "ACTIVE" || !methodEnabled(booking.Access, methods) { return false }
	if credit.Access != "ANY" && (credit.Access != booking.Access || !methodEnabled(credit.Access, methods)) { return false }
	if dated {
		if credit.CreditDate == "" || booking.VisitDate == "" || !open[credit.CreditDate] || credit.CreditDate > booking.VisitDate { return false }
		if blackedOut(booking.Access, credit.CreditDate, blackouts) { return false }
		if len(limits) > 0 {
			limit := bestLimit(credit, booking.Access, limits)
			if limit == nil || budget[budgetKey(credit, booking.Access)]+credit.Amount > limit.Max { return false }
		}
	}
	return true
}

func better(booking Booking, best Booking, bookingRow, bestRow int, dated bool, methods map[string]Method) bool {
	if dated && booking.VisitDate != best.VisitDate { return booking.VisitDate > best.VisitDate }
	pp, bp := priority(booking.Access, methods), priority(best.Access, methods)
	if pp != bp { return pp < bp }
	return bookingRow < bestRow
}

func bestLimit(credit Credit, access string, limits []Limit) *Limit {
	var best *Limit
	for i := range limits {
		l := &limits[i]
		if l.Dancer != credit.Dancer || l.Access != access || l.Effective > credit.CreditDate { continue }
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

func budgetKey(credit Credit, access string) string { return credit.Dancer + "|" + access + "|" + credit.CreditDate }
func methodEnabled(access string, methods map[string]Method) bool { m, ok := methods[canon(access)]; return ok && m.Enabled }
func priority(access string, methods map[string]Method) int { if m, ok := methods[canon(access)]; ok { return m.Priority }; return 99999 }
func clean(st string) string { return strings.TrimSpace(st) }
func canon(st string) string {
	switch strings.ToUpper(clean(st)) {
	case "SL": return "SOLO"
	case "GP": return "GROUP"
	case "ST": return "STAGE"
	default: return strings.ToUpper(clean(st))
	}
}
func allowed(st string) bool { st = canon(st); return st == "SOLO" || st == "GROUP" || st == "STAGE" }
func dateOK(st string) bool { s := clean(st); if len(s) != 10 { return false }; return s[4] == '-' && s[7] == '-' }
func has(headers []string, name string) bool { for _, h := range headers { if strings.EqualFold(clean(h), name) { return true } }; return false }
GO

/app/scripts/run_batch.sh
test -s /app/out/recital_credit_report.csv
test -s /app/out/recital_credit_summary.json
