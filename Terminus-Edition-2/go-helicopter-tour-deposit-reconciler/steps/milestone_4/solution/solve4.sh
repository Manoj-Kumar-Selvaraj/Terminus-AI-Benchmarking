#!/usr/bin/env bash
set -euo pipefail

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

type Tour struct {
	ID          string
	Passenger  string
	Amount      int
	AmountValid bool
	Status      string
	Tier        string
	TourDate    string
	HasTourDate bool
	Row         int
}

type Deposit struct {
	TourID         string
	Passenger      string
	Amount         int
	AmountText     string
	AmountValid    bool
	Tier           string
	DepositDate    string
	HasDepositDate bool
}

type Summary struct {
	MatchedCount         int `json:"matched_count"`
	MatchedAmountCents   int `json:"matched_amount_cents"`
	UnmatchedCount       int `json:"unmatched_count"`
	UnmatchedAmountCents int `json:"unmatched_amount_cents"`
}

type TierPolicy struct {
	Enabled       bool
	Priority      int
	PriorityValid bool
}

type Limit struct {
	Passenger string
	Date      string
	Max       int
	Row       int
}

type Blackout struct {
	TourID string
	Start  string
	End    string
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run() error {
	tours, err := loadTours("/app/data/tours.csv")
	if err != nil {
		return err
	}
	deposits, err := loadDeposits("/app/data/deposits.csv")
	if err != nil {
		return err
	}
	openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
	if err != nil {
		return err
	}
	policies, err := loadTierPolicies("/app/config/fleet_policy.csv")
	if err != nil {
		return err
	}
	limits, err := loadLimits("/app/config/passenger_limits.csv")
	if err != nil {
		return err
	}
	blackouts, err := loadBlackouts("/app/config/weather_blackouts.csv")
	if err != nil {
		return err
	}
	return writeOutputs(tours, deposits, openDates, policies, limits, blackouts)
}

func loadTours(path string) ([]Tour, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	tours := make([]Tour, 0, len(rows))
	for i, row := range rows {
		if len(row) < 5 {
			continue
		}
		amount, err := strconv.Atoi(clean(row[2]))
		tour := Tour{
			ID:          clean(row[0]),
			Passenger:   clean(row[1]),
			Amount:      amount,
			AmountValid: err == nil,
			Status:      strings.ToUpper(clean(row[3])),
			Tier:        canonicalTier(row[4], false),
			Row:         i,
		}
		if len(row) > 5 {
			tour.HasTourDate = true
			tour.TourDate = clean(row[5])
		}
		tours = append(tours, tour)
	}
	return tours, nil
}

func loadDeposits(path string) ([]Deposit, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	deposits := make([]Deposit, 0, len(rows))
	for _, row := range rows {
		if len(row) < 4 {
			continue
		}
		amountText := clean(row[2])
		amount, err := strconv.Atoi(amountText)
		deposit := Deposit{
			TourID:      clean(row[0]),
			Passenger:   clean(row[1]),
			Amount:      amount,
			AmountText:  amountText,
			AmountValid: err == nil,
			Tier:        canonicalTier(row[3], true),
		}
		if len(row) > 4 {
			deposit.HasDepositDate = true
			deposit.DepositDate = clean(row[4])
		}
		deposits = append(deposits, deposit)
	}
	return deposits, nil
}

func readRows(path string) ([][]string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer f.Close()
	reader := csv.NewReader(f)
	reader.FieldsPerRecord = -1
	rows, err := reader.ReadAll()
	if err != nil {
		return nil, err
	}
	if len(rows) <= 1 {
		return [][]string{}, nil
	}
	return rows[1:], nil
}

func writeOutputs(tours []Tour, deposits []Deposit, openDates map[string]bool, policies map[string]TierPolicy, limits []Limit, blackouts []Blackout) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportFile, err := os.Create(filepath.Join("/app/out", "tour_deposit_report.csv"))
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"tour_id", "passenger_id", "cabin_tier", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	used := make([]bool, len(tours))
	dailyTotals := map[string]int{}

	for _, deposit := range deposits {
		status := "UNMATCHED"
		outTier := ""
		if deposit.AmountValid {
			best := findMatch(tours, deposit, used, openDates, policies, blackouts)
			if best >= 0 && withinLimit(deposit, limits, dailyTotals) {
				used[best] = true
				status = "MATCHED"
				outTier = tours[best].Tier
				summary.MatchedCount++
				summary.MatchedAmountCents += deposit.Amount
				if dateSchemaActive(&tours[best], &deposit) {
					dailyTotals[limitKey(deposit.Passenger, deposit.DepositDate)] += deposit.Amount
				}
			}
		}
		if status == "UNMATCHED" {
			summary.UnmatchedCount++
			if deposit.AmountValid {
				summary.UnmatchedAmountCents += deposit.Amount
			}
		}
		if err := writer.Write([]string{
			deposit.TourID,
			deposit.Passenger,
			outTier,
			deposit.AmountText,
			status,
		}); err != nil {
			return err
		}
	}
	if writer.Error() != nil {
		return writer.Error()
	}
	data, err := json.MarshalIndent(summary, "", "  ")
	if err != nil {
		return err
	}
	return os.WriteFile("/app/out/tour_deposit_summary.json", append(data, '\n'), 0o644)
}

func findMatch(tours []Tour, deposit Deposit, used []bool, openDates map[string]bool, policies map[string]TierPolicy, blackouts []Blackout) int {
	best := -1
	for i := range tours {
		tour := &tours[i]
		if used[i] || !tour.AmountValid {
			continue
		}
		if tour.ID != deposit.TourID ||
			tour.Passenger != deposit.Passenger ||
			tour.Amount != deposit.Amount ||
			tour.Status != "COMPLETED" ||
			!validTier(tour.Tier) ||
			!tierEnabled(tour.Tier, policies) {
			continue
		}
		if deposit.Tier != "ANY" && tour.Tier != deposit.Tier {
			continue
		}
		if deposit.Tier == "ANY" && !validTier(tour.Tier) {
			continue
		}
		if dateSchemaActive(tour, &deposit) {
			if deposit.DepositDate == "" ||
				tour.TourDate == "" ||
				!openDates[deposit.DepositDate] ||
				deposit.DepositDate > tour.TourDate ||
				isBlackedOut(*tour, blackouts) {
				continue
			}
		}
		if betterCandidate(tours, i, best, policies, deposit.Tier == "ANY") {
			best = i
		}
	}
	return best
}

func betterCandidate(tours []Tour, candidate int, current int, policies map[string]TierPolicy, wildcard bool) bool {
	if current < 0 {
		return true
	}
	a := tours[candidate]
	b := tours[current]
	if a.TourDate != b.TourDate {
		return a.TourDate > b.TourDate
	}
	if wildcard {
		aRank := priorityRank(a.Tier, policies)
		bRank := priorityRank(b.Tier, policies)
		if aRank != bRank {
			return aRank < bRank
		}
	}
	return candidate < current
}

func priorityRank(tier string, policies map[string]TierPolicy) int {
	policy, ok := policies[tier]
	if !ok || !policy.Enabled || !policy.PriorityValid {
		return 1_000_000
	}
	return policy.Priority
}

func withinLimit(deposit Deposit, limits []Limit, totals map[string]int) bool {
	if !deposit.HasDepositDate {
		return true
	}
	limit, ok := selectLimit(deposit.Passenger, deposit.DepositDate, limits)
	if !ok {
		return false
	}
	return totals[limitKey(deposit.Passenger, deposit.DepositDate)]+deposit.Amount <= limit
}

func selectLimit(passenger string, depositDate string, limits []Limit) (int, bool) {
	best := -1
	for i := range limits {
		limit := limits[i]
		if limit.Passenger != passenger || limit.Date == "" || limit.Date > depositDate {
			continue
		}
		if best < 0 || limit.Date > limits[best].Date || (limit.Date == limits[best].Date && limit.Row > limits[best].Row) {
			best = i
		}
	}
	if best < 0 {
		return 0, false
	}
	return limits[best].Max, true
}

func dateSchemaActive(tour *Tour, deposit *Deposit) bool {
	return tour.HasTourDate || deposit.HasDepositDate
}

func loadOpenDates(path string) (map[string]bool, error) {
	data, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	openDates := map[string]bool{}
	for _, line := range strings.Split(string(data), "\n") {
		fields := strings.Fields(line)
		if len(fields) >= 2 && strings.EqualFold(fields[1], "open") {
			openDates[fields[0]] = true
		}
	}
	return openDates, nil
}

func loadTierPolicies(path string) (map[string]TierPolicy, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	policies := map[string]TierPolicy{}
	for _, row := range rows {
		if len(row) < 2 {
			continue
		}
		tier := canonicalTier(row[0], false)
		if !validTier(tier) {
			continue
		}
		enabled := strings.EqualFold(clean(row[1]), "true")
		priority := 1_000_000
		priorityValid := false
		if len(row) > 2 {
			if value, err := strconv.Atoi(clean(row[2])); err == nil {
				priority = value
				priorityValid = true
			}
		}
		policies[tier] = TierPolicy{Enabled: enabled, Priority: priority, PriorityValid: priorityValid}
	}
	return policies, nil
}

func loadLimits(path string) ([]Limit, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	limits := []Limit{}
	for i, row := range rows {
		if len(row) < 3 {
			continue
		}
		max, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			continue
		}
		limits = append(limits, Limit{
			Passenger: clean(row[0]),
			Date:      clean(row[1]),
			Max:       max,
			Row:       i,
		})
	}
	return limits, nil
}

func loadBlackouts(path string) ([]Blackout, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	blackouts := []Blackout{}
	for _, row := range rows {
		if len(row) < 3 {
			continue
		}
		blackout := Blackout{TourID: clean(row[0]), Start: clean(row[1]), End: clean(row[2])}
		if blackout.TourID == "" || blackout.Start == "" || blackout.End == "" || blackout.Start > blackout.End {
			continue
		}
		blackouts = append(blackouts, blackout)
	}
	return blackouts, nil
}

func isBlackedOut(tour Tour, blackouts []Blackout) bool {
	for _, blackout := range blackouts {
		if blackout.TourID == tour.ID && tour.TourDate >= blackout.Start && tour.TourDate <= blackout.End {
			return true
		}
	}
	return false
}

func tierEnabled(tier string, policies map[string]TierPolicy) bool {
	policy, ok := policies[tier]
	return ok && policy.Enabled
}

func limitKey(passenger string, date string) string {
	return passenger + "|" + date
}

func canonicalTier(value string, allowAny bool) string {
	tier := strings.ToUpper(clean(value))
	switch tier {
	case "ST":
		return "STD"
	case "PM":
		return "PREM"
	case "LX":
		return "LUX"
	case "ANY":
		if allowAny {
			return "ANY"
		}
	}
	return tier
}

func validTier(tier string) bool {
	return tier == "STD" || tier == "PREM" || tier == "LUX"
}

func clean(value string) string {
	return strings.TrimSpace(value)
}
GO

/app/scripts/run_batch.sh
test -s /app/out/tour_deposit_report.csv
test -s /app/out/tour_deposit_summary.json
