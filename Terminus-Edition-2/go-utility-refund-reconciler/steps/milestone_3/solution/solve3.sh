#!/usr/bin/env bash
set -euo pipefail

cat > /app/cmd/reconcile/main.go <<'GO'
package main

import (
	"encoding/csv"
	"encoding/json"
	"os"
	"strconv"
	"strings"
)

type Bill struct {
	ID       string
	Customer string
	Amount   int
	Status   string
	Channel  string
	DueDate  string
	Row      int
}

type Refund struct {
	BillID     string
	Customer   string
	Amount     int
	Channel    string
	RefundDate string
}

type ReportRow struct {
	BillID   string
	Customer string
	Channel  string
	Amount   int
	Status   string
}

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
	bills, hasDueDate, err := loadBills("/app/data/bills.csv")
	if err != nil {
		return err
	}
	refunds, hasRefundDate, err := loadRefunds("/app/data/refunds.csv")
	if err != nil {
		return err
	}
	openDates, err := loadOpenDates("/app/config/cutoff_calendar.txt")
	if err != nil {
		return err
	}
	return writeOutputs(bills, refunds, openDates, hasDueDate && hasRefundDate)
}

func loadBills(path string) ([]Bill, bool, error) {
	records, hasDueDate, err := readCSV(path, "due_date")
	if err != nil {
		return nil, false, err
	}
	bills := make([]Bill, 0, len(records))
	for i, row := range records {
		amount, err := strconv.Atoi(clean(row["amount_cents"]))
		if err != nil {
			continue
		}
		bills = append(bills, Bill{
			ID:       clean(row["bill_id"]),
			Customer: clean(row["customer_id"]),
			Amount:   amount,
			Status:   strings.ToUpper(clean(row["status"])),
			Channel:  canonicalChannel(row["channel"]),
			DueDate:  clean(row["due_date"]),
			Row:      i,
		})
	}
	return bills, hasDueDate, nil
}

func loadRefunds(path string) ([]Refund, bool, error) {
	records, hasRefundDate, err := readCSV(path, "refund_date")
	if err != nil {
		return nil, false, err
	}
	refunds := make([]Refund, 0, len(records))
	for _, row := range records {
		amount, err := strconv.Atoi(clean(row["amount_cents"]))
		if err != nil {
			continue
		}
		refunds = append(refunds, Refund{
			BillID:     clean(row["bill_id"]),
			Customer:   clean(row["customer_id"]),
			Amount:     amount,
			Channel:    canonicalChannel(row["channel"]),
			RefundDate: clean(row["refund_date"]),
		})
	}
	return refunds, hasRefundDate, nil
}

func readCSV(path string, optionalColumn string) ([]map[string]string, bool, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, false, err
	}
	defer file.Close()

	reader := csv.NewReader(file)
	reader.FieldsPerRecord = -1
	rows, err := reader.ReadAll()
	if err != nil {
		return nil, false, err
	}
	if len(rows) == 0 {
		return nil, false, nil
	}
	headers := rows[0]
	hasOptional := false
	out := make([]map[string]string, 0, len(rows)-1)
	for _, header := range headers {
		if clean(header) == optionalColumn {
			hasOptional = true
			break
		}
	}
	for _, values := range rows[1:] {
		row := map[string]string{}
		for i, header := range headers {
			value := ""
			if i < len(values) {
				value = values[i]
			}
			row[clean(header)] = value
		}
		out = append(out, row)
	}
	return out, hasOptional, nil
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

func writeOutputs(bills []Bill, refunds []Refund, openDates map[string]bool, datedMode bool) error {
	usedBills := make([]bool, len(bills))
	reportRows := make([]ReportRow, 0, len(refunds))
	summary := Summary{}

	for _, refund := range refunds {
		matchIndex := findMatch(bills, refund, usedBills, openDates, datedMode)
		if matchIndex >= 0 {
			usedBills[matchIndex] = true
			reportRows = append(reportRows, ReportRow{BillID: refund.BillID, Customer: refund.Customer, Channel: bills[matchIndex].Channel, Amount: refund.Amount, Status: "MATCHED"})
			summary.MatchedCount++
			summary.MatchedAmountCents += refund.Amount
		} else {
			reportRows = append(reportRows, ReportRow{BillID: refund.BillID, Customer: refund.Customer, Channel: "", Amount: refund.Amount, Status: "UNMATCHED"})
			summary.UnmatchedCount++
			summary.UnmatchedAmountCents += refund.Amount
		}
	}

	if err := os.MkdirAll("/app/out", 0o755); err != nil {
		return err
	}
	if err := writeReport("/app/out/refund_report.csv", reportRows); err != nil {
		return err
	}
	return writeSummary("/app/out/refund_summary.json", summary)
}

func findMatch(bills []Bill, refund Refund, used []bool, openDates map[string]bool, datedMode bool) int {
	bestIndex := -1
	for i := range bills {
		if used[i] {
			continue
		}
		bill := &bills[i]
		if bill.ID != refund.BillID ||
			bill.Customer != refund.Customer ||
			bill.Amount != refund.Amount ||
			bill.Status != "POSTED" ||
			!allowedChannel(bill.Channel) ||
			bill.Channel != refund.Channel {
			continue
		}
		if !datedMode {
			return i
		}
		if !openDates[refund.RefundDate] ||
			refund.RefundDate == "" ||
			bill.DueDate == "" ||
			refund.RefundDate > bill.DueDate {
			continue
		}
		if bestIndex < 0 || bill.DueDate > bills[bestIndex].DueDate {
			bestIndex = i
		}
	}
	return bestIndex
}

func writeReport(path string, rows []ReportRow) error {
	file, err := os.Create(path)
	if err != nil {
		return err
	}
	defer file.Close()

	writer := csv.NewWriter(file)
	defer writer.Flush()
	if err := writer.Write([]string{"bill_id", "customer_id", "channel", "amount_cents", "status"}); err != nil {
		return err
	}
	for _, row := range rows {
		if err := writer.Write([]string{row.BillID, row.Customer, row.Channel, strconv.Itoa(row.Amount), row.Status}); err != nil {
			return err
		}
	}
	return writer.Error()
}

func writeSummary(path string, summary Summary) error {
	data, err := json.Marshal(summary)
	if err != nil {
		return err
	}
	return os.WriteFile(path, data, 0o644)
}

func clean(value string) string {
	return strings.TrimSpace(value)
}

func canonicalChannel(value string) string {
	switch strings.ToUpper(clean(value)) {
	case "CC", "CARD":
		return "CARD"
	case "WIR", "WIRE":
		return "WIRE"
	case "ACH":
		return "ACH"
	default:
		return strings.ToUpper(clean(value))
	}
}

func allowedChannel(channel string) bool {
	switch channel {
	case "ACH", "CARD", "WIRE":
		return true
	default:
		return false
	}
}
GO

/app/scripts/run_batch.sh
test -s /app/out/refund_report.csv
test -s /app/out/refund_summary.json
