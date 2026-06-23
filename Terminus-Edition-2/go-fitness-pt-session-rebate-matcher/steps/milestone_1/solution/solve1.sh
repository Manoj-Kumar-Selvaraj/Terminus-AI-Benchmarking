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

type Session struct{ ID, Client, Status, Access, VisitDate string; Amount int }
type Rebate struct{ SessionID, Client, Access, RebateDate string; Amount int }
type Method struct{ Enabled bool; Priority int }
type Limit struct{ Client, Access, Effective string; Max, Row int }
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
	sessionRows, sessionHeaders, err := readTable("/app/data/sessions.csv")
	if err != nil { return err }
	rebateRows, rebateHeaders, err := readTable("/app/data/rebates.csv")
	if err != nil { return err }
	dated := has(sessionHeaders, "session_date") && has(rebateHeaders, "rebate_date")
	sessions := loadSessions(sessionRows, dated)
	rebates := loadRebates(rebateRows, dated)
	methods, err := loadMethods("/app/config/methods.csv")
	if err != nil { return err }
	openDates := map[string]bool{}
	if dated {
		openDates, err = loadOpenDates("/app/config/cutoff_calendar.txt")
		if err != nil { return err }
	}
	limits := []Limit{}
	if dated { limits, _ = loadLimits("/app/config/client_limits.csv") }
	blackouts := []Blackout{}
	if dated { blackouts, _ = loadBlackouts("/app/config/blackouts.csv") }
	return writeOutputs(sessions, rebates, dated, openDates, methods, limits, blackouts)
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
			tm := ""
			if i < len(vals) { tm = vals[i] }
			m[clean(h)] = tm
		}
		out = append(out, m)
	}
	return out, headers, nil
}

func loadSessions(rows []map[string]string, dated bool) []Session {
	out := []Session{}
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row["amount_cents"])); if err != nil { continue }
		p := Session{ID: clean(row["session_id"]), Client: clean(row["client_id"]), Amount: amount, Status: strings.ToUpper(clean(row["status"])), Access: canon(row["training_type"])}
		if dated { p.VisitDate = clean(row["session_date"]) }
		out = append(out, p)
	}
	return out
}

func loadRebates(rows []map[string]string, dated bool) []Rebate {
	out := []Rebate{}
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row["amount_cents"])); if err != nil { continue }
		r := Rebate{SessionID: clean(row["session_id"]), Client: clean(row["client_id"]), Amount: amount, Access: canon(row["training_type"])}
		if dated { r.RebateDate = clean(row["rebate_date"]) }
		out = append(out, r)
	}
	return out
}

func loadMethods(path string) (map[string]Method, error) {
	rows, _, err := readTable(path); if err != nil { return nil, err }
	methods := map[string]Method{}
	for i, row := range rows {
		access := canon(row["training_type"])
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
		access := canon(row["training_type"])
		if !allowed(access) || !strings.EqualFold(clean(row["status"]), "ACTIVE") || !dateOK(row["effective_date"]) { continue }
		max, err := strconv.Atoi(clean(row["max_daily_amount"])); if err != nil { continue }
		out = append(out, Limit{Client: clean(row["client_id"]), Access: access, Effective: clean(row["effective_date"]), Max: max, Row: i})
	}
	return out, nil
}

func loadBlackouts(path string) ([]Blackout, error) {
	rows, _, err := readTable(path); if err != nil { return nil, err }
	out := []Blackout{}
	for _, row := range rows {
		access := canon(row["training_type"])
		if !allowed(access) || !strings.EqualFold(clean(row["state"]), "ACTIVE") || !dateOK(row["start_date"]) || !dateOK(row["end_date"]) { continue }
		start, end := clean(row["start_date"]), clean(row["end_date"])
		if start > end { continue }
		out = append(out, Blackout{Access: access, Start: start, End: end})
	}
	return out, nil
}

func writeOutputs(sessions []Session, rebates []Rebate, dated bool, open map[string]bool, methods map[string]Method, limits []Limit, blackouts []Blackout) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil { return err }
	f, err := os.Create("/app/out/session_rebate_report.csv"); if err != nil { return err }
	defer f.Close()
	w := csv.NewWriter(f); defer w.Flush()
	_ = w.Write([]string{"session_id", "client_id", "training_type", "amount_cents", "status"})
	used := make([]bool, len(sessions))
	budget := map[string]int{}
	s := Summary{}
	for _, rebate := range rebates {
		idx := findMatch(sessions, rebate, used, dated, open, methods, limits, blackouts, budget)
		if idx >= 0 {
			used[idx] = true
			if dated { budget[budgetKey(rebate, sessions[idx].Access)] += rebate.Amount }
			s.MatchedCount++; s.MatchedAmountCents += rebate.Amount
			_ = w.Write([]string{rebate.SessionID, rebate.Client, sessions[idx].Access, strconv.Itoa(rebate.Amount), "MATCHED"})
		} else {
			s.UnmatchedCount++; s.UnmatchedAmountCents += rebate.Amount
			_ = w.Write([]string{rebate.SessionID, rebate.Client, "", strconv.Itoa(rebate.Amount), "UNMATCHED"})
		}
	}
	w.Flush(); if err := w.Error(); err != nil { return err }
	data, err := json.Marshal(s); if err != nil { return err }
	return os.WriteFile("/app/out/session_rebate_summary.json", data, 0o644)
}

func findMatch(sessions []Session, rebate Rebate, used []bool, dated bool, open map[string]bool, methods map[string]Method, limits []Limit, blackouts []Blackout, budget map[string]int) int {
	best := -1
	for i, session := range sessions {
		if used[i] || !eligible(session, rebate, dated, open, methods, limits, blackouts, budget) { continue }
		if best < 0 || better(session, sessions[best], i, best, dated, methods) { best = i }
	}
	return best
}

func eligible(session Session, rebate Rebate, dated bool, open map[string]bool, methods map[string]Method, limits []Limit, blackouts []Blackout, budget map[string]int) bool {
	if session.ID != rebate.SessionID || session.Client != rebate.Client || session.Amount != rebate.Amount || session.Status != "ACTIVE" || !methodEnabled(session.Access, methods) { return false }
	if rebate.Access != "ANY" && (rebate.Access != session.Access || !methodEnabled(rebate.Access, methods)) { return false }
	if dated {
		if rebate.RebateDate == "" || session.VisitDate == "" || !open[rebate.RebateDate] || rebate.RebateDate > session.VisitDate { return false }
		if blackedOut(session.Access, rebate.RebateDate, blackouts) { return false }
		if len(limits) > 0 {
			limit := bestLimit(rebate, session.Access, limits)
			if limit == nil || budget[budgetKey(rebate, session.Access)]+rebate.Amount > limit.Max { return false }
		}
	}
	return true
}

func better(session Session, best Session, sessionRow, bestRow int, dated bool, methods map[string]Method) bool {
	if dated && session.VisitDate != best.VisitDate { return session.VisitDate > best.VisitDate }
	pp, bp := priority(session.Access, methods), priority(best.Access, methods)
	if pp != bp { return pp < bp }
	return sessionRow < bestRow
}

func bestLimit(rebate Rebate, access string, limits []Limit) *Limit {
	var best *Limit
	for i := range limits {
		l := &limits[i]
		if l.Client != rebate.Client || l.Access != access || l.Effective > rebate.RebateDate { continue }
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

func budgetKey(rebate Rebate, access string) string { return rebate.Client + "|" + access + "|" + rebate.RebateDate }
func methodEnabled(access string, methods map[string]Method) bool { m, ok := methods[canon(access)]; return ok && m.Enabled }
func priority(access string, methods map[string]Method) int { if m, ok := methods[canon(access)]; ok { return m.Priority }; return 99999 }
func clean(tm string) string { return strings.TrimSpace(tm) }
func canon(tm string) string {
	switch strings.ToUpper(clean(tm)) {
	case "SO": return "SOLO"
	case "DU": return "DUO"
	case "TM": return "TEAM"
	default: return strings.ToUpper(clean(tm))
	}
}
func allowed(tm string) bool { tm = canon(tm); return tm == "SOLO" || tm == "DUO" || tm == "TEAM" }
func dateOK(tm string) bool { s := clean(tm); if len(s) != 10 { return false }; return s[4] == '-' && s[7] == '-' }
func has(headers []string, name string) bool { for _, h := range headers { if strings.EqualFold(clean(h), name) { return true } }; return false }
GO

/app/scripts/run_batch.sh
test -s /app/out/session_rebate_report.csv
test -s /app/out/session_rebate_summary.json
