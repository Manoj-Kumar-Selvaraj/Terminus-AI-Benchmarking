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
	Passenger   string
	Amount      int
	AmountValid bool
	Status      string
	Tier        string
	TourDate    string
	HasTourDate bool
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
	return writeOutputs(tours, deposits, openDates)
}

func loadTours(path string) ([]Tour, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	tours := make([]Tour, 0, len(rows))
	for _, row := range rows {
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
			Tier:        canonicalTier(row[4]),
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
			Tier:        canonicalTier(row[3]),
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

func writeOutputs(tours []Tour, deposits []Deposit, openDates map[string]bool) error {
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
	for _, deposit := range deposits {
		status := "UNMATCHED"
		tier := ""
		if deposit.AmountValid {
			match := findMatch(tours, deposit, used, openDates)
			if match >= 0 {
				used[match] = true
				status = "MATCHED"
				tier = tours[match].Tier
				summary.MatchedCount++
				summary.MatchedAmountCents += deposit.Amount
			}
		}
		if status == "UNMATCHED" {
			summary.UnmatchedCount++
			if deposit.AmountValid {
				summary.UnmatchedAmountCents += deposit.Amount
			}
		}
		if err := writer.Write([]string{deposit.TourID, deposit.Passenger, tier, deposit.AmountText, status}); err != nil {
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

func findMatch(tours []Tour, deposit Deposit, used []bool, openDates map[string]bool) int {
	best := -1
	for i := range tours {
		if used[i] {
			continue
		}
		tour := tours[i]
		if !tour.AmountValid ||
			tour.ID != deposit.TourID ||
			tour.Passenger != deposit.Passenger ||
			tour.Amount != deposit.Amount ||
			tour.Status != "COMPLETED" ||
			!validTier(tour.Tier) ||
			tour.Tier != deposit.Tier {
			continue
		}
		if dateMode(&tour, &deposit) {
			if deposit.DepositDate == "" ||
				tour.TourDate == "" ||
				!openDates[deposit.DepositDate] ||
				deposit.DepositDate > tour.TourDate {
				continue
			}
		}
		if best < 0 || tour.TourDate > tours[best].TourDate || (tour.TourDate == tours[best].TourDate && i < best) {
			best = i
		}
	}
	return best
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

func dateMode(tour *Tour, deposit *Deposit) bool {
	return tour.HasTourDate || deposit.HasDepositDate
}

func canonicalTier(value string) string {
	tier := strings.ToUpper(clean(value))
	switch tier {
	case "ST":
		return "STD"
	case "PM":
		return "PREM"
	case "LX":
		return "LUX"
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
