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
	ID           string
	Customer     string
	Amount       int
	AmountRaw    string
	AmountValid  bool
	Status       string
	PassType     string
	OrderDate    string
	HasOrderDate bool
	RowIndex     int
}

type Credit struct {
	TripID        string
	Customer      string
	Amount        int
	AmountRaw     string
	AmountValid   bool
	PassType      string
	CreditDate    string
	HasCreditDate bool
}

type Summary struct {
	MatchedCount         int `json:"matched_count"`
	MatchedAmountCents   int `json:"matched_amount_cents"`
	UnmatchedCount       int `json:"unmatched_count"`
	UnmatchedAmountCents int `json:"unmatched_amount_cents"`
}

type csvData struct {
	Header []string
	Rows   [][]string
}

func main() {
	if err := run(); err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
}

func run() error {
	trips, ordersHaveDates, err := loadOrders("/app/data/orders.csv")
	if err != nil {
		return err
	}
	credits, vouchersHaveDates, err := loadCredits("/app/data/vouchers.csv")
	if err != nil {
		return err
	}
	openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
	if err != nil {
		return err
	}
	return writeOutputs(trips, credits, openDates, ordersHaveDates || vouchersHaveDates)
}

func loadOrders(path string) ([]Trip, bool, error) {
	data, err := readCSV(path)
	if err != nil {
		return nil, false, err
	}
	hasDateColumn := indexOfHeader(data.Header, "order_date") >= 0
	out := make([]Trip, 0, len(data.Rows))
	for idx, row := range data.Rows {
		amountRaw := clean(field(row, 2))
		amount, amountValid := parseAmount(amountRaw)
		orderDate := ""
		if hasDateColumn {
			orderDate = clean(field(row, 5))
		}
		out = append(out, Trip{ID: clean(field(row, 0)), Customer: clean(field(row, 1)), Amount: amount, AmountRaw: amountRaw, AmountValid: amountValid, Status: strings.ToUpper(clean(field(row, 3))), PassType: canonicalPassType(field(row, 4)), OrderDate: orderDate, HasOrderDate: hasDateColumn, RowIndex: idx})
	}
	return out, hasDateColumn, nil
}

func loadCredits(path string) ([]Credit, bool, error) {
	data, err := readCSV(path)
	if err != nil {
		return nil, false, err
	}
	hasDateColumn := indexOfHeader(data.Header, "voucher_date") >= 0
	out := make([]Credit, 0, len(data.Rows))
	for _, row := range data.Rows {
		amountRaw := clean(field(row, 2))
		amount, amountValid := parseAmount(amountRaw)
		creditDate := ""
		if hasDateColumn {
			creditDate = clean(field(row, 4))
		}
		out = append(out, Credit{TripID: clean(field(row, 0)), Customer: clean(field(row, 1)), Amount: amount, AmountRaw: amountRaw, AmountValid: amountValid, PassType: canonicalPassType(field(row, 3)), CreditDate: creditDate, HasCreditDate: hasDateColumn})
	}
	return out, hasDateColumn, nil
}

func readCSV(path string) (csvData, error) {
	f, err := os.Open(path)
	if err != nil {
		return csvData{}, err
	}
	defer f.Close()
	reader := csv.NewReader(f)
	reader.FieldsPerRecord = -1
	rows, err := reader.ReadAll()
	if err != nil {
		return csvData{}, err
	}
	if len(rows) == 0 {
		return csvData{}, nil
	}
	return csvData{Header: rows[0], Rows: rows[1:]}, nil
}

func writeOutputs(trips []Trip, credits []Credit, openDates map[string]bool, dateSchemaActive bool) error {
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
		matchIndex := findMatch(trips, credit, usedRecords, openDates, dateSchemaActive)
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

func findMatch(trips []Trip, credit Credit, used []bool, openDates map[string]bool, dateSchemaActive bool) int {
	if !credit.AmountValid {
		return -1
	}
	bestIndex := -1
	for i := range trips {
		if used[i] {
			continue
		}
		trip := &trips[i]
		if trip.ID != credit.TripID || trip.Customer != credit.Customer || !trip.AmountValid || trip.Amount != credit.Amount || trip.Status != "COMPLETED" || !allowedPassType(trip.PassType) || trip.PassType != credit.PassType {
			continue
		}
		if dateSchemaActive {
			if !credit.HasCreditDate || credit.CreditDate == "" || !openDates[credit.CreditDate] || !trip.HasOrderDate || trip.OrderDate == "" || credit.CreditDate > trip.OrderDate {
				continue
			}
		}
		if bestIndex < 0 || isBetterCandidate(*trip, trips[bestIndex], dateSchemaActive) {
			bestIndex = i
		}
	}
	return bestIndex
}

func isBetterCandidate(candidate Trip, current Trip, dateSchemaActive bool) bool {
	if !dateSchemaActive {
		return candidate.RowIndex < current.RowIndex
	}
	if candidate.OrderDate != current.OrderDate {
		return candidate.OrderDate > current.OrderDate
	}
	return candidate.RowIndex < current.RowIndex
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

func field(row []string, index int) string {
	if index < 0 || index >= len(row) {
		return ""
	}
	return row[index]
}

func indexOfHeader(header []string, name string) int {
	for i, value := range header {
		if strings.EqualFold(clean(value), name) {
			return i
		}
	}
	return -1
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
