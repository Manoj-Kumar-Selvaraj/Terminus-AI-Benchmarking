#!/usr/bin/env bash
set -euo pipefail

cd /app

cat > /app/cmd/reconcile/main.go <<'GO'
package main

import (
	"encoding/csv"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

type Order struct {
	ID          string
	Cafe        string
	Amount      int
	Status      string
	Route       string
	BakeDate    string
	HasBakeDate bool
	Row         int
}

type Credit struct {
	OrderID       string
	Cafe          string
	Amount        int
	Route         string
	CreditDate    string
	HasCreditDate bool
}

type RoutePolicy struct {
	Enabled  bool
	Priority int
}

type CafeLimit struct {
	Cafe          string
	EffectiveDate string
	MaxCents      int
	Row           int
}

type Blackout struct {
	Cafe  string
	Route string
	Start string
	End   string
}

type Summary struct {
	MatchedCount         int `json:"matched_count"`
	MatchedAmountCents   int `json:"matched_amount_cents"`
	UnmatchedCount       int `json:"unmatched_count"`
	UnmatchedAmountCents int `json:"unmatched_amount_cents"`
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run() error {
	orders, orderDates, err := loadOrders("/app/data/orders.csv")
	if err != nil {
		return err
	}
	credits, creditDates, err := loadCredits("/app/data/credits.csv")
	if err != nil {
		return err
	}
	openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
	if err != nil {
		return err
	}
	policies, err := loadRoutePolicies("/app/config/route_policy.csv")
	if err != nil {
		return err
	}
	limits, err := loadCafeLimits("/app/config/cafe_limits.csv")
	if err != nil {
		return err
	}
	blackouts, err := loadBlackouts("/app/config/route_blackouts.csv")
	if err != nil {
		return err
	}
	return writeOutputs(orders, credits, openDates, policies, limits, blackouts, orderDates || creditDates)
}

func loadOrders(path string) ([]Order, bool, error) {
	header, rows, err := readCSV(path)
	if err != nil {
		return nil, false, err
	}
	hasDate := headerIndex(header, "bake_date") >= 0
	out := make([]Order, 0, len(rows))
	for i, row := range rows {
		amount, ok := parseInt(get(row, header, "amount_cents"))
		if !ok {
			return nil, hasDate, fmt.Errorf("invalid order amount on row %d", i+2)
		}
		out = append(out, Order{
			ID:          clean(get(row, header, "order_id")),
			Cafe:        clean(get(row, header, "cafe_id")),
			Amount:      amount,
			Status:      strings.ToUpper(clean(get(row, header, "status"))),
			Route:       canonicalRoute(get(row, header, "route")),
			BakeDate:    clean(get(row, header, "bake_date")),
			HasBakeDate: hasDate,
			Row:         i,
		})
	}
	return out, hasDate, nil
}

func loadCredits(path string) ([]Credit, bool, error) {
	header, rows, err := readCSV(path)
	if err != nil {
		return nil, false, err
	}
	hasDate := headerIndex(header, "credit_date") >= 0
	out := make([]Credit, 0, len(rows))
	for i, row := range rows {
		amount, ok := parseInt(get(row, header, "amount_cents"))
		if !ok {
			return nil, hasDate, fmt.Errorf("invalid credit amount on row %d", i+2)
		}
		out = append(out, Credit{
			OrderID:       clean(get(row, header, "order_id")),
			Cafe:          clean(get(row, header, "cafe_id")),
			Amount:        amount,
			Route:         canonicalRoute(get(row, header, "route")),
			CreditDate:    clean(get(row, header, "credit_date")),
			HasCreditDate: hasDate,
		})
	}
	return out, hasDate, nil
}

func writeOutputs(orders []Order, credits []Credit, openDates map[string]bool, policies map[string]RoutePolicy, limits []CafeLimit, blackouts []Blackout, dated bool) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportFile, err := os.Create(filepath.Join("/app/out", "credit_report.csv"))
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"order_id", "cafe_id", "route", "amount_cents", "status"}); err != nil {
		return err
	}

	used := make([]bool, len(orders))
	budgetUsed := map[string]int{}
	summary := Summary{}
	for _, credit := range credits {
		matchIndex := findMatch(orders, credit, used, openDates, policies, blackouts, dated)
		route := ""
		status := "UNMATCHED"
		if matchIndex >= 0 && withinLimit(credit, limits, budgetUsed, dated) {
			used[matchIndex] = true
			if dated {
				budgetUsed[limitKey(credit)] += credit.Amount
			}
			if credit.Route == "ANY" {
				route = orders[matchIndex].Route
			} else {
				route = credit.Route
			}
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents += credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{credit.OrderID, credit.Cafe, route, strconv.Itoa(credit.Amount), status}); err != nil {
			return err
		}
	}
	if writer.Error() != nil {
		return writer.Error()
	}
	summaryBytes, err := json.MarshalIndent(summary, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile("/app/out/credit_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(orders []Order, credit Credit, used []bool, openDates map[string]bool, policies map[string]RoutePolicy, blackouts []Blackout, dated bool) int {
	best := -1
	for i := range orders {
		order := orders[i]
		if used[i] ||
			order.ID != credit.OrderID ||
			order.Cafe != credit.Cafe ||
			order.Amount != credit.Amount ||
			order.Status != "FULFILLED" ||
			!routeEnabled(order.Route, policies) ||
			!creditRouteMatches(credit.Route, order.Route) {
			continue
		}
		if dated && (credit.CreditDate == "" || order.BakeDate == "" || !openDates[credit.CreditDate] || credit.CreditDate > order.BakeDate || isBlackedOut(order, blackouts)) {
			continue
		}
		if best < 0 || betterCandidate(order, orders[best], credit.Route == "ANY", dated, policies) {
			best = i
		}
	}
	return best
}

func betterCandidate(candidate Order, current Order, anyRoute bool, dated bool, policies map[string]RoutePolicy) bool {
	if dated && candidate.BakeDate != current.BakeDate {
		return candidate.BakeDate > current.BakeDate
	}
	if anyRoute {
		candidatePriority := priorityRank(candidate.Route, policies)
		currentPriority := priorityRank(current.Route, policies)
		if candidatePriority != currentPriority {
			return candidatePriority < currentPriority
		}
	}
	return candidate.Row < current.Row
}

func withinLimit(credit Credit, limits []CafeLimit, used map[string]int, dated bool) bool {
	if !dated {
		return true
	}
	limit, ok := selectLimit(credit, limits)
	if !ok {
		return false
	}
	return used[limitKey(credit)]+credit.Amount <= limit.MaxCents
}

func selectLimit(credit Credit, limits []CafeLimit) (CafeLimit, bool) {
	var selected CafeLimit
	found := false
	for _, limit := range limits {
		if limit.Cafe != credit.Cafe || limit.EffectiveDate == "" || limit.EffectiveDate > credit.CreditDate {
			continue
		}
		if !found || limit.EffectiveDate > selected.EffectiveDate || (limit.EffectiveDate == selected.EffectiveDate && limit.Row > selected.Row) {
			selected = limit
			found = true
		}
	}
	return selected, found
}

func readCSV(path string) ([]string, [][]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, nil, err
	}
	defer f.Close()
	reader := csv.NewReader(f)
	reader.FieldsPerRecord = -1
	rows, err := reader.ReadAll()
	if err != nil {
		return nil, nil, err
	}
	if len(rows) == 0 {
		return nil, nil, nil
	}
	header := make([]string, len(rows[0]))
	for i, name := range rows[0] {
		header[i] = strings.ToLower(clean(name))
	}
	return header, rows[1:], nil
}

func loadOpenDates(path string) (map[string]bool, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	openDates := map[string]bool{}
	for _, line := range strings.Split(string(data), "\n") {
		fields := strings.Fields(line)
		if len(fields) == 2 && strings.EqualFold(fields[1], "open") {
			openDates[fields[0]] = true
		}
	}
	return openDates, nil
}

func loadRoutePolicies(path string) (map[string]RoutePolicy, error) {
	header, rows, err := readCSV(path)
	if err != nil {
		return nil, err
	}
	policies := map[string]RoutePolicy{}
	for i, row := range rows {
		route := canonicalRoute(get(row, header, "route"))
		if !allowedRoute(route) {
			continue
		}
		priority, ok := parseInt(get(row, header, "priority"))
		if !ok {
			priority = 1_000_000 + i
		}
		policies[route] = RoutePolicy{Enabled: strings.EqualFold(clean(get(row, header, "enabled")), "Y"), Priority: priority}
	}
	return policies, nil
}

func loadCafeLimits(path string) ([]CafeLimit, error) {
	header, rows, err := readCSV(path)
	if err != nil {
		return nil, err
	}
	limits := []CafeLimit{}
	for i, row := range rows {
		amount, ok := parseInt(get(row, header, "max_daily_amount_cents"))
		if !ok {
			continue
		}
		limits = append(limits, CafeLimit{
			Cafe:          clean(get(row, header, "cafe_id")),
			EffectiveDate: clean(get(row, header, "effective_date")),
			MaxCents:      amount,
			Row:           i,
		})
	}
	return limits, nil
}

func loadBlackouts(path string) ([]Blackout, error) {
	header, rows, err := readCSV(path)
	if err != nil {
		return nil, err
	}
	blackouts := []Blackout{}
	for _, row := range rows {
		blackout := Blackout{
			Cafe:  clean(get(row, header, "cafe_id")),
			Route: canonicalRoute(get(row, header, "route")),
			Start: clean(get(row, header, "start_date")),
			End:   clean(get(row, header, "end_date")),
		}
		if blackout.Cafe == "" || !allowedRoute(blackout.Route) || blackout.Start == "" || blackout.End == "" || blackout.Start > blackout.End {
			continue
		}
		blackouts = append(blackouts, blackout)
	}
	return blackouts, nil
}

func isBlackedOut(order Order, blackouts []Blackout) bool {
	for _, blackout := range blackouts {
		if blackout.Cafe == order.Cafe && blackout.Route == order.Route && order.BakeDate >= blackout.Start && order.BakeDate <= blackout.End {
			return true
		}
	}
	return false
}

func creditRouteMatches(creditRoute string, orderRoute string) bool {
	return creditRoute == "ANY" || creditRoute == orderRoute
}

func routeEnabled(route string, policies map[string]RoutePolicy) bool {
	policy, ok := policies[route]
	return ok && policy.Enabled
}

func priorityRank(route string, policies map[string]RoutePolicy) int {
	if policy, ok := policies[route]; ok {
		return policy.Priority
	}
	return 1_000_000
}

func canonicalRoute(route string) string {
	switch strings.ToUpper(clean(route)) {
	case "LOC":
		return "LOCAL"
	case "REG":
		return "REGIONAL"
	case "EXP":
		return "EXPORT"
	case "LOCAL", "REGIONAL", "EXPORT", "ANY":
		return strings.ToUpper(clean(route))
	default:
		return strings.ToUpper(clean(route))
	}
}

func allowedRoute(route string) bool {
	return route == "LOCAL" || route == "REGIONAL" || route == "EXPORT"
}

func limitKey(credit Credit) string {
	return credit.Cafe + "|" + credit.CreditDate
}

func get(row []string, header []string, name string) string {
	index := headerIndex(header, name)
	if index < 0 || index >= len(row) {
		return ""
	}
	return row[index]
}

func headerIndex(header []string, name string) int {
	for i, field := range header {
		if field == name {
			return i
		}
	}
	return -1
}

func parseInt(value string) (int, bool) {
	number, err := strconv.Atoi(clean(value))
	return number, err == nil
}

func clean(value string) string {
	return strings.TrimSpace(value)
}
GO

/app/scripts/run_batch.sh
test -s /app/out/credit_report.csv
test -s /app/out/credit_summary.json
