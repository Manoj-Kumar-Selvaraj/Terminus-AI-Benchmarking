#!/usr/bin/env bash
set -euo pipefail
cd /app
cat > /app/cmd/reconcile/main.go <<'GOEOF'
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
	ID          string
	Customer    string
	Amount      int
	AmountRaw   string
	AmountValid bool
	Status      string
	PassType    string
}

type Credit struct {
	TripID      string
	Customer    string
	Amount      int
	AmountRaw   string
	AmountValid bool
	PassType    string
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
	trips, err := loadOrders("/app/data/orders.csv")
	if err != nil {
		return err
	}
	credits, err := loadCredits("/app/data/vouchers.csv")
	if err != nil {
		return err
	}
	return writeOutputs(trips, credits)
}

func loadOrders(path string) ([]Trip, error) {
	rows, err := readRows(path)
	if err != nil {
		return nil, err
	}
	out := make([]Trip, 0, len(rows))
	for _, row := range rows {
		amountRaw := clean(field(row, 2))
		amount, amountValid := parseAmount(amountRaw)
		out = append(out, Trip{ID: clean(field(row, 0)), Customer: clean(field(row, 1)), Amount: amount, AmountRaw: amountRaw, AmountValid: amountValid, Status: strings.ToUpper(clean(field(row, 3))), PassType: canonicalPassType(field(row, 4))})
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
		amountRaw := clean(field(row, 2))
		amount, amountValid := parseAmount(amountRaw)
		out = append(out, Credit{TripID: clean(field(row, 0)), Customer: clean(field(row, 1)), Amount: amount, AmountRaw: amountRaw, AmountValid: amountValid, PassType: canonicalPassType(field(row, 3))})
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
	reportFile, err := os.Create(filepath.Join("/app/out", "rally_voucher_report.csv"))
	if err != nil {
		return err
	}
	defer reportFile.Close()
	writer := csv.NewWriter(reportFile)
	defer writer.Flush()
	if err := writer.Write([]string{"order_id", "vendor_id", "meal_tier", "amount_cents", "status"}); err != nil {
		return err
	}

	summary := Summary{}
	usedRecords := make([]bool, len(trips))
	for _, credit := range credits {
		matchIndex := findMatch(trips, credit, usedRecords)
		passType := ""
		status := "UNMATCHED"
		if matchIndex >= 0 {
			match := &trips[matchIndex]
			usedRecords[matchIndex] = true
			passType = match.PassType
			status = "MATCHED"
			summary.MatchedCount++
			summary.MatchedAmountCents += credit.Amount
		} else {
			summary.UnmatchedCount++
			if credit.AmountValid {
				summary.UnmatchedAmountCents += credit.Amount
			}
		}
		if err := writer.Write([]string{credit.TripID, credit.Customer, passType, credit.AmountRaw, status}); err != nil {
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
	return os.WriteFile("/app/out/rally_voucher_summary.json", append(summaryBytes, '\n'), 0o644)
}

func findMatch(trips []Trip, credit Credit, used []bool) int {
	if !credit.AmountValid {
		return -1
	}
	for i := range trips {
		if used[i] {
			continue
		}
		trip := &trips[i]
		if trip.ID == credit.TripID && trip.Customer == credit.Customer && trip.AmountValid && trip.Amount == credit.Amount && trip.Status == "COMPLETED" && allowedPassType(trip.PassType) && trip.PassType == credit.PassType {
			return i
		}
	}
	return -1
}

func field(row []string, index int) string {
	if index < 0 || index >= len(row) {
		return ""
	}
	return row[index]
}

func clean(value string) string {
	return strings.TrimSpace(value)
}

func parseAmount(value string) (int, bool) {
	value = clean(value)
	if value == "" {
		return 0, false
	}
	for _, ch := range value {
		if ch < '0' || ch > '9' {
			return 0, false
		}
	}
	amount, err := strconv.Atoi(value)
	if err != nil || amount <= 0 {
		return 0, false
	}
	return amount, true
}

func canonicalPassType(passType string) string {
	switch strings.ToUpper(clean(passType)) {
	case "SN":
		return "SNACK"
	case "ML":
		return "MEAL"
	case "CB":
		return "COMBO"
	default:
		return strings.ToUpper(clean(passType))
	}
}

func allowedPassType(passType string) bool {
	passType = canonicalPassType(passType)
	return passType == "SNACK" || passType == "MEAL" || passType == "COMBO"
}

GOEOF
/app/scripts/run_batch.sh
test -s /app/out/rally_voucher_report.csv
test -s /app/out/rally_voucher_summary.json
