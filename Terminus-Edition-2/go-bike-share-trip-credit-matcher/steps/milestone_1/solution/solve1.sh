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

type Trip struct {
	ID, Customer, Station string
	Amount                int
	Status, PassType      string
}

type Credit struct {
	TripID, Customer, Station string
	Amount                    int
	PassType                  string
}

type Summary struct {
	MatchedCount         int `json:"matched_count"`
	MatchedAmountCents   int `json:"matched_amount_cents"`
	UnmatchedCount       int `json:"unmatched_count"`
	UnmatchedAmountCents int `json:"unmatched_amount_cents"`
}

func clean(value string) string {
	return strings.TrimSpace(value)
}

func upper(value string) string {
	return strings.ToUpper(clean(value))
}

func allowedPassType(passType string) bool {
	switch upper(passType) {
	case "DAY", "MONTH", "ANNUAL":
		return true
	default:
		return false
	}
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run() error {
	trips, err := loadTrips("/app/data/trips.csv")
	if err != nil {
		return err
	}
	credits, err := loadCredits("/app/data/credits.csv")
	if err != nil {
		return err
	}
	return writeOutputs(trips, credits)
}

func loadTrips(path string) ([]Trip, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Trip, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row[3]))
		if err != nil {
			return nil, err
		}
		out = append(out, Trip{
			ID: clean(row[0]), Customer: clean(row[1]), Station: clean(row[2]),
			Amount: amount, Status: upper(row[4]), PassType: upper(row[5]),
		})
	}
	return out, nil
}

func loadCredits(path string) ([]Credit, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Credit, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row[3]))
		if err != nil {
			return nil, err
		}
		out = append(out, Credit{
			TripID: clean(row[0]), Customer: clean(row[1]), Station: clean(row[2]),
			Amount: amount, PassType: upper(row[4]),
		})
	}
	return out, nil
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
	if len(rows) == 0 {
		return nil, nil
	}
	return rows[1:], nil
}

func writeOutputs(trips []Trip, credits []Credit) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "credit_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"trip_id", "rider_id", "pass_type", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	used := make([]bool, len(trips))
	for _, credit := range credits {
		matchIndex := findMatch(trips, used, credit)
		passType := ""
		status := "UNMATCHED"
		if matchIndex >= 0 {
			used[matchIndex] = true
			passType = trips[matchIndex].PassType
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents += credit.Amount
		} else {
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += credit.Amount
		}
		if err := writer.Write([]string{
			clean(credit.TripID),
			clean(credit.Customer),
			passType,
			strconv.Itoa(credit.Amount),
			status,
		}); err != nil {
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

func findMatch(trips []Trip, used []bool, credit Credit) int {
	for i := range trips {
		if used[i] {
			continue
		}
		trip := &trips[i]
		if trip.ID == clean(credit.TripID) &&
			trip.Customer == clean(credit.Customer) &&
			trip.Station == clean(credit.Station) &&
			trip.Amount == credit.Amount &&
			upper(trip.Status) == "COMPLETED" &&
			allowedPassType(trip.PassType) &&
			upper(trip.PassType) == upper(credit.PassType) {
			return i
		}
	}
	return -1
}
GO
/app/scripts/run_batch.sh
