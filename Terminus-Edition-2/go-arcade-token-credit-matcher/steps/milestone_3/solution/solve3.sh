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
	ID, Customer string
	Amount       int
	Status, PassType string
	PlayDate     string
}

type Credit struct {
	TripID, Customer string
	Amount           int
	PassType         string
	CreditDate       string
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

func canonicalPassType(passType string) string {
	switch upper(passType) {
	case "AR":
		return "ARC"
	case "PR":
		return "PRO"
	case "VI":
		return "VIP"
	default:
		return upper(passType)
	}
}

func allowedPassType(passType string) bool {
	switch canonicalPassType(passType) {
	case "ARC", "PRO", "VIP":
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
	trips, err := loadTrips("/app/data/plays.csv")
	if err != nil {
		return err
	}
	credits, err := loadCredits("/app/data/token_credits.csv")
	if err != nil {
		return err
	}
	openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
	if err != nil {
		return err
	}
	return writeOutputs(trips, credits, openDates)
}

func loadTrips(path string) ([]Trip, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Trip, 0, len(rows))
	for _, row := range rows {
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		playDate := ""
		if len(row) > 5 {
			playDate = clean(row[5])
		}
		out = append(out, Trip{
			ID: clean(row[0]), Customer: clean(row[1]), Amount: amount,
			Status: upper(row[3]), PassType: canonicalPassType(row[4]), PlayDate: playDate,
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
		amount, err := strconv.Atoi(clean(row[2]))
		if err != nil {
			return nil, err
		}
		creditDate := ""
		if len(row) > 4 {
			creditDate = clean(row[4])
		}
		out = append(out, Credit{
			TripID: clean(row[0]), Customer: clean(row[1]), Amount: amount,
			PassType: canonicalPassType(row[3]), CreditDate: creditDate,
		})
	}
	return out, nil
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

func writeOutputs(trips []Trip, credits []Credit, openDates map[string]bool) error {
	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	reportPath := filepath.Join("/app/out", "token_credit_report.csv")
	reportFile, err := os.Create(reportPath)
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"play_id", "member_id", "token_tier", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	used := make([]bool, len(trips))
	for _, credit := range credits {
		matchIndex := findMatch(trips, credit, used, openDates)
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
	return os.WriteFile("/app/out/token_credit_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(trips []Trip, credit Credit, used []bool, openDates map[string]bool) int {
	bestIndex := -1
	for i := range trips {
		if used[i] {
			continue
		}
		trip := &trips[i]
		if !openDates[credit.CreditDate] ||
			credit.CreditDate == "" ||
			trip.PlayDate == "" ||
			credit.CreditDate > trip.PlayDate ||
			trip.ID != clean(credit.TripID) ||
			trip.Customer != clean(credit.Customer) ||
			trip.Amount != credit.Amount ||
			trip.Status != "COMPLETED" ||
			!allowedPassType(trip.PassType) ||
			trip.PassType != credit.PassType {
			continue
		}
		if bestIndex < 0 ||
			trip.PlayDate > trips[bestIndex].PlayDate ||
			(trip.PlayDate == trips[bestIndex].PlayDate && i < bestIndex) {
			bestIndex = i
		}
	}
	return bestIndex
}
GO
/app/scripts/run_batch.sh
